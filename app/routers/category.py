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



"""
GET /api/categories — sorted by sort_order
 GET /api/products?category=&q=&sort= — start q as a simple ILIKE match on name (Day 12 swaps this for real tsvector search); exclude is_hidden=true
 GET /api/products/:id — sizes, images, and the notes-by-category content block
 GET /api/offers — only offers where active=true and current time is within starts_at/ends_at
 GET /api/notes?category=, GET /api/faqs, GET /api/shipping-info — if §2 didn't give these an explicit table, add a minimal content_blocks-style table now rather than hardcoding the content in Python
"""