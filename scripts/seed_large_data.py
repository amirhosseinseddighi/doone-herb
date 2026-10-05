import asyncio
from datetime import UTC, datetime, time, timedelta
import random
import time as time_lib
import uuid

from faker import Faker
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.database import engine
from app.models.admin import (
    ActivityKind,
    ActivityLog,
    AdminNotification,
    AdminNotificationKind,
    CampaignAudienceType,
    Purchase,
    PushCampaign,
    PushCampaignRecipient,
)
from app.models.cart import (
    Cart,
    CartItem,
)
from app.models.category import (
    Category,
    Offer,
    Product,
    ProductImage,
    ProductVariant,
    Review,
)
from app.models.identity import (
    Address,
    Roles,
    User,
    UserTier,
)
from app.models.order import (
    DeliverySlot,
    DeliverySlotKind,
    FulfillmentMethod,
    Order,
    OrderItem,
    OrderStatus,
    OrderStatusEvent,
    OrderStatusEventActor,
    Payment,
    PaymentMethod,
    PaymentProvider,
    PaymentStatus,
)
from app.models.general import ShopSettings

# راه‌اندازی Faker برای زبان فارسی و انگلیسی
fake_fa = Faker("fa_IR")
fake_en = Faker("en_US")

NUM_EXTRA_USERS = 10_000
NUM_CATEGORIES = 5_000
NUM_PRODUCTS = 100_000
NUM_ORDERS = 1_000_000

BATCH_SIZE = 20_000  # اندازه Batch جهت مدیریت بهینه RAM

SessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
)

SHOP_SETTINGS = [
    {"key": "shop_name", "value": "دونه هرب"},
    {"key": "footer_label", "value": "پلاک ۴۲، رویِ بازارِ سبزیجات"},
    {
        "key": "footer_description",
        "value": "خیابان ولی‌عصر، تهران · شنبه تا پنجشنبه، ۹:۰۰ تا ۲۰:۰۰ · ۰۲۱ ۸۸۴۲ ۱۱۹۰",
    },
    {
        "key": "address",
        "value": "تهران، خیابان ولیعصر، ردیف بازار گیاهان، پلاک ۴۲",
    },
    {"key": "support_number", "value": "021 8842 1190"},
    {"key": "tehran_fee", "value": "45000"},
    {"key": "free_send_threshold", "value": "900000"},
    {"key": "last_send_hour", "value": "14:00"},
]

DELIVERY_SLOTS = [
    {
        "label": "تحویل همان روز (عصر)",
        "note": "سفارش‌های ثبت شده قبل از ساعت ۱۴",
        "fee": 50000,
        "kind": DeliverySlotKind.SAME_DAY,
        "cutoff_time": time(14, 0),
        "active": True,
    },
    {
        "label": "تحویل فردا صبح",
        "note": "ارسال بین ساعت ۹ تا ۱۲ صبح",
        "fee": 35000,
        "kind": DeliverySlotKind.NEXT_MORNING,
        "cutoff_time": time(20, 0),
        "active": True,
    },
    {
        "label": "تحویل حضوری",
        "note": "مراجعه حضوری به فروشگاه مرکزی",
        "fee": 0,
        "kind": DeliverySlotKind.PICKUP,
        "cutoff_time": time(18, 0),
        "active": True,
    },
]


async def seed_admin(session) -> User:
    result = await session.execute(
        select(User).where(User.phone == "09129999999")
    )
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            phone="09129999999",
            name="Test Admin",
            email="admin@gmail.com",
            tier=UserTier.NEW,
            role=Roles.OWNER,
            password_hash="$argon2id$v=19$m=65536,t=3,p=4$qznbi/jmFhYeZQ8JGBUoEw$3JK+GUlEpdnoMI//jTPSumK/vqBe1pFVw7pHCfG8hWk",
            telegram_opt_in=False,
            sms_opt_in=False,
        )
        session.add(user)
        await session.flush()

    return user


async def seed_customer(session) -> User:
    result = await session.execute(
        select(User).where(User.phone == "09120000000")
    )
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            phone="09120000000",
            name="Test Customer",
            email="customer@gmail.com",
            tier=UserTier.NEW,
            role=Roles.CUSTOMER,
            password_hash="$argon2id$v=19$m=65536,t=3,p=4$qbCOQ0JAn7ob7d86L/7jzw$iCKbdv7YMBS43Cy42UV+IMvZsnTeJNHnqAeX1sENvsA",
            telegram_opt_in=False,
            sms_opt_in=False,
        )
        session.add(user)
        await session.flush()

    return user


