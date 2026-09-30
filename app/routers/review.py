from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import (
    CurrentAdminOptional,
    CurrentManagerOrOwner,
    CurrentUser,
    get_db,
)
from app.core.rate_limiter import limiter
from app.models.category import Product, Review
from app.models.order import Order, OrderItem
from app.schemas.review import (
    PaginatedReviewResponse,
    ReviewCreate,
    ReviewReplyCreate,
    ReviewResponse,
    ReviewUpdate,
)
import structlog

logger = structlog.get_logger()

router = APIRouter(prefix="/reviews", tags=["reviews"])


# --------------------------------------------------------------------------
# Shared dependencies / helpers
# --------------------------------------------------------------------------

async def get_review_or_404(
    review_id: int,
    db: AsyncSession = Depends(get_db),
) -> Review:
    """Load a review/reply by id or raise 404.

    FastAPI resolves `review_id` from the path even though it's declared
    on this dependency rather than directly on the route function.
    """
    review = await db.get(Review, review_id)
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found",
        )
    return review


async def _load_review_for_response(db: AsyncSession, review_id: int) -> Review:
    """Load a review with everything ReviewResponse's serialization touches.

    ReviewResponse recursively includes `user` and `replies` (and each
    reply's own `user`). Returning an ORM object to a route with
    response_model=ReviewResponse means Pydantic will access those
    attributes during serialization -- outside of any `await`, so any of
    them left unloaded raises MissingGreenlet instead of a clean error.
    Any route returning a single Review should go through this rather
    than a bare `db.get()` / `db.refresh()`, whether or not that review
    is expected to already have replies.
    """
    result = await db.execute(
        select(Review)
        .options(
            selectinload(Review.user),
            selectinload(Review.replies).selectinload(Review.user),
        )
        .where(Review.id == review_id)
    )
    return result.scalar_one()


ReviewOrNotFound = Annotated[Review, Depends(get_review_or_404)]


def _ensure_can_modify(review: Review, current_user: CurrentUser, admin: Optional[object]) -> None:
    """Author of the review, or an admin/manager, may modify it."""
    if review.user_id != current_user.id and admin is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to modify this review",
        )


