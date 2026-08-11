import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.database import engine
from app.models.category import (
    Category,
    Product,
    ProductVariant,
    ProductImage,
)
from app.models.identity import (
    AdminRole,
    AdminUser,
    User,
    UserTier,
)


SessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
)


CATEGORIES = [
    {
        "name": "زعفران",
        "slug": "saffron",
        "tint_color": "#FFF4CC",
        "dot_color": "#D4A017",
        "sort_order": 1,
    },
    {
        "name": "چای",
        "slug": "tea",
        "tint_color": "#E8F5E9",
        "dot_color": "#4CAF50",
        "sort_order": 2,
    },
    {
        "name": "دمنوش",
        "slug": "herbal-tea",
        "tint_color": "#E8F5E9",
        "dot_color": "#66BB6A",
        "sort_order": 3,
    },
    {
        "name": "گیاهان دارویی",
        "slug": "medicinal-herbs",
        "tint_color": "#E3F2FD",
        "dot_color": "#42A5F5",
        "sort_order": 4,
    },
]


PRODUCTS = [
    {
        "name": "زعفران نگین",
        "category_slug": "saffron",
        "description": "زعفران نگین با کیفیت ممتاز.",
        "keyword_tags": "زعفران,نگین,خالص,ممتاز",
        "is_featured": True,
        "variants": [
            {"label": "۱ گرم", "price": 450000, "stock_qty": 50, "sku": "SAF-N-1G"},
            {"label": "۲ گرم", "price": 850000, "stock_qty": 35, "sku": "SAF-N-2G"},
            {"label": "۴ گرم", "price": 1600000, "stock_qty": 20, "sku": "SAF-N-4G"},
        ],
    },
    {
        "name": "زعفران سرگل",
        "category_slug": "saffron",
        "description": "زعفران سرگل مناسب مصرف روزانه.",
        "keyword_tags": "زعفران,سرگل",
        "is_featured": True,
        "variants": [
            {"label": "۱ گرم", "price": 350000, "stock_qty": 60, "sku": "SAF-S-1G"},
            {"label": "۲ گرم", "price": 680000, "stock_qty": 40, "sku": "SAF-S-2G"},
        ],
    },
    {
        "name": "چای سبز ممتاز",
        "category_slug": "tea",
        "description": "چای سبز با عطر و طعم ملایم.",
        "keyword_tags": "چای,چای سبز",
        "is_featured": True,
        "variants": [
            {"label": "۱۰۰ گرم", "price": 180000, "stock_qty": 40, "sku": "TEA-G-100"},
            {"label": "۲۵۰ گرم", "price": 400000, "stock_qty": 25, "sku": "TEA-G-250"},
        ],
    },
    {
        "name": "چای سیاه ایرانی",
        "category_slug": "tea",
        "description": "چای سیاه ایرانی با عطر طبیعی.",
        "keyword_tags": "چای,چای سیاه,ایرانی",
        "is_featured": False,
        "variants": [
            {"label": "۲۵۰ گرم", "price": 300000, "stock_qty": 30, "sku": "TEA-B-250"},
            {"label": "۵۰۰ گرم", "price": 550000, "stock_qty": 20, "sku": "TEA-B-500"},
        ],
    },
    {
        "name": "دمنوش گل گاوزبان",
        "category_slug": "herbal-tea",
        "description": "گل گاوزبان خشک مناسب تهیه دمنوش.",
        "keyword_tags": "دمنوش,گل گاوزبان",
        "is_featured": False,
        "variants": [
            {"label": "۵۰ گرم", "price": 120000, "stock_qty": 30, "sku": "HER-B-50"},
            {"label": "۱۰۰ گرم", "price": 220000, "stock_qty": 20, "sku": "HER-B-100"},
        ],
    },
    {
        "name": "دمنوش بابونه",
        "category_slug": "herbal-tea",
        "description": "بابونه خشک با کیفیت مناسب تهیه دمنوش.",
        "keyword_tags": "دمنوش,بابونه",
        "is_featured": True,
        "variants": [
            {"label": "۵۰ گرم", "price": 100000, "stock_qty": 35, "sku": "HER-C-50"},
            {"label": "۱۰۰ گرم", "price": 190000, "stock_qty": 25, "sku": "HER-C-100"},
        ],
    },
    {
        "name": "گل محمدی خشک",
        "category_slug": "medicinal-herbs",
        "description": "گل محمدی خشک معطر.",
        "keyword_tags": "گل محمدی,گیاه دارویی",
        "is_featured": False,
        "variants": [
            {"label": "۵۰ گرم", "price": 140000, "stock_qty": 25, "sku": "HER-R-50"},
            {"label": "۱۰۰ گرم", "price": 260000, "stock_qty": 15, "sku": "HER-R-100"},
        ],
    },
    {
        "name": "نعناع خشک",
        "category_slug": "medicinal-herbs",
        "description": "نعناع خشک مناسب آشپزی و دمنوش.",
        "keyword_tags": "نعناع,گیاه دارویی",
        "is_featured": False,
        "variants": [
            {"label": "۱۰۰ گرم", "price": 90000, "stock_qty": 40, "sku": "HER-M-100"},
            {"label": "۲۵۰ گرم", "price": 200000, "stock_qty": 25, "sku": "HER-M-250"},
        ],
    },
    {
        "name": "دارچین سیلان",
        "category_slug": "medicinal-herbs",
        "description": "دارچین سیلان با عطر و کیفیت بالا.",
        "keyword_tags": "دارچین,سیلان",
        "is_featured": True,
        "variants": [
            {"label": "۱۰۰ گرم", "price": 180000, "stock_qty": 30, "sku": "HER-CIN-100"},
            {"label": "۲۵۰ گرم", "price": 400000, "stock_qty": 20, "sku": "HER-CIN-250"},
        ],
    },
    {
        "name": "هل سبز",
        "category_slug": "medicinal-herbs",
        "description": "هل سبز معطر مناسب چای و دمنوش.",
        "keyword_tags": "هل,هل سبز",
        "is_featured": True,
        "variants": [
            {"label": "۵۰ گرم", "price": 250000, "stock_qty": 20, "sku": "HER-CARD-50"},
            {"label": "۱۰۰ گرم", "price": 470000, "stock_qty": 15, "sku": "HER-CARD-100"},
        ],
    },
]


