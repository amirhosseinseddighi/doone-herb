from fastapi import APIRouter, Depends, HTTPException, status
from typing import Annotated
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy import delete as sql_delete
from app.models.category import (
    Product
)
from app.schemas.products import (
    ProductResponse,
    ProductVariantResponse
)
from app.core.deps import get_db
from app.db.database import AsyncSession


router = APIRouter()


# Get list of all categories
@router.get("", response_model=list[ProductResponse])
async def get_all_products(db: Annotated[AsyncSession, Depends(get_db)]):
    product_result = await db.execute(
            select(Product)
            .options(selectinload(Product.variants))
            .options(selectinload(Product.category))
            .where(Product.is_hidden == False)
            .order_by(Product.updated_at)
    )
    return product_result.scalars().all()
