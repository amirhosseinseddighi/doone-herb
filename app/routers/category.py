from typing import Annotated

from PIL import UnidentifiedImageError
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from slugify import slugify
from sqlalchemy import and_, func, select

from app.core.config import settings
from app.core.deps import CurrentManagerOrOwner, get_db
from app.db.database import AsyncSession
from app.models.category import Category, Product, ProductVariant
from app.schemas.categories import (
    CategoryDetails,
    CategoryImageResponse,
    CategoryResponse,
    NewCategoryRequest,
    UpdateCategoryRequest,
)
from app.utils.image_utils import delete_image_file, process_category_image
from sqlalchemy.orm import selectinload

from app.schemas.products import BaseProductResponse
router = APIRouter(prefix="/categories", tags=["category"])



@router.get("", response_model=list[CategoryResponse])
async def get_all_categories(
    db: Annotated[AsyncSession, Depends(get_db)],
    search: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=100,
            description="Search categories by name",
        ),
    ] = None,
):
    conditions = [Category.is_active.is_(True), Category.is_deleted.is_(False)]

    if search is not None:
        term = search.strip()
        if term:
            escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped}%"
            conditions.append(Category.name.ilike(pattern, escape="\\"))

    result = await db.execute(
        select(Category)
        .where(and_(*conditions))
        .order_by(Category.sort_order.desc())
    )
    return result.scalars().all()


@router.get("/{category_id}", response_model=CategoryDetails)
async def get_category_details(
    category_id: int,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    stmt = (
        select(Category)
        .where(Category.id == category_id)
        .options(selectinload(Category.products))
    )
    category_res = await db.execute(stmt)
    category = category_res.scalar_one_or_none()

    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category does not exist"
        )

    return CategoryDetails(
        id=category.id,
        slug=category.slug,
        name=category.name,
        tint_color=category.tint_color,
        dot_color=category.dot_color,
        sort_order=category.sort_order,
        is_active=category.is_active,
        products=[BaseProductResponse.model_validate(p) for p in category.products],
        total_products=len(category.products),
    )

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


# ============= CATEGORY IMAGE ===================


async def _get_active_category(db: AsyncSession, category_id: int) -> Category:
    """Load a non-soft-deleted category or 404."""
    result = await db.execute(
        select(Category).where((Category.id == category_id) & (Category.is_deleted.is_(False)))
    )
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    return category


@router.get("/{category_id}/image", response_model=CategoryImageResponse)
async def get_category_image(
    category_id: int,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    category = await _get_active_category(db, category_id)

    if not category.image_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category image not found"
        )

    return category


@router.post("/{category_id}/image", response_model=CategoryImageResponse)
async def upload_category_image(
    category_id: int,
    file: UploadFile,
    admin: CurrentManagerOrOwner,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    category = await _get_active_category(db, category_id)

    image = await file.read()

    if not image:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is empty"
        )

    # check image size
    max_image_size = settings.MAX_IMAGE_SIZE_MEGA_BYTE * 1024 * 1024
    if len(image) > max_image_size:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Image size is larger than limit: {settings.MAX_IMAGE_SIZE_MEGA_BYTE}MB"
        )

    try:
        new_filename = await run_in_threadpool(process_category_image, image)

    except UnidentifiedImageError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image file. Please upload a valid image (JPEG, PNG, GIF, WebP).",
        ) from err

    # replacing an existing image leaves the old file orphaned otherwise
    previous_image_url = category.image_url

    category.image_url = new_filename
    await db.commit()
    await db.refresh(category)

    delete_image_file(previous_image_url)

    return category


@router.delete("/{category_id}/image", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category_image(
    category_id: int,
    admin: CurrentManagerOrOwner,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    category = await _get_active_category(db, category_id)

    if not category.image_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category image not found"
        )

    image_url = category.image_url
    category.image_url = None
    await db.commit()

    delete_image_file(image_url)

    return None