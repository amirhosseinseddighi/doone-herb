from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from typing import Annotated
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload, with_loader_criteria
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
            selectinload(Product.category),
            selectinload(Product.variants).selectinload(ProductVariant.offers),
            with_loader_criteria(
                Offer, 
                lambda cls: cls.active.is_(True) & (cls.starts_at <= now) & (cls.ends_at >= now), 
                include_aliases=True
            )
        )
        .where(Product.is_hidden.is_(False))
        .order_by(Product.updated_at)
    )
    return result.scalars().all()




@router.get(
        "/{product_slug}", 
        response_model=ProductResponse,
        status_code=status.HTTP_200_OK
)
async def show_product_details(product_slug: str, db: Annotated[AsyncSession, Depends(get_db)]):

    now = datetime.now(UTC)
    product_result = await db.execute(
            select(Product)
            .options(
                selectinload(Product.category),
                selectinload(Product.variants)
                .selectinload(ProductVariant.offers),
                with_loader_criteria(
                    Offer, 
                    lambda cls: cls.active.is_(True) & (cls.starts_at <= now) & (cls.ends_at >= now), 
                    include_aliases=True
                )
            )
            .where(Product.is_hidden.is_(False) & (func.lower(Product.slug) == product_slug.lower()))
        )

    product = product_result.scalars().first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    return product