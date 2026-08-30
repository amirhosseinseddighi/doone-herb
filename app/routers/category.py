from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from slugify import slugify
from sqlalchemy import select

from app.core.deps import CurrentManagerOrOwner, get_db
from app.db.database import AsyncSession
from app.models.category import Category
from app.schemas.categories import CategoryResponse, NewCategoryRequest, UpdateCategoryRequest

router = APIRouter()


@router.get("", response_model=list[CategoryResponse])
async def get_all_categories(db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(
        select(Category)
        .where(Category.is_active.is_(True) & Category.is_deleted.is_(False))
        .order_by(Category.sort_order.desc())
    )
    return result.scalars().all()


# ================= ADMIN OPERATIONS ===================

@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def add_category(
    admin: CurrentManagerOrOwner,
    new_category: NewCategoryRequest,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    slug = slugify(new_category.name, allow_unicode=True)
    counter = 1

    while True:
        existing = await db.execute(select(Category).where(Category.slug == slug))
        if not existing.scalar_one_or_none():
            break
        slug = f"{slugify(new_category.name, allow_unicode=True)}-{counter}"
        counter += 1

    category = Category(
        name=new_category.name,
        slug=slug,
        tint_color=new_category.tint_color,
        dot_color=new_category.dot_color,
        sort_order=new_category.sort_order,
        is_active=new_category.is_active,
    )

    db.add(category)
    await db.commit()
    await db.refresh(category)
    return category


@router.patch("/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: int,
    category_update: UpdateCategoryRequest,
    admin: CurrentManagerOrOwner,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(
        select(Category).where((Category.id == category_id) & (Category.is_deleted.is_(False)))
    )
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

    update_data = category_update.model_dump(exclude_unset=True)

    if "name" in update_data and update_data["name"] != category.name:
        new_slug = slugify(update_data["name"], allow_unicode=True)
        slug = new_slug
        counter = 1
        while True:
            existing = await db.execute(
                select(Category).where((Category.slug == slug) & (Category.id != category_id))
            )
            if not existing.scalar_one_or_none():
                break
            slug = f"{new_slug}-{counter}"
            counter += 1
        category.slug = slug

    for field, value in update_data.items():
        setattr(category, field, value)

    await db.commit()
    await db.refresh(category)
    return category


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: int,
    admin: CurrentManagerOrOwner,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(
        select(Category).where((Category.id == category_id) & (Category.is_deleted.is_(False)))
    )
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

    # Soft delete category
    category.is_deleted = True
    category.is_active = False
    await db.commit()
    return None