"""Order domain models: carts, orders, payments, and delivery scheduling."""

from datetime import UTC, datetime, time
import enum
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def _utcnow() -> datetime:
    """Single source of truth for 'now' across all created_at/updated_at defaults."""
    return datetime.now(UTC)


def _pg_enum(enum_cls: type[enum.Enum], name: str) -> SQLEnum:
    """ Create DB enum column given python enums """
    return SQLEnum(enum_cls, name=name, values_callable=lambda x: [e.value for e in x])


# ====== ENUMS =========

class DeliverySlotKind(str, enum.Enum):
    SAME_DAY = "same_day"
    NEXT_MORNING = "next_morning"
    PICKUP = "pickup"


class OrderStatus(str, enum.Enum):
    NEW = "new"
    PACKING = "packing"
    SHIPPED = "shipped"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    RETURNED = "returned"
    CANCELLED = "cancelled"


class FulfillmentMethod(str, enum.Enum):
    COURIER = "courier"
    POST = "post"
    PICKUP = "pickup"

class PaymentMethod(str, enum.Enum):
    ONLINE = "online"
    CASH_ON_DELIVERY = "cash_on_delivery"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"


class OrderStatusEventActor(str, enum.Enum):
    SYSTEM = "system"
    ADMIN = "admin"
    COURIER = "courier"


class PaymentProvider(str, enum.Enum):
    STRIPE = "stripe"
    PAYPAL = "paypal"
    RAZORPAY = "razorpay"
    BANK_TRANSFER = "bank_transfer"
    CASH = "cash"


# DB ENUMS

ORDER_STATUS_ENUM = _pg_enum(OrderStatus, "order_status_enum")
PAYMENT_STATUS_ENUM = _pg_enum(PaymentStatus, "payment_status_enum")

# ========== MODELS ===========

class DeliverySlot(Base):
    __tablename__ = "delivery_slots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fee: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[DeliverySlotKind] = mapped_column(
        _pg_enum(DeliverySlotKind, "delivery_slot_kind_enum"), nullable=False
    )
    cutoff_time: Mapped[time] = mapped_column(Time, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    orders: Mapped[list["Order"]] = relationship("Order", back_populates="delivery_slot")

    __table_args__ = (CheckConstraint("fee >= 0", name="ck_delivery_slots_fee_non_negative"),)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_no: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    address_id: Mapped[int] = mapped_column(Integer, ForeignKey("addresses.id"), nullable=False, index=True)
    delivery_slot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("delivery_slots.id"), nullable=False, index=True
    )

    status: Mapped[OrderStatus] = mapped_column(ORDER_STATUS_ENUM, nullable=False, index=True)

    fulfillment_method: Mapped[FulfillmentMethod] = mapped_column(
        _pg_enum(FulfillmentMethod, "fulfillment_method_enum"), nullable=False
    )
    tracking_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)

    subtotal: Mapped[int] = mapped_column(Integer, nullable=False)
    delivery_fee: Mapped[int] = mapped_column(Integer, nullable=False)
    discount: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total: Mapped[int] = mapped_column(Integer, nullable=False)

    payment_method: Mapped[PaymentMethod] = mapped_column(
        _pg_enum(PaymentMethod, "payment_method_enum"), nullable=False
    )
    payment_status: Mapped[PaymentStatus] = mapped_column(PAYMENT_STATUS_ENUM, nullable=False, index=True)

    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    placed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="orders")
    address: Mapped["Address"] = relationship("Address", back_populates="orders")
    delivery_slot: Mapped["DeliverySlot"] = relationship("DeliverySlot", back_populates="orders")
    reviews: Mapped[list["Review"]] = relationship("Review", back_populates="order")
    items: Mapped[list["OrderItem"]] = relationship(
        "OrderItem", back_populates="order", cascade="all, delete-orphan"
    )
    status_events: Mapped[list["OrderStatusEvent"]] = relationship(
        "OrderStatusEvent",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderStatusEvent.created_at",
    )
    payments: Mapped[list["Payment"]] = relationship(
        "Payment", back_populates="order", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("subtotal >= 0", name="ck_orders_subtotal_non_negative"),
        CheckConstraint("delivery_fee >= 0", name="ck_orders_delivery_fee_non_negative"),
        CheckConstraint("discount >= 0", name="ck_orders_discount_non_negative"),
        CheckConstraint("total >= 0", name="ck_orders_total_non_negative"),
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    product_variant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("product_variants.id"), nullable=False, index=True
    )

    name_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    size_label_snapshot: Mapped[str] = mapped_column(String(100), nullable=False)
    unit_price_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    line_total: Mapped[int] = mapped_column(Integer, nullable=False)

    order: Mapped["Order"] = relationship("Order", back_populates="items")
    product: Mapped["Product"] = relationship("Product", back_populates="order_items")
    product_variant: Mapped["ProductVariant"] = relationship("ProductVariant", back_populates="order_items")

    __table_args__ = (
        CheckConstraint("qty > 0", name="ck_order_items_qty_positive"),
        CheckConstraint("unit_price_snapshot >= 0", name="ck_order_items_unit_price_non_negative"),
    )


class OrderStatusEvent(Base):
    __tablename__ = "order_status_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    status: Mapped[OrderStatus] = mapped_column(ORDER_STATUS_ENUM, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    actor: Mapped[OrderStatusEventActor] = mapped_column(
        _pg_enum(OrderStatusEventActor, "order_status_event_actor_enum"), nullable=False
    )
    # which admin
    actor_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )

    order: Mapped["Order"] = relationship("Order", back_populates="status_events")
    actor_user: Mapped[Optional["User"]] = relationship("User")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    provider: Mapped[PaymentProvider] = mapped_column(
        _pg_enum(PaymentProvider, "payment_provider_enum"), nullable=False
    )
    provider_ref: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(PAYMENT_STATUS_ENUM, nullable=False)
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )

    order: Mapped["Order"] = relationship("Order", back_populates="payments")

    __table_args__ = (
        UniqueConstraint("provider", "provider_ref", name="uq_payments_provider_ref"),
        CheckConstraint("amount >= 0", name="ck_payments_amount_non_negative"),
    )