async def seed_categories(session):
    categories = {}

    for data in CATEGORIES:
        result = await session.execute(
            select(Category).where(Category.slug == data["slug"])
        )
        category = result.scalar_one_or_none()

        if category is None:
            category = Category(**data)
            session.add(category)

        categories[data["slug"]] = category

    await session.flush()

    return categories


async def seed_products(session, categories):
    for data in PRODUCTS:
        result = await session.execute(
            select(Product).where(Product.name == data["name"])
        )
        product = result.scalar_one_or_none()

        if product is not None:
            continue

        product = Product(
            name=data["name"],
            category=categories[data["category_slug"]],
            description=data["description"],
            keyword_tags=data["keyword_tags"],
            is_featured=data["is_featured"],
            is_hidden=False,
        )

        session.add(product)

        # Need the product ID for the related rows.
        await session.flush()

        for variant_data in data["variants"]:
            variant = ProductVariant(
                product_id=product.id,
                label=variant_data["label"],
                price=variant_data["price"],
                stock_qty=variant_data["stock_qty"],
                sku=variant_data["sku"],
            )

            session.add(variant)

        # Placeholder images
        session.add_all(
            [
                ProductImage(
                    product_id=product.id,
                    url=f"https://placehold.co/800x800?text={product.id}-1",
                    sort_order=1,
                ),
                ProductImage(
                    product_id=product.id,
                    url=f"https://placehold.co/800x800?text={product.id}-2",
                    sort_order=2,
                ),
            ]
        )


async def seed_admin(session):
    result = await session.execute(
        select(AdminUser).where(
            AdminUser.email == "admin@example.com"
        )
    )

    admin = result.scalar_one_or_none()

    if admin is None:
        admin = AdminUser(
            name="Owner",
            email="admin@example.com",
            # Development-only password hash placeholder.
            password_hash="CHANGE_ME",
            role=AdminRole.OWNER,
        )

        session.add(admin)


async def seed_customer(session):
    result = await session.execute(
        select(User).where(User.phone == "09120000000")
    )

    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            phone="09120000000",
            name="Test Customer",
            tier=UserTier.NEW,
            telegram_opt_in=False,
            sms_opt_in=False,
        )

        session.add(user)


async def main():
    async with SessionLocal() as session:
        try:
            categories = await seed_categories(session)
            await seed_products(session, categories)
            await seed_admin(session)
            await seed_customer(session)

            await session.commit()

            print("Seed completed successfully.")

        except Exception:
            await session.rollback()
            raise

        finally:
            await session.close()

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())