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
    Roles,
    User,
    UserTier,
)
from app.models.cart import (
    Cart,
    CartItem,
)
from app.models.order import DeliverySlot, DeliverySlotKind, FulfillmentMethod, Order, OrderItem, OrderStatus, OrderStatusEvent, OrderStatusEventActor, Payment, PaymentMethod, PaymentProvider, PaymentStatus


SessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
)


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

async def main():
    async with SessionLocal() as session:
        try:
            admin = await seed_admin(session)
            user = await seed_customer(session)

            address = await seed_address(session, user)
            delivery_slots = await seed_delivery_slots(session)
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