from datetime import UTC, datetime
import os
from typing import Annotated

from PIL import UnidentifiedImageError
from fastapi import (
    APIRouter, 
    Depends, 
    HTTPException, 
    Query, 
    status, 
    UploadFile
)
from fastapi.concurrency import run_in_threadpool
from pydantic import Field
from slugify import slugify
from sqlalchemy import and_, func, or_, select, update, delete as sql_delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload, with_loader_criteria

from app.core.deps import CurrentManagerOrOwner, get_db
from app.db.database import AsyncSession
from app.models.cart import CartItem
from app.models.category import Category, Offer, Product, ProductImage, ProductVariant
from app.schemas.categories import CategoryResponse
from app.schemas.products import ImageUploadResponse, NewProductRequest, NewProductVariantRequest, PaginatedProductResponse, ProductResponse, ProductVariantResponse, UpdateProductImageRequest, UpdateProductRequest, UpdateProductVariantRequest
from app.utils.image_utils import process_product_image
from app.utils.product_utils import generate_sku
from app.core.config import settings


router = APIRouter(prefix="/products", tags=["products"])


# ============= CATEGORY IMAGE UPLOAD ===================
@router.post("/{category_id}/image", response_model=CategoryResponse)
async def upload_category_image(
    category_id: int,
    file: UploadFile,
    admin: CurrentManagerOrOwner,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    # check if category exists
    category = await db.get(Category, category_id)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="category not found"
        )

    image = await file.read()

    # check image size
    max_image_size = settings.MAX_IMAGE_SIZE_MEGA_BYTE * 1024 * 1024
    if len(image) > max_image_size:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Image size is larger than limit: {settings.MAX_IMAGE_SIZE_MEGA_BYTE}MB"
        )

    if not image:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is empty"
        )

    # check image format and process file
    try:
        new_filename = await run_in_threadpool(process_product_image, image)
    except UnidentifiedImageError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image file. Please upload a valid image (JPEG, PNG, GIF, WebP).",
        ) from err

    # Remove old physical file if replacing an existing image
    if category.image_url and os.path.exists(category.image_url):
        os.remove(category.image_url)

    # Update category image_url attribute directly
    category.image_url = new_filename

    db.add(category)
    await db.commit()
    await db.refresh(category)

    return category


@router.delete("/{category_id}/image", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category_image(
    category_id: int,
    admin: CurrentManagerOrOwner,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    category = await db.get(Category, category_id)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="category not found"
        )

    if not category.image_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="category image not found"
        )

    old_image_path = category.image_url

    # Clear image path on the category
    category.image_url = None
    db.add(category)
    await db.commit()

    # Remove file from disk after successful DB commit
    if os.path.exists(old_image_path):
        os.remove(old_image_path)

    return None

# =================================================================

# ============ PRODUCTS =====================

@router.get("", response_model=PaginatedProductResponse)
async def get_all_products(
    db: Annotated[AsyncSession, Depends(get_db)],
    search: Annotated[
        str | None,
        Query(
            min_length=1,
            max_length=100,
            description="Search products by name or description",
        ),
    ] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1)] = 25
):
    now = datetime.now(UTC)

    conditions = [Product.is_hidden.is_(False), Product.is_deleted.is_(False)]

    if search is not None:
        term = search.strip()
        if term:
            # escape user-supplied LIKE wildcards so they're matched literally
            escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped}%"
            conditions.append(
                or_(
                    Product.name.ilike(pattern, escape="\\"),
                    Product.description.ilike(pattern, escape="\\"),
                )
            )

    result = await db.execute(
        select(Product)
        .options(
            selectinload(Product.category),
            selectinload(Product.images),
            selectinload(Product.variants).selectinload(ProductVariant.offers),
            with_loader_criteria(
                Offer,
                lambda cls: cls.active.is_(True) & (cls.starts_at <= now) & (cls.ends_at >= now),
                include_aliases=True
            ),
            with_loader_criteria(
                ProductVariant,
                lambda cls: cls.is_deleted.is_(False),
                include_aliases=True,
            ),
        )
        .where(and_(*conditions))
        .offset(offset)
        .limit(limit)
        .order_by(Product.updated_at.desc())
    )

    total_products_req = await db.execute(select(func.count()).select_from(Product).where(and_(*conditions)))


    total_products = total_products_req.scalar() or 0

    has_more = offset + limit < total_products

    products = result.scalars().all()

    print(products)

    return PaginatedProductResponse(
        products=[ProductResponse.model_validate(product) for product in products],
        has_more=has_more,
        offset=offset,
        limit=limit
    )


@router.get("/{product_slug}", response_model=ProductResponse, status_code=status.HTTP_200_OK)
async def show_product_details(product_slug: str, db: Annotated[AsyncSession, Depends(get_db)]):
    now = datetime.now(UTC)
    product_result = await db.execute(
        select(Product)
        .options(
            selectinload(Product.category),
            selectinload(Product.images),
            selectinload(Product.variants).selectinload(ProductVariant.offers),
            with_loader_criteria(
                Offer,
                lambda cls: cls.active.is_(True) & (cls.starts_at <= now) & (cls.ends_at >= now),
                include_aliases=True
            ),
            with_loader_criteria(
                ProductVariant,
                lambda cls: cls.is_deleted.is_(False),
                include_aliases=True,
            ),
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
            selectinload(Product.images),
            selectinload(Product.variants).selectinload(ProductVariant.offers),
            with_loader_criteria(
                ProductVariant,
                lambda cls: cls.is_deleted.is_(False),
                include_aliases=True,
            ),
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
        select(Product)
        .options(selectinload(Product.variants))
        .where((Product.id == product_id) & Product.is_deleted.is_(False))
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    # soft delete product
    product.is_deleted = True
    product.is_hidden = True

    # TODO: delete all cart items with this product
    variants = product.variants
    for variant in variants:
        await db.execute(sql_delete(CartItem).where(CartItem.product_variant_id == variant.id))
    # TODO: soft-delete all product variants of this product
    await db.execute(update(ProductVariant).where(ProductVariant.product_id == product_id).values(is_deleted=True))

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
            selectinload(Product.images),
            selectinload(Product.variants).selectinload(ProductVariant.offers),
            with_loader_criteria(
                ProductVariant,
                lambda cls: cls.is_deleted.is_(False),
                include_aliases=True,
            ),
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

    # get variant belonging to this specific product (and not already removed)
    variant_stmt = select(ProductVariant).where(
        (ProductVariant.id == variant_id)
        & (ProductVariant.product_id == product_id)
        & (ProductVariant.is_deleted.is_(False))
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
        .where(
            (ProductVariant.product_id == product_id)
            & (ProductVariant.is_deleted.is_(False))
        )
    )
    total_variants = await db.scalar(count_stmt)
    if total_variants <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete the only remaining variant of a product"
        )

    # Soft delete: a hard delete here would either violate the FK from
    # cart_items (no cascade defined) or, for order_items, get nullified by
    # the ORM's default relationship handling and violate its NOT NULL
    # constraint. Orders keep their own name/price snapshot, so they don't
    # need the row to keep existing.
    variant.is_deleted = True
    await db.execute(sql_delete(CartItem).where(CartItem.product_variant_id == variant.id))

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
        .where(
            (ProductVariant.id == variant_id)
            & (ProductVariant.product_id == product_id)
            & (ProductVariant.is_deleted.is_(False))
        )
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