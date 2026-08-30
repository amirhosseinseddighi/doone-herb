from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from slugify import slugify
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload, with_loader_criteria

from app.core.deps import CurrentManagerOrOwner, get_db
from app.db.database import AsyncSession
from app.models.category import Category, Offer, Product, ProductVariant
from app.schemas.products import NewProductRequest, ProductResponse
from app.utils import generate_sku

router = APIRouter()


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
        .where(Product.is_hidden.is_(False) & Product.is_deleted.is_(False))
        .order_by(Product.updated_at.desc())
    )
    return result.scalars().all()


@router.get("/{product_slug}", response_model=ProductResponse, status_code=status.HTTP_200_OK)
async def show_product_details(product_slug: str, db: Annotated[AsyncSession, Depends(get_db)]):
    now = datetime.now(UTC)
    product_result = await db.execute(
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
        .where(
            Product.is_hidden.is_(False) & 
            Product.is_deleted.is_(False) & 
            (func.lower(Product.slug) == product_slug.lower())
        )
    )

    product = product_result.scalars().first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    return product


# =================== ADMIN OPERATIONS ====================

@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def add_product(
    admin: CurrentManagerOrOwner,
    new_product: NewProductRequest,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    category_result = await db.execute(
        select(Category).where((Category.id == new_product.category_id) & (Category.is_deleted.is_(False)))
    )
    if not category_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

    slug = slugify(new_product.name, allow_unicode=True)
    counter = 1
    while True:
        existing = await db.execute(select(Product).where(Product.slug == slug))
        if not existing.scalar_one_or_none():
            break
        slug = f"{slugify(new_product.name, allow_unicode=True)}-{counter}"
        counter += 1

    product = Product(
        name=new_product.name,
        slug=slug,
        category_id=new_product.category_id,
        description=new_product.description,
        is_featured=new_product.is_featured,
        is_hidden=not new_product.is_in_stock,
    )

    db.add(product)
    await db.flush()

    variants_to_add = [
        ProductVariant(
            product_id=product.id,
            label=v.label,
            price=v.price,
            compare_at_price=v.compare_at_price,
            stock_qty=v.stock_qty,
            sku=generate_sku(),
        ) for v in new_product.variants
    ]
    
    db.add_all(variants_to_add)
    await db.commit()

    stmt = (
        select(Product)
        .where(Product.id == product.id)
        .options(
            selectinload(Product.category),
            selectinload(Product.variants).selectinload(ProductVariant.offers)
        )
    )
    return await db.scalar(stmt)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: int,
    admin: CurrentManagerOrOwner,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(
        select(Product).where((Product.id == product_id) & Product.is_deleted.is_(False))
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    # soft delete product
    product.is_deleted = True
    product.is_hidden = True
    await db.commit()
    return None