from datetime import UTC, datetime
import enum
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.database import Base
from sqlalchemy import Enum as SQLEnum, Time


class DeliverySlotKind(str, enum.Enum):
    SAME_DAY = 'same_day'
    NEXT_MORNING = 'next_morning'
    PICKUP = 'pickup'


class OrderStatus(str, enum.Enum):
    NEW = "new"
    PACKING = "packing"
    SHIPPED = "shipped"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    RETURNED = "returned"


class FulfillmentMethod(str, enum.Enum):
    COURIER = "courier"
    POST = "post"
    PICKUP = "pickup"


class CourierType(str, enum.Enum):
    IN_HOUSE_RIDER = "in_house_rider"
    TIPAX = "tipax"
    NATIONAL_POST = "national_post"
    NONE = "none"


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





class Order(Base):
    __tablename__ = "orders"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_no: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    address_id: Mapped[int] = mapped_column(Integer, ForeignKey("addresses.id"), nullable=False, index=True)
    delivery_slot_id: Mapped[int] = mapped_column(
        Integer, 
        ForeignKey("delivery_slots.id"), 
        nullable=False, 
        index=True
    )
    status: Mapped[OrderStatus] = mapped_column(
        SQLEnum(OrderStatus, name="order_status_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False
    )
    fulfillment_method: Mapped[FulfillmentMethod] = mapped_column(
        SQLEnum(FulfillmentMethod, name="fulfillment_method_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False
    )
    courier: Mapped[CourierType] = mapped_column(
        SQLEnum(CourierType, name="courier_type_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False
    )
    rider_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    tracking_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    subtotal: Mapped[int] = mapped_column(Integer, nullable=False)
    delivery_fee: Mapped[int] = mapped_column(Integer, nullable=False)
    discount: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total: Mapped[int] = mapped_column(Integer, nullable=False)
    payment_method: Mapped[PaymentMethod] = mapped_column(
        SQLEnum(
            PaymentMethod, 
            name="payment_method_enum", 
            values_callable=lambda x: [e.value for e in x]),
            nullable=False
        )
    payment_status: Mapped[PaymentStatus] = mapped_column(
        SQLEnum(
            PaymentStatus, 
            name="payment_status_enum", 
            values_callable=lambda x: [e.value for e in x]),
            nullable=False
        )
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    placed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(UTC), 
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(UTC), 
        onupdate=lambda: datetime.now(UTC), 
        nullable=False
    )
    
    user: Mapped["User"] = relationship("User", back_populates="orders")
    address: Mapped["Address"] = relationship("Address", back_populates="orders")
    delivery_slot: Mapped["DeliverySlot"] = relationship("DeliverySlot", back_populates="orders")
    reviews: Mapped[list["Review"]] = relationship("Review", back_populates="order")
    items: Mapped[list["OrderItem"]] = relationship("OrderItem", back_populates="order")
    status_events: Mapped[list["OrderStatusEvent"]] = relationship(
        "OrderStatusEvent", 
        back_populates="order",
        cascade="all, delete-orphan"
    )
    payments: Mapped[list["Payment"]] = relationship("Payment", back_populates="order")



class DeliverySlot(Base):
    __tablename__ = "delivery_slots"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fee: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[DeliverySlotKind] = mapped_column(
        SQLEnum(
            DeliverySlotKind,
            name="delivery_slot_kind_enum",
            values_callable=lambda x: [e.value for e in x]
        ),
        nullable=False
    )
    cutoff_time: Mapped[Time] = mapped_column(Time, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    orders: Mapped[list["Order"]] = relationship("Order", back_populates="delivery_slot")


class Cart(Base):
    __tablename__="carts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    session_id: Mapped[str] = mapped_column(String(100),nullable=False, unique=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), 
            default=lambda: datetime.now(UTC), 
            onupdate=lambda: datetime.now(UTC)
        )


    user: Mapped["User"] = relationship("User", back_populates="cart")
    items: Mapped[list["CartItem"]] = relationship("CartItem", back_populates="cart")



class CartItem(Base):
    __tablename__="cart_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cart_id: Mapped[int] = mapped_column(Integer, ForeignKey("carts.id"), index=True)
    product_variant_id: Mapped[int] = mapped_column(
        Integer, 
        ForeignKey("product_variants.id"), 
        index=True, 
        nullable=False
    )
    qty: Mapped[int] = mapped_column(Integer, nullable=False)


    cart: Mapped[Optional["Cart"]] = relationship("Cart", back_populates="items")



class OrderItem(Base):
    __tablename__ = "order_items"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(
        Integer, 
        ForeignKey("orders.id"), 
        nullable=False, 
        index=True
    )
    product_id: Mapped[int] = mapped_column(
        Integer, 
        ForeignKey("products.id"), 
        nullable=False, 
        index=True
    )
    product_variant_id: Mapped[int] = mapped_column(
        Integer, 
        ForeignKey("product_variants.id"), 
        nullable=False, 
        index=True
    )
    name_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    size_label_snapshot: Mapped[str] = mapped_column(String(100), nullable=False)
    unit_price_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    line_total: Mapped[int] = mapped_column(Integer, nullable=False)
    
    order: Mapped["Order"] = relationship("Order", back_populates="items")
    product: Mapped["Product"] = relationship("Product", back_populates="order_items")
    product_variant: Mapped["ProductVariant"] = relationship("ProductVariant", back_populates="order_items")




class OrderStatusEvent(Base):
    __tablename__ = "order_status_events"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(
        Integer, 
        ForeignKey("orders.id"), 
        nullable=False, 
        index=True
    )
    status: Mapped[OrderStatus] = mapped_column(
        SQLEnum(OrderStatus, name="order_status_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False
    )
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    actor: Mapped[OrderStatusEventActor] = mapped_column(
        SQLEnum(
            OrderStatusEventActor, 
            name="order_status_event_actor_enum", 
            values_callable=lambda x: [e.value for e in x]
        ),
        nullable=False
        )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(UTC), 
        nullable=False,
        index=True
    )
    
    order: Mapped["Order"] = relationship("Order", back_populates="status_events")


class Payment(Base):
    __tablename__ = "payments"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(
        Integer, 
        ForeignKey("orders.id"), 
        nullable=False, 
        index=True
    )
    provider: Mapped[PaymentProvider] = mapped_column(
        SQLEnum(PaymentProvider, name="payment_provider_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False
    )
    provider_ref: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        SQLEnum(PaymentStatus, name="payment_status_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False
    )
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(UTC), 
        nullable=False,
        index=True
    )
    
    order: Mapped["Order"] = relationship("Order", back_populates="payments")