from datetime import UTC, date, datetime
from typing import Optional

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, UniqueConstraint,String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Enum as SQLEnum
from app.models.identity import UserTier
from app.db.database import Base
import enum


class AdminNotificationKind(str, enum.Enum):
    ORDER = 'order'
    STOCK = 'stock'
    OFFER = 'offer'
    MESSAGE = 'message'


class CampaignAudienceType(str, enum.Enum):
    """
        Campaign Audience Type which extends `UserTier` enum in  `app.models.identity`
    """
    ALL = 'all'
    GOLD = 'gold'
    SILVER = 'silver'
    NEW = 'new'
    RISK = 'risk'
    CUSTOM = 'custom'


class ActivityKind(str, enum.Enum):
    ORDER = 'order'
    STOCK = 'stock'
    PRICE = 'price'
    USER = 'user'
    OFFER = 'offer'




class AdminNotification(Base):
    __tablename__="admin_notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[AdminNotificationKind] = mapped_column(
        SQLEnum(
            AdminNotificationKind,
            name="notification_kind_enum",
            values_callable=lambda x:[e.value for e in x]
        ), 
        nullable=False, 
        index=True
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)


    order_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), 
        nullable=True
    )
    product_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), 
        nullable=True
    )
    product_variant_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("product_variants.id", ondelete="SET NULL"), 
        nullable=True
    )
    offer_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("offers.id", ondelete="SET NULL"), 
        nullable=True
    )


    product: Mapped[Optional["Product"]] = relationship(foreign_keys=[product_id])
    product_variant: Mapped[Optional["ProductVariant"]] = relationship(foreign_keys=[product_variant_id])
    order: Mapped[Optional["Order"]] = relationship(foreign_keys=[order_id])
    offer: Mapped[Optional["Offer"]] = relationship(foreign_keys=[offer_id])

    
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True),nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True
    )


    __table_args__ = (
        Index("ix_admin_notifications_kind_read_at", "kind", "read_at"),
        CheckConstraint(
            "(CASE WHEN product_id IS NOT NULL THEN 1 ELSE 0 END) + "
            "(CASE WHEN product_variant_id IS NOT NULL THEN 1 ELSE 0 END) + "
            "(CASE WHEN offer_id IS NOT NULL THEN 1 ELSE 0 END) + "
            "(CASE WHEN order_id IS NOT NULL THEN 1 ELSE 0 END) <= 1 ",
            name="ck_admin_notifications_single_ref"
        )
    )


    @property
    def ref(self) -> Optional[object]:
        return self.product or self.product_variant or self.order or self.offer



class PushCampaign(Base):
    __tablename__="push_campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    audience_type: Mapped[CampaignAudienceType] = mapped_column(
        SQLEnum(
            CampaignAudienceType,
            name="campaign_audience_type_enum",
            values_callable=lambda x: [e.value for e in x]
        ),
        nullable=False,
        index=True
    )

    sent_at: Mapped[Optional[datetime]] = mapped_column(
            DateTime(timezone=True),
            nullable=False,
            index=True
        )

    created_at: Mapped[Optional[datetime]] = mapped_column(
            DateTime(timezone=True),
            default=lambda: datetime.now(UTC),
            nullable=False,
            index=True
        )

    recipient_count: Mapped[Optional[int]]= mapped_column(Integer, nullable=True)

    recipients: Mapped[list["PushCampaignRecipient"]] = relationship("PushCampaignRecipient",  back_populates="campaign")


class PushCampaignRecipient(Base):
    __tablename__="push_campaign_recipients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, 
        ForeignKey("users.id", ondelete="CASCADE"), 
        nullable=False, 
        index=True
    )
    campaign_id: Mapped[int] = mapped_column(
        Integer, 
        ForeignKey("push_campaigns.id", ondelete="CASCADE"), 
        nullable=False, 
        index=True
    )


    campaign: Mapped["PushCampaign"] = relationship("PushCampaign", back_populates="recipients")
    __table_args__ = (
        UniqueConstraint("campaign_id", "user_id", name="uq_push_campaign_recipient"),
    )


class ActivityLog(Base):
    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # FK for querying "everything Sara did" — but nullable, and NOT
    # what's displayed. If the admin account is later deleted, this
    # goes to NULL; the log entry stays fully readable regardless.
    actor_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Snapshot of the actor's name at write time — same pattern as
    # order_items.name_snapshot. None only for genuine system events
    # (e.g. stock auto-hitting 0), in which case use 'System'.
    actor_label: Mapped[str] = mapped_column(String(100), nullable=False)

    kind: Mapped[ActivityKind] = mapped_column(
        SQLEnum(
            ActivityKind,
            name="activity_kind_enum",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        index=True,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False, index=True
    )

    actor: Mapped[Optional["AdminUser"]] = relationship(foreign_keys=[actor_id])



class Purchase(Base):
    """
        This table is for taking notes pf purchases from suppliers just for book keeping
        Admin will insert a row whenever buy something from a supplier.
    """
    __tablename__ = "purchases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Integer Toman
    amount: Mapped[int] = mapped_column(Integer, nullable=False)

    # The day this purchase belongs to on the calendar — admin can backdate
    # this (logged today, happened last week). Date, not DateTime: the
    # calendar endpoint only ever cares about the day, and a plain Date
    # makes the year/month range filter trivial.
    purchase_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # the purchase date could be different from the day it get inserted
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
