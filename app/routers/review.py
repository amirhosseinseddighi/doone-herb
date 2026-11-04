from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from redis import RedisError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import (
    CurrentUser,
    SessionDep,
    get_db,
    require_perm,
)
from app.core.permissions import Permissions, has_perm
from app.core.rate_limiter import limiter
from app.models.category import Product, Review
from app.models.identity import User
from app.models.order import Order, OrderItem
from app.schemas.review import (
    PaginatedReviewResponse,
    ReviewCreate,
    ReviewReplyCreate,
    ReviewResponse,
    ReviewUpdate,
)
import structlog
from app.db.redis_cli import redis_client

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
            # ReviewResponse serializes `replies` recursively, so each reply's
            # own (empty) replies collection must be loaded too.
            selectinload(Review.replies).selectinload(Review.replies),
        )
        .where(Review.id == review_id)
    )
    return result.scalar_one()


ReviewOrNotFound = Annotated[Review, Depends(get_review_or_404)]


def _ensure_can_modify(review: Review, user: User) -> bool:
    """Allow the review's author or a moderator. Returns True if acting as moderator."""
    if review.user_id == user.id:
        return False
    if has_perm(user, Permissions.REVIEWS_MODERATE):
        return True
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


# --------- cache -------
REVIEWS_CACHE_TTL = 60

def _reviews_ver_key(product_id: int) -> str:
    return f"reviews:product:{product_id}:ver"


def _reviews_page_key(product_id: int, version: str, offset: int, limit: int) -> str:
    return f"reviews:product:{product_id}:v{version}:o{offset}:l{limit}"


async def _get_reviews_version(product_id: int) -> str:
    try:
        raw = await redis_client.get(_reviews_ver_key(product_id))
    except RedisError:
        logger.warning("Redis unavailable (version read)", product_id=product_id)
        return "0"
    if raw is None:
        return "0"
    return raw.decode() if isinstance(raw, bytes) else str(raw)


async def _invalidate_product_reviews(product_id: int) -> None:
    """Call AFTER the DB commit."""
    try:
        await redis_client.incr(_reviews_ver_key(product_id))
    except RedisError:
        logger.warning("Review cache invalidation failed", product_id=product_id)

# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@router.get("/product/{product_id}", response_model=PaginatedReviewResponse)
@limiter.limit("2/second")
async def get_product_reviews(
    request: Request,
    product_id: int,
    db: SessionDep,
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
):
    """Retrieve top-level reviews and nested replies for a specific product."""

    version = await _get_reviews_version(product_id)
    cache_key = _reviews_page_key(product_id, version, offset, limit)

    try:
        cached = await redis_client.get(cache_key)
    except RedisError:
        cached = None
    if cached is not None:
        return Response(content=cached, media_type="application/json")


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
            # ReviewResponse serializes `replies` recursively, so each reply's
            # own (empty) replies collection must be loaded too.
            selectinload(Review.replies).selectinload(Review.replies),
        )
        .where(Review.product_id == product_id, Review.parent_id.is_(None))
        .order_by(Review.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(query)
    reviews = result.scalars().all()

    payload = PaginatedReviewResponse(
        items=reviews, total=total, offset=offset, limit=limit
    )
    body = payload.model_dump_json()

    try:
        await redis_client.set(cache_key, body, ex=REVIEWS_CACHE_TTL)
    except RedisError:
        logger.warning("Redis unavailable (cache write)", product_id=product_id)

    return Response(content=body, media_type="application/json")

@router.get("/me", response_model=PaginatedReviewResponse)
@limiter.limit("2/second")
async def get_my_reviews(
    request: Request,
    db: SessionDep,
    current_user: CurrentUser,
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
    
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
            # ReviewResponse serializes `replies` recursively, so each reply's
            # own (empty) replies collection must be loaded too.
            selectinload(Review.replies).selectinload(Review.replies),
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
    db: SessionDep,
    payload: ReviewCreate,
    current_user: CurrentUser,
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

    await _invalidate_product_reviews(payload.product_id)

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
    admin_user: Annotated[User, Depends(require_perm(Permissions.REVIEWS_MODERATE))],
    db: SessionDep,
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

    await _invalidate_product_reviews(parent_review.product_id)

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
    db: SessionDep,
):
    """Update an existing review or reply (by author or admin/staff)."""
        
    by_moderator = _ensure_can_modify(review, current_user)

    update_data = payload.model_dump(exclude_unset=True)
    if review.parent_id is not None and "stars" in update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Replies cannot have a star rating",
        )

    for key, value in update_data.items():
        setattr(review, key, value)

    await db.commit()

    await _invalidate_product_reviews(review.product_id)

    logger.info(
        "Review updated",
        review_id=review.id,
        product_id=review.product_id,
        user_id=current_user.id,
        fields=sorted(update_data.keys()),
        by_admin=by_moderator is not None,
    )
    return await _load_review_for_response(db, review.id)


@router.delete("/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/minute")
async def delete_review(
    request: Request,
    review: ReviewOrNotFound,
    current_user: CurrentUser,
    db: SessionDep,
):
    """Delete a review or reply (by author or admin/staff)."""
    by_moderator = _ensure_can_modify(review, current_user)

    deleted_review_id = review.id
    deleted_product_id = review.product_id

    await db.delete(review)
    await db.commit()

    await _invalidate_product_reviews(deleted_product_id)

    logger.info(
        "Review deleted",
        review_id=deleted_review_id,
        product_id=deleted_product_id,
        user_id=current_user.id,
        by_admin=by_moderator is not None,
    )