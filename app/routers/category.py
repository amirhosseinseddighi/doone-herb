from fastapi import APIRouter, Depends, HTTPException, status
from typing import Annotated
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy import delete as sql_delete
from app.models.category import (
    Category
)
from app.schemas.categories import (
    CategoryResponse
)
from app.core.deps import get_db
from app.db.database import AsyncSession


router = APIRouter()


# Get list of all categories
@router.get("", response_model=list[CategoryResponse])
async def get_all_categories(db: Annotated[AsyncSession, Depends(get_db)]):
    category_result = await db.execute(
            select(Category)
            .where(Category.is_active == True)
            .order_by(Category.sort_order.desc())
    )
    return category_result.scalars().all()
