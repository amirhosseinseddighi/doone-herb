import asyncio
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select
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
    OTPCode,
    Roles,
    User,
    UserTier,
)
from app.models.order import (
    Cart,
    CartItem,
    CourierType,
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
        "sort_order": 0,
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
        "slug": "زعفران-نگین",
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
        "slug": "زعفران-سرگل",
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
        "slug": "چای-سبز-ممتاز",
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
        "slug": "چای-سیاه-ایرانی",
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
        "slug": "دمنوش-گل-گاوزبان",
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
        "slug": "دمنوش-بابونه",
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
        "slug": "گل-محمدی-خشک",
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
        "slug": "نعناع-خشک",
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
        "slug": "دارچین-سیلان",
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
        "slug": "هل-سبز",
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
            slug = data["slug"],
            category=categories[data["category_slug"]],
            description=data["description"],
            keyword_tags=data["keyword_tags"],
            is_featured=data["is_featured"],
            is_hidden=False,
        )

        session.add(product)
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


async def seed_offers(session):
    variant_res = await session.execute(
        select(ProductVariant).where(ProductVariant.sku == "SAF-N-1G")
    )
    variant = variant_res.scalar_one_or_none()

    if variant is None:
        return None

    result = await session.execute(
        select(Offer).where(Offer.product_variant_id == variant.id)
    )
    offer = result.scalar_one_or_none()

    if offer is None:
        now = datetime.now(UTC)
        offer = Offer(
            product_variant_id=variant.id,
            badge_label="پیشنهاد ویژه",
            starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=7),
            active=True,
        )
        session.add(offer)
        await session.flush()

    return offer



async def seed_admin(session) -> User:
    result = await session.execute(
        select(User).where(User.phone == "09129999999")
    )
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            phone="09129999999",
            name="Test Admin",
            tier=UserTier.NEW,
            role=Roles.OWNER,
            password_hash="$argon2id$v=19$m=65536,t=3,p=4$qbCOQ0JAn7ob7d86L/7jzw$iCKbdv7YMBS43Cy42UV+IMvZsnTeJNHnqAeX1sENvsA",
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
            tier=UserTier.NEW,
            role=Roles.CUSTOMER,
            password_hash="$argon2id$v=19$m=65536,t=3,p=4$qbCOQ0JAn7ob7d86L/7jzw$iCKbdv7YMBS43Cy42UV+IMvZsnTeJNHnqAeX1sENvsA",
            telegram_opt_in=False,
            sms_opt_in=False,
        )
        session.add(user)
        await session.flush()

    return user


async def seed_otp_codes(session):
    result = await session.execute(
        select(OTPCode).where(OTPCode.phone == "09120000000")
    )
    otp = result.scalar_one_or_none()

    if otp is None:
        now = datetime.now(UTC)
        otp = OTPCode(
            phone="09120000000",
            code="12345",
            expires_at=now + timedelta(minutes=2),
            consumed_at=now,
            attempts=1,
        )
        session.add(otp)


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


async def seed_cart(session, user: User):
    result = await session.execute(
        select(Cart).where(Cart.user_id == user.id)
    )
    cart = result.scalar_one_or_none()

    if cart is None:
        cart = Cart(
            user_id=user.id,
            session_id="sess_test_customer_001",
        )
        session.add(cart)
        await session.flush()

        variant_res = await session.execute(
            select(ProductVariant).where(ProductVariant.sku == "TEA-G-100")
        )
        variant = variant_res.scalar_one()

        cart_item = CartItem(
            cart_id=cart.id,
            product_variant_id=variant.id,
            qty=2,
        )
        session.add(cart_item)


