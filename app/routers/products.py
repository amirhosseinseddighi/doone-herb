from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from typing import Annotated
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy import delete as sql_delete
from app.models.category import (
    Offer,
    Product,
    ProductVariant
)
from app.schemas.products import (
    ProductResponse,
    ProductVariantResponse
)
from app.core.deps import get_db
from app.db.database import AsyncSession


router = APIRouter()


# Get list of all products
@router.get("", response_model=list[ProductResponse])
async def get_all_products(db: Annotated[AsyncSession, Depends(get_db)]):
    now = datetime.now(UTC)
    result = await db.execute(
        select(Product)
        .options(
            selectinload(Product.variants).selectinload(
                ProductVariant.offers.and_(
                    Offer.active.is_(True),
                    Offer.starts_at <= now,
                    Offer.ends_at >= now,
                )
            ),
            selectinload(Product.category),
        )
        .where(Product.is_hidden.is_(False))
        .order_by(Product.updated_at)
    )
    return result.scalars().all()
