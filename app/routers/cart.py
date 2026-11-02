import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.core.deps import CartIdentityDep, CurrentUser, OptionalUser, RequiredCartIdentityDep, SessionDep, get_db
from app.db.database import AsyncSession
from app.models.category import ProductVariant
from app.models.cart import Cart, CartItem
from app.schemas.cart import AddCartItemRequest, CartItemResponse, CartResponse, DeleteCartItemResponse, UpdateCartItemRequest
from app.core.config import settings
from app.core.rate_limiter import limiter
import structlog

logger = structlog.get_logger()

router = APIRouter(prefix="/cart", tags=["cart"])


# ========== HELPERS =============
def _filter_by_owner(stmt, user_id: Optional[int], guest_token: Optional[str]):
    """Apply the recurring 'owned by this user or this guest' where-clause."""
    if user_id:
        return stmt.where(Cart.user_id == user_id)
    return stmt.where(Cart.guest_token == guest_token)


async def _find_cart(
    db: AsyncSession,
    *,
    user_id: Optional[int] = None,
    guest_token: Optional[str] = None,
) -> Optional[Cart]:
    """Fetch a cart with its items only (no variant/product join)."""
    if not user_id and not guest_token:
        return None

    stmt = _filter_by_owner(
        select(Cart).options(selectinload(Cart.items)), user_id, guest_token
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _get_cart_with_items(
    db: AsyncSession,
    user_id: Optional[int] = None,
    guest_token: Optional[str] = None,
) -> Optional[Cart]:
    """Get cart with items, product variants, and parent products."""
    if not user_id and not guest_token:
        return None

    stmt = _filter_by_owner(
        select(Cart).options(
            selectinload(Cart.items)
            .joinedload(CartItem.product_variant)
            .joinedload(ProductVariant.product)
        ),
        user_id,
        guest_token,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


def _issue_guest_token(response: Response) -> str:
    """Mint a new guest token and set it as a cookie. Caller decides whether a Cart row is created."""
    guest_token = str(uuid.uuid4())
    response.set_cookie(
        key="guest_cart_token",
        value=guest_token,
        httponly=True,
        max_age=settings.GUEST_CART_MAX_AGE,
        samesite="lax",
    )
    return guest_token


async def _get_or_create_cart(
    db: AsyncSession,
    user_id: Optional[int],
    guest_token: Optional[str],
    response: Response,
) -> Cart:
    """Get existing cart or create a new cart for user/guest."""
    if user_id:
        cart = await _find_cart(db, user_id=user_id)
        if not cart:
            cart = Cart(user_id=user_id, guest_token=str(uuid.uuid4()))
            db.add(cart)
            await db.flush()
        return cart

    # guest user flow
    if guest_token:
        cart = await _find_cart(db, guest_token=guest_token)
        if cart:
            return cart

    # create new guest cart if no valid token or existing cart was found
    new_guest_token = _issue_guest_token(response)
    cart = Cart(guest_token=new_guest_token)
    db.add(cart)
    await db.flush()

    return cart


async def _get_variant_or_404(db: AsyncSession, variant_id: int) -> ProductVariant:
    result = await db.execute(
        select(ProductVariant).where(
            (ProductVariant.id == variant_id) & (ProductVariant.is_deleted.is_(False))
        )
    )
    variant = result.scalar_one_or_none()
    if not variant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product variant not found",
        )
    return variant


def _build_cart_response(
    cart: Optional[Cart], user_id: Optional[int], guest_token: Optional[str]
) -> CartResponse:
    """Build a proper cart response to return to the user."""
    if not cart:
        return CartResponse(
            id=0,
            user_id=user_id,
            guest_token=guest_token or "",
            items=[],
            total_items=0,
            total_price=0,
        )

    items_response = []
    total_price = 0
    total_items = 0

    for item in cart.items:
        variant = item.product_variant
        product = variant.product if variant else None

        price = variant.price if variant else 0
        subtotal = price * item.qty

        total_items += item.qty
        total_price += subtotal

        items_response.append(
            CartItemResponse(
                id=item.id,
                product_variant_id=item.product_variant_id,
                qty=item.qty,
                product_name=product.name if product else None,
                variant_label=variant.label if variant else None,
                price=price,
                stock_qty=variant.stock_qty if variant else 0,
                subtotal=subtotal,
            )
        )

    return CartResponse(
        id=cart.id,
        user_id=cart.user_id,
        guest_token=cart.guest_token,
        items=items_response,
        total_items=total_items,
        total_price=total_price,
    )



async def merge_guest_cart_to_user(
    guest_token: str, current_user: CurrentUser, db: AsyncSession
) -> None:
    """Merge current guest cart with the authenticated user cart during login or signup."""
    if not guest_token:
        return

    guest_cart = await _find_cart(db, guest_token=guest_token)
    if not guest_cart or not guest_cart.items:
        return

    user_cart = await _find_cart(db, user_id=current_user.id)

    # if user doesn't have a cart, then convert guest cart to user cart
    if not user_cart:
        guest_cart.user_id = current_user.id
        guest_cart.guest_token = ""
        await db.commit()
        logger.info(
            "Guest cart converted to user cart",
            user_id=current_user.id,
            item_count=len(guest_cart.items),
        )
        return

    # merge items into existing user cart
    user_items_map = {item.product_variant_id: item for item in user_cart.items}

    # get all variants
    guest_variant_ids = [item.product_variant_id for item in guest_cart.items]
    variants_stmt = select(ProductVariant).where(ProductVariant.id.in_(guest_variant_ids))
    variants_res = await db.execute(variants_stmt)
    variant_map = {v.id: v for v in variants_res.scalars().all()}

    for guest_item in guest_cart.items:
        variant = variant_map.get(guest_item.product_variant_id)
        if not variant or variant.stock_qty <= 0:
            continue

        if guest_item.product_variant_id in user_items_map:
            existing_item = user_items_map[guest_item.product_variant_id]
            existing_item.qty = min(existing_item.qty + guest_item.qty, variant.stock_qty)
        else:
            guest_item.qty = min(guest_item.qty, variant.stock_qty)
            guest_cart.items.remove(guest_item)
            user_cart.items.append(guest_item)

    await db.delete(guest_cart)
    await db.commit()

    logger.info(
        "Guest cart merged into user cart",
        user_id=current_user.id,
        guest_items=len(guest_variant_ids),
        user_items_before=len(user_items_map),
    )






# ======== ENDPOINTS =======

@router.get("", response_model=CartResponse)
@limiter.limit("2/second")
async def get_cart(
    request: Request,
    db: SessionDep,
    response: Response,
    identity: CartIdentityDep,
):
    guest_token = identity.guest_token
    if not identity.user_id and not guest_token:
        # for new users
        guest_token = _issue_guest_token(response)

    cart = await _get_cart_with_items(db, user_id=identity.user_id, guest_token=guest_token)
    return _build_cart_response(cart, identity.user_id, guest_token)


@router.post("", status_code=status.HTTP_200_OK)
@limiter.limit("30/minute")
async def add_item_to_cart(
    request: Request,
    db: SessionDep,
    cart_request: AddCartItemRequest,
    response: Response,
    identity: CartIdentityDep,
):
    variant = await _get_variant_or_404(db, cart_request.product_variant_id)

    if variant.stock_qty < cart_request.qty:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Not enough quantity in stock",
        )

    # get or create active cart
    cart = await _get_or_create_cart(db, identity.user_id, identity.guest_token, response)

    # add or update cart
    item_stmt = select(CartItem).where(
        (CartItem.cart_id == cart.id)
        & (CartItem.product_variant_id == cart_request.product_variant_id)
    )
    item_result = await db.execute(item_stmt)
    cart_item = item_result.scalar_one_or_none()

    if cart_item:
        new_qty = cart_item.qty + cart_request.qty
        if variant.stock_qty < new_qty:
            logger.warning(
                "Cart add rejected: exceeds stock",
                cart_id=cart.id,
                user_id=identity.user_id,
                variant_id=cart_request.product_variant_id,
                requested_qty=new_qty,
                stock_qty=variant.stock_qty,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot add more. Total requested quantity ({new_qty}) exceeds stock ({variant.stock_qty}).",
            )
        cart_item.qty = new_qty
        action = "updated"
    else:
        cart_item = CartItem(
            cart_id=cart.id,
            product_variant_id=cart_request.product_variant_id,
            qty=cart_request.qty,
        )
        db.add(cart_item)
        action = "added"

    await db.commit()

    logger.info(
        "Cart item added",
        cart_id=cart.id,
        user_id=identity.user_id,
        variant_id=cart_request.product_variant_id,
        qty=cart_request.qty,
        action=action,
    )
    return {"message": "Item added to cart successfully", "cart_id": cart.id}