async def seed_address(session, user: User) -> Address:
    result = await session.execute(
        select(Address).where(Address.user_id == user.id)
    )
    address = result.scalar_one_or_none()

    if address is None:
        address = Address(
            user_id=user.id,
            label="خانه",
            line="تهران، خیابان ولیعصر، نرسیده به میدان ونک، پلاک ۱",
            unit="واحد ۴",
            postal_code="1234567890",
            phone="09120000000",
            lat=35.7575,
            lng=51.4100,
            is_default=True,
        )
        session.add(address)
        await session.flush()

    return address


async def seed_delivery_slots(session) -> list[DeliverySlot]:
    slots = []
    for data in DELIVERY_SLOTS:
        result = await session.execute(
            select(DeliverySlot).where(DeliverySlot.label == data["label"])
        )
        slot = result.scalar_one_or_none()

        if slot is None:
            slot = DeliverySlot(**data)
            session.add(slot)

        slots.append(slot)

    await session.flush()
    return slots


async def seed_shop_settings(session) -> list[ShopSettings]:
    settings = []
    for data in SHOP_SETTINGS:
        result = await session.execute(
            select(ShopSettings).where(ShopSettings.key == data["key"])
        )
        setting = result.scalar_one_or_none()

        if setting is None:
            setting = ShopSettings(key=data["key"], value=data["value"])
            session.add(setting)
        else:
            setting.value = data["value"]

        settings.append(setting)

    await session.flush()
    return settings


# ==========================================
# توابع درج انبوه داده با Faker
# ==========================================

async def seed_bulk_users(session) -> list[int]:
    print(f"Generating {NUM_EXTRA_USERS:,} Extra Users with Faker...")
    users_batch = []
    now = datetime.now(UTC)
    dummy_pwd = "$argon2id$v=19$m=65536,t=3,p=4$qbCOQ0JAn7ob7d86L/7jzw$iCKbdv7YMBS43Cy42UV+IMvZsnTeJNHnqAeX1sENvsA"

    for i in range(1, NUM_EXTRA_USERS + 1):
        # ساخت شماره موبایل یکتا با استفاده از فرمت‌دهی اندیس i
        unique_phone = f"09{100000000 + i}"

        users_batch.append({
            "phone": unique_phone,
            "name": fake_fa.name(),
            "email": f"{fake_en.user_name()}_{i}@example.com",
            "tier": random.choice(list(UserTier)),
            "role": Roles.CUSTOMER,
            "password_hash": dummy_pwd,
            "telegram_opt_in": random.choice([True, False]),
            "sms_opt_in": random.choice([True, False]),
            "created_at": now,
            "last_seen_at": now,
        })

        if len(users_batch) >= BATCH_SIZE:
            await session.execute(insert(User), users_batch)
            users_batch.clear()

    if users_batch:
        await session.execute(insert(User), users_batch)

    await session.flush()
    
    user_ids = (await session.execute(select(User.id))).scalars().all()
    print("Extra Users inserted successfully.")
    return user_ids


async def seed_bulk_categories(session) -> list[int]:
    print(f"Generating {NUM_CATEGORIES:,} Categories with Faker...")
    cat_batch = []
    
    # نمونه کلمات مناسب برای دسته‌بندی گیاهی/دارویی
    category_prefixes = ["عصاره", "دمنوش", "روغن", "گیاه خشک", "بذر", "عرقیات", "ادویه", "صمغ"]

    for i in range(1, NUM_CATEGORIES + 1):
        cat_name = f"{random.choice(category_prefixes)} {fake_fa.word()} {i}"
        cat_batch.append({
            "name": cat_name,
            "slug": f"cat-{fake_en.slug()}-{i}",
            "tint_color": fake_en.hex_color(),
            "dot_color": fake_en.hex_color(),
            "sort_order": i,
            "is_active": True,
            "is_deleted": False,
            "image_url": fake_en.image_url(width=200, height=200),
        })

        if len(cat_batch) >= BATCH_SIZE:
            await session.execute(insert(Category), cat_batch)
            cat_batch.clear()

    if cat_batch:
        await session.execute(insert(Category), cat_batch)

    await session.flush()
    
    category_ids = (await session.execute(select(Category.id))).scalars().all()
    print("Categories inserted successfully.")
    return category_ids