async def _validate_order_for_review(
    order_id: int,
    product_id: int,
    current_user: CurrentUser,
    db: AsyncSession,
) -> None:
    """Ensure the order belongs to the user and contains the product."""
    order = await db.get(Order, order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )
    if order.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Order does not belong to the current user",
        )

    item_stmt = select(OrderItem).where(
        OrderItem.order_id == order_id,
        OrderItem.product_id == product_id,
    )
    order_item = (await db.execute(item_stmt)).scalar_one_or_none()
    if not order_item:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Product was not part of this order",
        )


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@router.get("/product/{product_id}", response_model=PaginatedReviewResponse)
@limiter.limit("2/second")
async def get_product_reviews(
    request: Request,
    product_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve top-level reviews and nested replies for a specific product."""
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    total_query = select(func.count(Review.id)).where(
        Review.product_id == product_id,
        Review.parent_id.is_(None),
    )
    total = (await db.execute(total_query)).scalar_one()

    query = (
        select(Review)
        .options(
            selectinload(Review.user),
            selectinload(Review.replies).selectinload(Review.user),
        )
        .where(Review.product_id == product_id, Review.parent_id.is_(None))
        .order_by(Review.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(query)
    reviews = result.scalars().all()

    return PaginatedReviewResponse(
        items=reviews,
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/me", response_model=PaginatedReviewResponse)
@limiter.limit("2/second")
async def get_my_reviews(
    request: Request,
    current_user: CurrentUser,
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List the current user's own top-level reviews, with any replies on them."""
    total_query = select(func.count(Review.id)).where(
        Review.user_id == current_user.id,
        Review.parent_id.is_(None),
    )
    total = (await db.execute(total_query)).scalar_one()

    query = (
        select(Review)
        .options(
            selectinload(Review.user),
            selectinload(Review.replies).selectinload(Review.user),
        )
        .where(Review.user_id == current_user.id, Review.parent_id.is_(None))
        .order_by(Review.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(query)
    reviews = result.scalars().all()

    return PaginatedReviewResponse(
        items=reviews,
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post("", response_model=ReviewResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/hour")
async def create_review(
    request: Request,
    payload: ReviewCreate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    """Submit a top-level product review."""
    product = await db.get(Product, payload.product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    if payload.order_id is not None:
        await _validate_order_for_review(
            payload.order_id, payload.product_id, current_user, db
        )

    existing_stmt = select(Review).where(
        Review.product_id == payload.product_id,
        Review.user_id == current_user.id,
        Review.parent_id.is_(None),
    )
    existing_review = (await db.execute(existing_stmt)).scalar_one_or_none()
    if existing_review:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You have already reviewed this product",
        )

    review = Review(
        product_id=payload.product_id,
        user_id=current_user.id,
        order_id=payload.order_id,
        stars=payload.stars,
        text=payload.text,
    )
    db.add(review)
    try:
        await db.commit()
    except IntegrityError:
        # Guards the race window between the SELECT above and this INSERT.
        # Requires a partial unique constraint, e.g.
        # UNIQUE (product_id, user_id) WHERE parent_id IS NULL.
        await db.rollback()
        logger.warning(
            "Duplicate review rejected",
            product_id=payload.product_id,
            user_id=current_user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You have already reviewed this product",
        )

    logger.info(
        "Review created",
        review_id=review.id,
        product_id=payload.product_id,
        user_id=current_user.id,
        stars=payload.stars,
        has_order=payload.order_id is not None,
    )
    return await _load_review_for_response(db, review.id)


@router.post("/{review_id}/reply", response_model=ReviewResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def reply_to_review(
    request: Request,
    payload: ReviewReplyCreate,
    parent_review: ReviewOrNotFound,
    admin_user: CurrentManagerOrOwner,
    db: AsyncSession = Depends(get_db),
):
    """Post an admin/manager reply to a top-level review."""
    if parent_review.parent_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot reply to a reply; replies only nest one level deep",
        )

    reply = Review(
        product_id=parent_review.product_id,
        user_id=admin_user.id,
        parent_id=parent_review.id,
        text=payload.text,
        stars=None,
    )
    db.add(reply)
    await db.commit()

    logger.info(
        "Review reply created",
        review_id=reply.id,
        parent_review_id=parent_review.id,
        product_id=parent_review.product_id,
        admin_id=admin_user.id,
    )
    return await _load_review_for_response(db, reply.id)


@router.patch("/{review_id}", response_model=ReviewResponse)
@limiter.limit("10/minute")
async def update_review(
    request: Request,
    payload: ReviewUpdate,
    review: ReviewOrNotFound,
    current_user: CurrentUser,
    current_admin: CurrentAdminOptional,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing review or reply (by author or admin/staff)."""
    _ensure_can_modify(review, current_user, current_admin)

    update_data = payload.model_dump(exclude_unset=True)
    if review.parent_id is not None and "stars" in update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Replies cannot have a star rating",
        )

    for key, value in update_data.items():
        setattr(review, key, value)

    await db.commit()

    logger.info(
        "Review updated",
        review_id=review.id,
        product_id=review.product_id,
        user_id=current_user.id,
        fields=sorted(update_data.keys()),
        by_admin=current_admin is not None,
    )
    return await _load_review_for_response(db, review.id)


@router.delete("/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/minute")
async def delete_review(
    request: Request,
    review: ReviewOrNotFound,
    current_user: CurrentUser,
    current_admin: CurrentAdminOptional,
    db: AsyncSession = Depends(get_db),
):
    """Delete a review or reply (by author or admin/staff)."""
    _ensure_can_modify(review, current_user, current_admin)

    deleted_review_id = review.id
    deleted_product_id = review.product_id

    await db.delete(review)
    await db.commit()

    logger.info(
        "Review deleted",
        review_id=deleted_review_id,
        product_id=deleted_product_id,
        user_id=current_user.id,
        by_admin=current_admin is not None,
    )