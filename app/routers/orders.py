from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import CurrentAdmin, CurrentUser, get_db
from app.models.identity import Roles
from app.models.cart import Cart, CartItem
from app.models.category import ProductVariant
from app.models.order import (
    DeliverySlot,
    Order,
    OrderItem,
    OrderStatus,
    OrderStatusEvent,
    OrderStatusEventActor,
    PaymentStatus,
)

from app.models.identity import Address

from app.schemas.orders import (
    DeliverySlotRead,
    OrderCreate,
    OrderFulfillmentUpdate,
    OrderListResponse,
    OrderRead,
    OrderStatusUpdate,
    OrderSummary,
)

router = APIRouter(prefix="/orders", tags=["orders"])


# Statuses a customer can still back out of themselves.
CANCELLABLE_STATUSES = {OrderStatus.NEW, OrderStatus.PACKING}

# Legal forward transitions for staff-driven status changes.
ALLOWED_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.NEW: {OrderStatus.PACKING, OrderStatus.CANCELLED},
    OrderStatus.PACKING: {OrderStatus.SHIPPED, OrderStatus.CANCELLED},
    OrderStatus.SHIPPED: {OrderStatus.OUT_FOR_DELIVERY, OrderStatus.RETURNED},
    OrderStatus.OUT_FOR_DELIVERY: {OrderStatus.DELIVERED, OrderStatus.RETURNED},
    OrderStatus.DELIVERED: set(),
    OrderStatus.RETURNED: set(),
    OrderStatus.CANCELLED: set(),
}

