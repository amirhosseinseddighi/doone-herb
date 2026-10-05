from app.core.deps import AsyncSession
from sqlalchemy import select
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
    User,
    UserTier,
)
from app.models.cart import (
    Cart,
    CartItem,
)

from app.models.general import ShopSettings

MODELS = {
    ActivityKind,
    ActivityLog,
    AdminNotification,
    AdminNotificationKind,
    CampaignAudienceType,
    Purchase,
    PushCampaign,
    PushCampaignRecipient,
    Category,
    Offer,
    Product,
    ProductImage,
    ProductVariant,
    Review,
    Address,
    Roles,
    User,
    UserTier,
    Cart,
    CartItem,
    ShopSettings
}

async def export_database(db: AsyncSession):
    for model in MODELS:
        result = await db.execute(select(model))
        all_results = result.scalars().all()
        print(all_results)