async def seed_bulk_products(session, category_ids: list[int]) -> list[tuple[int, int, int, str]]:
    print(f"Generating {NUM_PRODUCTS:,} Products with Variants and Images...")
    now = datetime.now(UTC)
    products_batch = []
    pv_tuples = []  # ذخیره (product_id, variant_id, price, product_name)

    herb_names = ["نعناع", "بابونه", "آویشن", "اسطوخودوس", "کاسنی", "شاه‌تره", "گل‌گاوزبان", "زنجبیل", "دارچین", "مریم‌گلی"]
    packaging_labels = ["بسته‌بندی ۵۰ گرمی", "بسته‌بندی ۱۰۰ گرمی", "بسته‌بندی ۲۵۰ گرمی", "پاکت ۱ کیلویی", "شیشه ۱۰۰ سی‌سی"]

    for i in range(1, NUM_PRODUCTS + 1):
        p_name = f"{random.choice(herb_names)} {fake_fa.word()} کد {i}"
        products_batch.append({
            "name": p_name,
            "slug": f"prod-{fake_en.slug()}-{i}",
            "category_id": random.choice(category_ids),
            "description": fake_fa.paragraph(nb_sentences=3),
            "keyword_tags": f"{fake_fa.word()},{fake_fa.word()},گیاهی",
            "is_featured": (i % 15 == 0),
            "is_hidden": False,
            "is_deleted": False,
            "created_at": now,
            "updated_at": now,
        })

        if len(products_batch) >= BATCH_SIZE:
            stmt = insert(Product).returning(Product.id, Product.name)
            res = await session.execute(stmt, products_batch)
            created_prods = res.all()

            variants_batch = []
            images_batch = []

            for prod_id, prod_name in created_prods:
                price = random.randint(20, 800) * 5_000
                variants_batch.append({
                    "product_id": prod_id,
                    "label": random.choice(packaging_labels),
                    "price": price,
                    "stock_qty": random.randint(10, 500),
                    "sku": f"SKU-{fake_en.bothify(text='??-####')}-{prod_id}",
                    "is_deleted": False,
                })
                images_batch.append({
                    "product_id": prod_id,
                    "url": fake_en.image_url(width=600, height=600),
                    "sort_order": 0,
                })

            stmt_v = insert(ProductVariant).returning(ProductVariant.id, ProductVariant.product_id, ProductVariant.price)
            res_v = await session.execute(stmt_v, variants_batch)
            
            # ذخیره کردن نام محصول همگام با variant_id
            prod_name_map = {p_id: p_name for p_id, p_name in created_prods}
            for v_id, p_id, v_price in res_v.all():
                pv_tuples.append((p_id, v_id, v_price, prod_name_map[p_id]))

            await session.execute(insert(ProductImage), images_batch)
            await session.commit()
            products_batch.clear()

    if products_batch:
        stmt = insert(Product).returning(Product.id, Product.name)
        res = await session.execute(stmt, products_batch)
        created_prods = res.all()

        variants_batch = []
        images_batch = []

        prod_name_map = {p_id: p_name for p_id, p_name in created_prods}

        for prod_id, prod_name in created_prods:
            price = random.randint(20, 800) * 5_000
            variants_batch.append({
                "product_id": prod_id,
                "label": random.choice(packaging_labels),
                "price": price,
                "stock_qty": random.randint(10, 500),
                "sku": f"SKU-{fake_en.bothify(text='??-####')}-{prod_id}",
                "is_deleted": False,
            })
            images_batch.append({
                "product_id": prod_id,
                "url": fake_en.image_url(width=600, height=600),
                "sort_order": 0,
            })

        stmt_v = insert(ProductVariant).returning(ProductVariant.id, ProductVariant.product_id, ProductVariant.price)
        res_v = await session.execute(stmt_v, variants_batch)
        for v_id, p_id, v_price in res_v.all():
            pv_tuples.append((p_id, v_id, v_price, prod_name_map[p_id]))

        await session.execute(insert(ProductImage), images_batch)
        await session.commit()

    print("Products inserted successfully.")
    return pv_tuples


