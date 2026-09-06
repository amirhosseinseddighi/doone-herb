from __future__ import annotations

from datetime import datetime, time
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.order import (
    FulfillmentMethod,
    OrderStatus,
    OrderStatusEventActor,
    PaymentMethod,
    PaymentProvider,
    PaymentStatus,
)


class DeliverySlotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    note: Optional[str]
    fee: int
    kind: str
    cutoff_time: time
    active: bool


class OrderCreate(BaseModel):
    """
    Checkout payload. Line items come from the caller's cart, never from the
    client. Money (subtotal/delivery_fee/discount/total) is computed
    server-side from the cart + delivery slot, never accepted as input.
    """

    address_id: int
    delivery_slot_id: int
    fulfillment_method: FulfillmentMethod
    payment_method: PaymentMethod
    note: Optional[str] = Field(default=None, max_length=1000)


class OrderStatusUpdate(BaseModel):
    """Staff-driven status transition."""

    status: OrderStatus
    note: Optional[str] = Field(default=None, max_length=1000)


class OrderFulfillmentUpdate(BaseModel):
    """Staff attaches/updates  tracking details on an order."""
    tracking_code: Optional[str] = Field(default=None, max_length=100)



class OrderItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    product_variant_id: int
    name_snapshot: str
    size_label_snapshot: str
    unit_price_snapshot: int
    qty: int
    line_total: int


class OrderStatusEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: OrderStatus
    note: Optional[str]
    actor: OrderStatusEventActor
    actor_user_id: Optional[int]
    created_at: datetime


class PaymentRead(BaseModel):
    """Deliberately omits raw_payload — that's provider webhook internals, not customer-facing."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    provider: PaymentProvider
    provider_ref: str
    amount: int
    status: PaymentStatus
    created_at: datetime


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_no: str
    user_id: int
    address_id: int
    delivery_slot: DeliverySlotRead

    status: OrderStatus

    fulfillment_method: FulfillmentMethod
    tracking_code: Optional[str]

    subtotal: int
    delivery_fee: int
    discount: int
    total: int

    payment_method: PaymentMethod
    payment_status: PaymentStatus

    note: Optional[str]

    placed_at: datetime
    updated_at: datetime

    items: list[OrderItemRead] = []
    status_events: list[OrderStatusEventRead] = []
    payments: list[PaymentRead] = []


class OrderSummary(BaseModel):
    """Lightweight row for list views (no items/events/payments)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    order_no: str
    status: OrderStatus
    payment_status: PaymentStatus
    total: int
    placed_at: datetime


class OrderListResponse(BaseModel):
    items: list[OrderSummary]
    total: int
    page: int
    page_size: int