async def seed_orders(session, user: User, address: Address, delivery_slot: DeliverySlot) -> Order:
    result = await session.execute(
        select(Order).where(Order.order_no == "ORD-20260818-001")
    )
    order = result.scalar_one_or_none()

    if order is not None:
        return order

    product_res = await session.execute(
        select(Product).where(Product.name == "زعفران نگین")
    )
    product = product_res.scalar_one()

    variant_res = await session.execute(
        select(ProductVariant).where(ProductVariant.sku == "SAF-N-1G")
    )
    variant = variant_res.scalar_one()

    now = datetime.now(UTC)

    # 1. Create Sample Order
    order = Order(
        order_no="ORD-20260818-001",
        user_id=user.id,
        address_id=address.id,
        delivery_slot_id=delivery_slot.id,
        status=OrderStatus.NEW,
        fulfillment_method=FulfillmentMethod.COURIER,
        courier=CourierType.IN_HOUSE_RIDER,
        subtotal=450000,
        delivery_fee=delivery_slot.fee,
        discount=0,
        total=450000 + delivery_slot.fee,
        payment_method=PaymentMethod.ONLINE,
        payment_status=PaymentStatus.PAID,
        note="لطفا قبل از ارسال تماس بگیرید.",
        placed_at=now,
        updated_at=now,
    )
    session.add(order)
    await session.flush()

    # 2. Add Order Item
    order_item = OrderItem(
        order_id=order.id,
        product_id=product.id,
        product_variant_id=variant.id,
        name_snapshot=product.name,
        size_label_snapshot=variant.label,
        unit_price_snapshot=variant.price,
        qty=1,
        line_total=variant.price * 1,
    )
    session.add(order_item)

    # 3. Add Initial Status Event
    status_event = OrderStatusEvent(
        order_id=order.id,
        status=OrderStatus.NEW,
        note="سفارش با موفقیت ثبت شد.",
        actor=OrderStatusEventActor.SYSTEM,
        created_at=now,
    )
    session.add(status_event)

    # 4. Add Payment record
    payment = Payment(
        order_id=order.id,
        provider=PaymentProvider.CASH,
        provider_ref="REF-20260818-001",
        amount=order.total,
        status=PaymentStatus.PAID,
        raw_payload={"gateway": "mock", "transaction_id": "TXN_123456"},
        created_at=now,
    )
    session.add(payment)

    return order


async def seed_reviews(session, user: User, order: Order):
    product_res = await session.execute(
        select(Product).where(Product.name == "زعفران نگین")
    )
    product = product_res.scalar_one()

    result = await session.execute(
        select(Review).where(Review.order_id == order.id)
    )
    review = result.scalar_one_or_none()

    if review is None:
        review = Review(
            product_id=product.id,
            user_id=user.id,
            order_id=order.id,
            stars=5,
            text="کیفیت عالی و بسته‌بندی بسیار خوب بود.",
            admin_reply="با تشکر از دیدگاه شما!",
        )
        session.add(review)


async def seed_admin_notifications(session, order: Order):
    result = await session.execute(
        select(AdminNotification).where(AdminNotification.order_id == order.id)
    )
    notification = result.scalar_one_or_none()

    if notification is None:
        notification = AdminNotification(
            kind=AdminNotificationKind.ORDER,
            title="سفارش جدید ثبت شد",
            body=f"سفارش شماره {order.order_no} ثبت شد.",
            order_id=order.id,
        )
        session.add(notification)


async def seed_push_campaigns(session, user: User):
    result = await session.execute(
        select(PushCampaign).where(PushCampaign.text == "تخفیف ویژه محصولات زعفران")
    )
    campaign = result.scalar_one_or_none()

    if campaign is None:
        now = datetime.now(UTC)
        campaign = PushCampaign(
            text="تخفیف ویژه محصولات زعفران",
            audience_type=CampaignAudienceType.ALL,
            sent_at=now,
            recipient_count=1,
        )
        session.add(campaign)
        await session.flush()

        recipient = PushCampaignRecipient(
            user_id=user.id,
            campaign_id=campaign.id,
        )
        session.add(recipient)


async def seed_activity_logs(session, admin: User):
    result = await session.execute(
        select(ActivityLog).where(ActivityLog.text == "تنظیمات پایگاه داده مقداردهی اولیه شد.")
    )
    log = result.scalar_one_or_none()

    if log is None:
        log = ActivityLog(
            actor_id=admin.id,
            actor_label=admin.name,
            kind=ActivityKind.USER,
            text="تنظیمات پایگاه داده مقداردهی اولیه شد.",
        )
        session.add(log)


async def seed_purchases(session):
    result = await session.execute(
        select(Purchase).where(Purchase.title == "خرید عمده زعفران نگین")
    )
    purchase = result.scalar_one_or_none()

    if purchase is None:
        purchase = Purchase(
            title="خرید عمده زعفران نگین",
            note="خرید مستقیم از کشاورزان خراسان",
            amount=50000000,
            purchase_date=date(2026, 8, 15),
        )
        session.add(purchase)


async def main():
    async with SessionLocal() as session:
        try:
            categories = await seed_categories(session)
            await seed_products(session, categories)
            await seed_offers(session)

            admin = await seed_admin(session)
            user = await seed_customer(session)
            await seed_otp_codes(session)

            address = await seed_address(session, user)
            delivery_slots = await seed_delivery_slots(session)

            await seed_cart(session, user)

            order = await seed_orders(session, user, address, delivery_slots[0])
            await seed_reviews(session, user, order)

            await seed_admin_notifications(session, order)
            await seed_push_campaigns(session, user)
            await seed_activity_logs(session, admin)
            await seed_purchases(session)

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