async def seed_bulk_orders(
    session,
    user_ids: list[int],
    delivery_slot_ids: list[int],
    pv_tuples: list[tuple[int, int, int, str]],
):
    print(f"Generating {NUM_ORDERS:,} Orders with Items and Payments using Faker...")
    statuses = list(OrderStatus)
    methods = list(FulfillmentMethod)
    pay_methods = list(PaymentMethod)
    pay_providers = list(PaymentProvider)
    pay_statuses = list(PaymentStatus)

    start_date = datetime.now(UTC) - timedelta(days=365)
    orders_batch = []

    for i in range(1, NUM_ORDERS + 1):
        selected_pv = random.choice(pv_tuples)
        prod_id, variant_id, unit_price, prod_name = selected_pv
        qty = random.randint(1, 4)
        line_total = unit_price * qty
        delivery_fee = random.choice([0, 35000, 50000])
        subtotal = line_total
        discount = 0
        total = subtotal + delivery_fee - discount
        
        placed_at = start_date + timedelta(seconds=random.randint(0, 365 * 86400))

        orders_batch.append({
            "order_no": f"ORD-{fake_en.bothify(text='#####')}-{i}",
            "user_id": random.choice(user_ids),
            "status": random.choice(statuses),
            "fulfillment_method": random.choice(methods),
            "delivery_slot_id": random.choice(delivery_slot_ids) if delivery_slot_ids else None,
            "subtotal": subtotal,
            "delivery_fee": delivery_fee,
            "discount": discount,
            "total": total,
            "payment_method": random.choice(pay_methods),
            "payment_status": random.choice(pay_statuses),
            "placed_at": placed_at,
            "updated_at": placed_at,
            
            # فیلدهای موقت جهت ساخت OrderItem و Payment
            "_tmp_variant_id": variant_id,
            "_tmp_product_id": prod_id,
            "_tmp_prod_name": prod_name,
            "_tmp_qty": qty,
            "_tmp_unit_price": unit_price,
            "_tmp_line_total": line_total,
        })

        if len(orders_batch) >= BATCH_SIZE:
            clean_orders = [
                {k: v for k, v in o.items() if not k.startswith("_tmp_")}
                for o in orders_batch
            ]
            
            stmt = insert(Order).returning(Order.id, Order.total, Order.placed_at)
            res = await session.execute(stmt, clean_orders)
            created_orders = res.all()

            order_items_batch = []
            payments_batch = []

            for idx, (order_id, order_total, o_placed_at) in enumerate(created_orders):
                orig_item = orders_batch[idx]

                order_items_batch.append({
                    "order_id": order_id,
                    "product_id": orig_item["_tmp_product_id"],
                    "product_variant_id": orig_item["_tmp_variant_id"],
                    "name_snapshot": orig_item["_tmp_prod_name"],
                    "size_label_snapshot": "بسته‌بندی اصلی",
                    "unit_price_snapshot": orig_item["_tmp_unit_price"],
                    "qty": orig_item["_tmp_qty"],
                    "line_total": orig_item["_tmp_line_total"],
                })

                payments_batch.append({
                    "order_id": order_id,
                    "amount": order_total,
                    "provider": random.choice(pay_providers),
                    "provider_ref": f"REF-{fake_en.hexify(text='^^^^^^^^^^^^').upper()}",
                    "status": orig_item["payment_status"],
                    "created_at": o_placed_at,
                })

            await session.execute(insert(OrderItem), order_items_batch)
            await session.execute(insert(Payment), payments_batch)

            await session.commit()
            orders_batch.clear()
            print(f"  Progress: {i:,} / {NUM_ORDERS:,} Orders created.")

    print("1 Million Orders, Items, and Payments inserted successfully.")


async def main():
    start_t = time_lib.time()
    async with SessionLocal() as session:
        try:
            # ۱. دیتای پایه سیستم
            admin = await seed_admin(session)
            user = await seed_customer(session)

            address = await seed_address(session, user)
            delivery_slots = await seed_delivery_slots(session)
            shop_settings = await seed_shop_settings(session)

            await session.commit()
            print("Base Seed completed successfully.")

            # ۲. دیتای حجیم و تست Benchmarking با Faker
            user_ids = await seed_bulk_users(session)
            category_ids = await seed_bulk_categories(session)
            pv_tuples = await seed_bulk_products(session, category_ids)

            slot_ids = [slot.id for slot in delivery_slots]
            
            # ۳. درج ۱ میلیون سفارش
            await seed_bulk_orders(session, user_ids, slot_ids, pv_tuples)

            print(f"\n🚀 ALL SEEDING FINISHED IN {time_lib.time() - start_t:.2f} SECONDS!")

        except Exception:
            await session.rollback()
            raise

        finally:
            await session.close()

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())