@router.delete("/{cart_item_id}", response_model=DeleteCartItemResponse)
@limiter.limit("30/minute")
async def delete_cart_item(
    request: Request,
    cart_item_id: int,
    db: SessionDep,
    identity: RequiredCartIdentityDep,
):
    """Delete one item from cart."""
    stmt = _filter_by_owner(
        select(CartItem).join(Cart, CartItem.cart_id == Cart.id).where(CartItem.id == cart_item_id),
        identity.user_id,
        identity.guest_token,
    )
    result = await db.execute(stmt)
    cart_item = result.scalar_one_or_none()

    if not cart_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cart item not found",
        )

    cart_id = cart_item.cart_id
    await db.delete(cart_item)
    await db.commit()

    logger.info(
        "Cart item removed",
        cart_id=cart_id,
        cart_item_id=cart_item_id,
        user_id=identity.user_id,
    )

    return {"message": "Item removed from cart", "cart_id": cart_id}


@router.delete("", response_model=CartResponse)
@limiter.limit("10/minute")
async def clear_cart(
    request: Request,
    db: SessionDep,
    identity: RequiredCartIdentityDep,
):
    """Clear entire cart."""
    cart = await _get_cart_with_items(db, user_id=identity.user_id, guest_token=identity.guest_token)

    if not cart:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cart not found",
        )

    removed_count = len(cart.items)
    for item in cart.items:
        await db.delete(item)

    await db.commit()

    logger.info(
        "Cart cleared",
        cart_id=cart.id,
        user_id=identity.user_id,
        removed_items=removed_count,
    )

    # cart now has no items, return empty cart
    cart.items = []
    return _build_cart_response(cart, identity.user_id, identity.guest_token)



