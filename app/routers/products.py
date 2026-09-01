from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from slugify import slugify
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload, with_loader_criteria

from app.core.deps import CurrentManagerOrOwner, get_db
from app.db.database import AsyncSession
from app.models.category import Category, Offer, Product, ProductVariant
from app.schemas.products import NewProductRequest, NewProductVariantRequest, ProductResponse, ProductVariantResponse, UpdateProductRequest, UpdateProductVariantRequest
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








@router.patch("/{product_id}", response_model=ProductResponse, status_code=status.HTTP_200_OK)
async def update_product(
    product_id: int,
    product_update: UpdateProductRequest,
    admin: CurrentManagerOrOwner,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    # check existance of product and check if it's not soft-deleted
    stmt = (
        select(Product)
        .where((Product.id == product_id) & (Product.is_deleted.is_(False)))
        .options(
            selectinload(Product.category),
            selectinload(Product.variants).selectinload(ProductVariant.offers)
        )
    )
    result = await db.execute(stmt)
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    update_data = product_update.model_dump(exclude_unset=True)

    # check existance of category
    if "category_id" in update_data and update_data["category_id"] != product.category_id:
        category_result = await db.execute(
            select(Category).where(
                (Category.id == update_data["category_id"]) & (Category.is_deleted.is_(False))
            )
        )
        if not category_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Target category not found or is deleted"
            )

    # slug generation if name changes
    if "name" in update_data and update_data["name"] != product.name:
        new_slug = slugify(update_data["name"], allow_unicode=True)
        slug = new_slug
        counter = 1

        while True:
            existing = await db.execute(
                select(Product).where(
                    (Product.slug == slug) & (Product.id != product_id)
                )
            )
            if not existing.scalar_one_or_none():
                break
            slug = f"{new_slug}-{counter}"
            counter += 1

        product.slug = slug


    for field, value in update_data.items():
        setattr(product, field, value)

    await db.commit()

    # refetch the created product
    refetched_stmt = (
        select(Product)
        .where(Product.id == product_id)
        .options(
            selectinload(Product.category),
            selectinload(Product.variants).selectinload(ProductVariant.offers)
        )
    )
    refetched_product = await db.scalar(refetched_stmt)

    return refetched_product



# ============== PRODUCT VARIANTS ================

@router.post(
        "/{product_id}/variants", 
        response_model=ProductVariantResponse, 
        status_code=status.HTTP_201_CREATED
)
async def add_product_variant(
    product_id: int,
    variant_data: NewProductVariantRequest,
    admin: CurrentManagerOrOwner,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # Verify product existence
    product_stmt = select(Product).where(
        (Product.id == product_id) & (Product.is_deleted.is_(False))
    )
    product_result = await db.execute(product_stmt)
    if not product_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Create a savepoint in case commit fails due to duplicate SKU
            async with db.begin_nested():
                new_variant = ProductVariant(
                    product_id=product_id,
                    label=variant_data.label,
                    price=variant_data.price,
                    compare_at_price=variant_data.compare_at_price,
                    stock_qty=variant_data.stock_qty,
                    sku=generate_sku(),
                )
                db.add(new_variant)
                await db.flush()
            
            # If flush succeeds without IntegrityError, commit transaction
            await db.commit()
            break
        except IntegrityError:
            # Rollback to savepoint on collision
            if attempt == max_retries - 1:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Could not generate a unique SKU. Please try again."
                )

    # Re-fetch with relationship criteria
    now = datetime.now(UTC)
    stmt = (
        select(ProductVariant)
        .where(ProductVariant.id == new_variant.id)
        .options(
            selectinload(ProductVariant.offers),
            with_loader_criteria(
                Offer,
                lambda cls: cls.active.is_(True) & (cls.starts_at <= now) & (cls.ends_at >= now),
                include_aliases=True,
            ),
        )
    )
    return await db.scalar(stmt)



@router.delete(
    "/{product_id}/variants/{variant_id}",
    status_code=status.HTTP_204_NO_CONTENT
)
async def delete_product_variant(
    product_id: int,
    variant_id: int,
    admin: CurrentManagerOrOwner,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    # check product exists and is not soft-deleted
    product_stmt = select(Product).where(
        (Product.id == product_id) & (Product.is_deleted.is_(False))
    )
    product_result = await db.execute(product_stmt)
    if not product_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    # get variant belonging to this specific product
    variant_stmt = select(ProductVariant).where(
        (ProductVariant.id == variant_id) & (ProductVariant.product_id == product_id)
    )
    variant_result = await db.execute(variant_stmt)
    variant = variant_result.scalar_one_or_none()

    if not variant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product variant not found"
        )

    # prevent deleting the last remaining variant to maintain product consistency
    count_stmt = (
        select(func.count())
        .select_from(ProductVariant)
        .where(ProductVariant.product_id == product_id)
    )
    total_variants = await db.scalar(count_stmt)
    if total_variants <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete the only remaining variant of a product"
        )

    await db.delete(variant)
    await db.commit()
    return None





@router.patch(
    "/{product_id}/variants/{variant_id}",
    response_model=ProductVariantResponse,
    status_code=status.HTTP_200_OK,
)
async def update_product_variant(
    product_id: int,
    variant_id: int,
    variant_update: UpdateProductVariantRequest,
    admin: CurrentManagerOrOwner,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # check the product exists and isn't soft-deleted
    product_result = await db.execute(
        select(Product).where((Product.id == product_id) & Product.is_deleted.is_(False))
    )
    if not product_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    # get the variant linked to this product with active offers loaded
    now = datetime.now(UTC)
    stmt = (
        select(ProductVariant)
        .where((ProductVariant.id == variant_id) & (ProductVariant.product_id == product_id))
        .options(
            selectinload(ProductVariant.offers),
            with_loader_criteria(
                Offer,
                lambda cls: cls.active.is_(True) & (cls.starts_at <= now) & (cls.ends_at >= now),
                include_aliases=True,
            ),
        )
    )
    result = await db.execute(stmt)
    variant = result.scalar_one_or_none()

    if not variant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product variant not found"
        )

    # do the partial updates
    update_data = variant_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(variant, field, value)

    await db.commit()
    await db.refresh(variant)

    return variant