ORDER_DETAIL_OPTIONS = (
    selectinload(Order.items),
    selectinload(Order.status_events),
    selectinload(Order.payments),
    selectinload(Order.delivery_slot),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_order_no() -> str:
    return f"ORD-{datetime.now(UTC):%Y%m%d}-{uuid.uuid4().hex[:8].upper()}"


async def _get_user_cart_with_items(user_id: int, db: AsyncSession) -> Optional[Cart]:
    stmt = select(Cart).options(
        selectinload(Cart.items)
        .joinedload(CartItem.product_variant)
        .joinedload(ProductVariant.product)
    ).where(Cart.user_id == user_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _load_order_or_404(order_id: int, db: AsyncSession) -> Order:
    stmt = select(Order).options(*ORDER_DETAIL_OPTIONS).where(Order.id == order_id)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order


async def _load_order_by_order_no_or_404(order_no: str, db: AsyncSession) -> Order:
    stmt = select(Order).options(*ORDER_DETAIL_OPTIONS).where(Order.order_no == order_no)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order

def _ensure_owner_or_staff(order: Order, user) -> None:
    if order.user_id != user.id and user.role not in (Roles.OWNER, Roles.MANAGER, Roles.PACKER):
        # 404 rather than 403 --> this will prevent enumeration
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")




# ---------------------------------------------------------------------------
# Checkout reference data
# ---------------------------------------------------------------------------

@router.get("/delivery-slots", response_model=list[DeliverySlotRead])
async def list_delivery_slots(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(DeliverySlot).where(DeliverySlot.active.is_(True)).order_by(DeliverySlot.cutoff_time)
    )
    return result.scalars().all()


# ---------------------------------------------------------------------------
# Checkout — logged-in users only
# ---------------------------------------------------------------------------

@router.post("/checkout", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
async def checkout(
    payload: OrderCreate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    # --- address must belong to the caller ---
    address = await db.get(Address, payload.address_id)
    if not address or address.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Address not found")

    # --- delivery slot must exist and be active ---
    slot = await db.get(DeliverySlot, payload.delivery_slot_id)
    if not slot or not slot.active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Delivery slot not available")

    # Pickup slots must use pickup fulfillment and vice versa
    slot_is_pickup = slot.kind.value == "pickup"
    method_is_pickup = payload.fulfillment_method.value == "pickup"
    if slot_is_pickup != method_is_pickup:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Fulfillment method doesn't match the selected delivery slot",
        )


    # --- cart must have items ---
    cart = await _get_user_cart_with_items(current_user.id, db)
    if not cart or not cart.items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cart is empty")

    order_items: list[OrderItem] = []
    subtotal = 0

    for cart_item in cart.items:
        if (
            cart_item.product_variant is None
            or cart_item.product_variant.product is None
            or cart_item.product_variant.product.is_deleted
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An item in your cart is no longer available",
            )

        # Lock the variant row so two concurrent checkouts can't oversell it.
        locked = await db.execute(
            select(ProductVariant)
            .where(ProductVariant.id == cart_item.product_variant_id)
            .with_for_update()
        )
        variant = locked.scalar_one()

        if variant.stock_qty < cart_item.qty:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Not enough stock for {variant.product.name}",
            )

        variant.stock_qty -= cart_item.qty

        line_total = variant.price * cart_item.qty
        order_items.append(
            OrderItem(
                product_id=variant.product_id,
                product_variant_id=variant.id,
                name_snapshot=variant.product.name,
                size_label_snapshot=variant.label,
                unit_price_snapshot=variant.price,
                qty=cart_item.qty,
                line_total=line_total,
            )
        )
        subtotal += line_total

    delivery_fee = slot.fee
    discount = 0  # no coupon/promo system wired up yet
    total = subtotal + delivery_fee - discount

    order = Order(
        order_no=_generate_order_no(),
        user_id=current_user.id,
        address_id=address.id,
        delivery_slot_id=slot.id,
        status=OrderStatus.NEW,
        fulfillment_method=payload.fulfillment_method,
        subtotal=subtotal,
        delivery_fee=delivery_fee,
        discount=discount,
        total=total,
        payment_method=payload.payment_method,
        payment_status=PaymentStatus.PENDING,  # updated separately once payment settles
        note=payload.note,
        items=order_items,
        status_events=[
            OrderStatusEvent(
                status=OrderStatus.NEW,
                actor=OrderStatusEventActor.SYSTEM,
                note="Order placed",
            )
        ],
    )
    db.add(order)

    # Empty the cart, keep the row (mirrors clear_cart's behavior elsewhere).
    for item in cart.items:
        await db.delete(item)

    try:
        await db.commit()
    except IntegrityError:
        # Extremely unlikely order_no collision — retry once with a fresh one.
        await db.rollback()
        order.order_no = _generate_order_no()
        db.add(order)
        await db.commit()

    return await _load_order_or_404(order.id, db)


# ---------------------------------------------------------------------------
# Customer-facing reads / actions
# ---------------------------------------------------------------------------

@router.get("", response_model=OrderListResponse)
async def list_my_orders(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[OrderStatus] = Query(None, alias="status"),
):
    stmt = select(Order).where(Order.user_id == current_user.id)
    if status_filter:
        stmt = stmt.where(Order.status == status_filter)

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()

    stmt = stmt.order_by(Order.placed_at.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(stmt)).scalars().all()

    return OrderListResponse(
        items=[OrderSummary.model_validate(o) for o in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/code/{order_no}", response_model=OrderRead)
async def get_order_by_order_no(
    order_no: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    order = await _load_order_by_order_no_or_404(order_no, db)
    _ensure_owner_or_staff(order, current_user)
    return order


@router.get("/{order_id}", response_model=OrderRead)
async def get_order(
    order_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    order = await _load_order_or_404(order_id, db)
    _ensure_owner_or_staff(order, current_user)
    return order


@router.post("/{order_id}/cancel", response_model=OrderRead)
async def cancel_order(
    order_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    order = await _load_order_or_404(order_id, db)
    _ensure_owner_or_staff(order, current_user)

    if order.status not in CANCELLABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Order in status '{order.status.value}' can no longer be cancelled",
        )

    for item in order.items:
        variant_res = await db.execute(select(ProductVariant).where(ProductVariant.id == item.product_variant_id).with_for_update())
        variant = variant_res.scalar_one_or_none()
        if variant:
            variant.stock_qty += item.qty

    order.status = OrderStatus.CANCELLED
    # OrderStatusEventActor has no "customer" option, so a customer-triggered
    # cancellation is logged as SYSTEM with a note explaining who asked for it.
    order.status_events.append(
        OrderStatusEvent(
            status=OrderStatus.CANCELLED,
            actor=OrderStatusEventActor.SYSTEM,
            note="Cancelled by customer",
        )
    )
    await db.commit()
    return await _load_order_or_404(order.id, db)


# ====================== ADMIN OPERATIONS ========================

@router.get("/admin/all", response_model=OrderListResponse)
async def list_all_orders(
    _staff: CurrentAdmin,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[OrderStatus] = Query(None, alias="status"),
    user_id: Optional[int] = Query(None),
):
    stmt = select(Order).options(selectinload(Order.user))
    if status_filter:
        stmt = stmt.where(Order.status == status_filter)
    if user_id:
        stmt = stmt.where(Order.user_id == user_id)


    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()

    stmt = stmt.order_by(Order.placed_at.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(stmt)).scalars().unique().all()
    return OrderListResponse(
        items=[OrderSummary.model_validate(o) for o in rows],
        total=total,
        page=page,
        page_size=page_size
    )


@router.patch("/{order_id}/status", response_model=OrderRead)
async def update_order_status(
    order_id: int,
    payload: OrderStatusUpdate,
    staff: CurrentAdmin,
    db: AsyncSession = Depends(get_db),
):
    order = await _load_order_or_404(order_id, db)

    allowed = ALLOWED_TRANSITIONS.get(order.status, set())
    if payload.status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot move order from '{order.status.value}' to '{payload.status.value}'",
        )

    order.status = payload.status
    order.status_events.append(
        OrderStatusEvent(
            status=payload.status,
            actor=OrderStatusEventActor.ADMIN,
            actor_user_id=staff.id,
            note=payload.note,
        )
    )
    await db.commit()
    await db.refresh(order)
    return order


@router.patch("/{order_id}/fulfillment", response_model=OrderRead)
async def update_order_fulfillment(
    order_id: int,
    payload: OrderFulfillmentUpdate,
    _staff: CurrentAdmin,
    db: AsyncSession = Depends(get_db),
):
    """Attach/update tracking details — no status change."""
    order = await _load_order_or_404(order_id, db)

    if payload.tracking_code is not None:
        order.tracking_code = payload.tracking_code

    await db.commit()
    await db.refresh(order)
    return order