@router.patch("/{cart_item_id}", response_model=CartResponse)
@limiter.limit("30/minute")
async def update_cart_item(
    request: Request,
    cart_item_id: int,
    update_request: UpdateCartItemRequest,
    db: SessionDep,
    identity: RequiredCartIdentityDep,
):
    """Update the quantity of an existing cart item."""
    stmt = _filter_by_owner(
        select(CartItem).join(Cart, CartItem.cart_id == Cart.id).where(CartItem.id == cart_item_id),
        identity.user_id,
        identity.guest_token,
    )
    result = await db.execute(stmt)
    cart_item = result.scalar_one_or_none()

    if not cart_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cart item not found",
        )

    variant = await _get_variant_or_404(db, cart_item.product_variant_id)

    if variant.stock_qty < update_request.qty:
        logger.warning(
            "Cart update rejected: exceeds stock",
            cart_item_id=cart_item_id,
            user_id=identity.user_id,
            requested_qty=update_request.qty,
            stock_qty=variant.stock_qty,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only {variant.stock_qty} left in stock",
        )

    previous_qty = cart_item.qty
    cart_item.qty = update_request.qty
    await db.commit()

    logger.info(
        "Cart item quantity updated",
        cart_id=cart_item.cart_id,
        cart_item_id=cart_item_id,
        user_id=identity.user_id,
        previous_qty=previous_qty,
        new_qty=update_request.qty,
    )

    cart = await _get_cart_with_items(db, user_id=identity.user_id, guest_token=identity.guest_token)
    return _build_cart_response(cart, identity.user_id, identity.guest_token)