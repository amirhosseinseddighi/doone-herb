from datetime import time
from uuid import uuid4

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category, Product, ProductVariant
from app.models.order import DeliverySlot, DeliverySlotKind
from tests.conftest import auth_header, create_test_user, login_user


async def create_test_variant(
    db_session: AsyncSession,
    *,
    price: int = 1250,
    stock_qty: int = 10,
) -> ProductVariant:
    suffix = uuid4().hex
    category = Category(
        slug=f"herbs-{suffix}",
        name="Herbs",
        tint_color="#E8F5E9",
        dot_color="#43A047",
        sort_order=0,
    )
    product = Product(
        slug=f"mint-{suffix}",
        name="Mint",
        category=category,
    )
    variant = ProductVariant(
        product=product,
        label="100g",
        price=price,
        stock_qty=stock_qty,
        sku=f"MINT-{suffix}",
    )
    db_session.add(variant)
    await db_session.flush()
    return variant


async def create_test_delivery_slot(db_session: AsyncSession) -> DeliverySlot:
    slot = DeliverySlot(
        label="Same day",
        note=None,
        fee=300,
        kind=DeliverySlotKind.SAME_DAY,
        cutoff_time=time(18, 0),
        active=True,
    )
    db_session.add(slot)
    await db_session.flush()
    return slot


def checkout_payload(address_id: int, delivery_slot_id: int) -> dict[str, object]:
    return {
        "address_id": address_id,
        "delivery_slot_id": delivery_slot_id,
        "fulfillment_method": "courier",
        "payment_method": "cash_on_delivery",
        "note": "Leave at the door",
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method", "path", "json"),
    [
        ("get", "/orders", None),
        ("get", "/orders/1", None),
        ("get", "/orders/code/ORD-missing", None),
        (
            "post",
            "/orders/checkout",
            checkout_payload(address_id=1, delivery_slot_id=1),
        ),
        ("post", "/orders/1/cancel", None),
    ],
)
async def test_unauthenticated_order_routes_require_login(
    client: AsyncClient,
    method: str,
    path: str,
    json: dict[str, object] | None,
):
    response = await client.request(method, path, json=json)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "Not authenticated"


@pytest.mark.anyio
async def test_authenticated_user_can_list_orders_when_empty(client: AsyncClient):
    await create_test_user(client)
    token = await login_user(client)

    response = await client.get("/orders", headers=auth_header(token))

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "items": [],
        "total": 0,
        "page": 1,
        "page_size": 20,
    }


@pytest.mark.anyio
async def test_authenticated_user_can_checkout_read_and_cancel_order(
    client: AsyncClient,
    db_session: AsyncSession,
):
    await create_test_user(client)
    token = await login_user(client)
    headers = auth_header(token)
    variant = await create_test_variant(db_session, price=1500, stock_qty=5)
    slot = await create_test_delivery_slot(db_session)

    address_response = await client.post(
        "/api/addresses",
        headers=headers,
        json={
            "label": "Home",
            "line": "Test street",
            "postal_code": "10000",
            "phone": "09121231234",
            "lat": 0.0,
            "lng": 0.0,
        },
    )
    assert address_response.status_code == status.HTTP_201_CREATED
    address_id = address_response.json()["id"]

    cart_response = await client.post(
        "/api/cart",
        headers=headers,
        json={"product_variant_id": variant.id, "qty": 2},
    )
    assert cart_response.status_code == status.HTTP_200_OK

    checkout_response = await client.post(
        "/orders/checkout",
        headers=headers,
        json=checkout_payload(address_id, slot.id),
    )
    assert checkout_response.status_code == status.HTTP_201_CREATED
    order = checkout_response.json()
    assert order["status"] == "new"
    assert order["subtotal"] == 3000
    assert order["delivery_fee"] == 300
    assert order["total"] == 3300
    assert order["items"][0]["qty"] == 2

    list_response = await client.get("/orders", headers=headers)
    assert list_response.status_code == status.HTTP_200_OK
    assert list_response.json()["total"] == 1
    assert list_response.json()["items"][0]["order_no"] == order["order_no"]

    detail_response = await client.get(f"/orders/{order['id']}", headers=headers)
    code_response = await client.get(
        f"/orders/code/{order['order_no']}", headers=headers
    )
    assert detail_response.status_code == status.HTTP_200_OK
    assert code_response.status_code == status.HTTP_200_OK
    assert detail_response.json()["id"] == order["id"]
    assert code_response.json()["id"] == order["id"]

    cancel_response = await client.post(
        f"/orders/{order['id']}/cancel", headers=headers
    )
    assert cancel_response.status_code == status.HTTP_200_OK
    assert cancel_response.json()["status"] == "cancelled"