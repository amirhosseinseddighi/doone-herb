from datetime import time
from typing import Any
from uuid import uuid4

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category, Product, ProductVariant
from app.models.identity import Roles, User
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


async def create_admin_product(
    client: AsyncClient,
    db_session: AsyncSession,
    *,
    stock_qty: int,
) -> tuple[str, dict[str, Any]]:
    suffix = uuid4().hex[:8]
    await create_test_user(
        client,
        email="admin@example.com",
        name="Test Admin",
        phone="09121231235",
    )
    admin = await db_session.scalar(
        select(User).where(User.email == "admin@example.com")
    )
    assert admin is not None
    admin.role = Roles.MANAGER
    await db_session.flush()
    admin_token = await login_user(client, email="admin@example.com")

    category_response = await client.post(
        "/api/v1/categories",
        headers=auth_header(admin_token),
        json={
            "name": f"Admin Herbs {suffix}",
            "tint_color": "#E8F5E9",
            "dot_color": "#43A047",
            "sort_order": 0,
            "is_active": True,
        },
    )
    assert category_response.status_code == status.HTTP_201_CREATED

    product_response = await client.post(
        "/api/v1/products",
        headers=auth_header(admin_token),
        json={
            "name": f"Admin Mint {suffix}",
            "category_id": category_response.json()["id"],
            "variants": [
                {
                    "label": "100g",
                    "price": 1500,
                    "compare_at_price": None,
                    "stock_qty": stock_qty,
                }
            ],
            "description": "Test product",
            "is_in_stock": stock_qty > 0,
            "is_featured": False,
        },
    )
    assert product_response.status_code == status.HTTP_201_CREATED
    return admin_token, product_response.json()


async def create_user_address_and_cart(
    client: AsyncClient,
    *,
    variant_id: int,
    qty: int = 1,
) -> tuple[str, int]:
    await create_test_user(
        client,
        email="customer@example.com",
        name="Test Customer",
        phone="09121231236",
    )
    user_token = await login_user(client, email="customer@example.com")
    headers = auth_header(user_token)

    address_response = await client.post(
        "/api/v1/addresses",
        headers=headers,
        json={
            "label": "Home",
            "line": "Test street",
            "postal_code": "10000",
            "phone": "09121231236",
            "lat": 0.0,
            "lng": 0.0,
        },
    )
    assert address_response.status_code == status.HTTP_201_CREATED

    cart_response = await client.post(
        "/api/v1/cart",
        headers=headers,
        json={"product_variant_id": variant_id, "qty": qty},
    )
    assert cart_response.status_code == status.HTTP_200_OK
    return user_token, address_response.json()["id"]


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
        "/api/v1/addresses",
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
        "/api/v1/cart",
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


@pytest.mark.anyio
async def test_cart_item_being_deleted_after_admin_delete_the_product(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin_token, product = await create_admin_product(
        client,
        db_session,
        stock_qty=5,
    )
    variant_id = product["variants"][0]["id"]
    user_token, address_id = await create_user_address_and_cart(
        client,
        variant_id=variant_id,
    )
    slot = await create_test_delivery_slot(db_session)

    delete_response = await client.delete(
        f"/api/v1/products/{product['id']}",
        headers=auth_header(admin_token),
    )
    assert delete_response.status_code == status.HTTP_204_NO_CONTENT

    checkout_response = await client.post(
        "/orders/checkout",
        headers=auth_header(user_token),
        json=checkout_payload(address_id, slot.id),
    )

    assert checkout_response.status_code == status.HTTP_400_BAD_REQUEST
    assert checkout_response.json()["detail"] == "Cart is empty"


@pytest.mark.anyio
async def test_checkout_rejects_cart_item_that_runs_out_of_stock(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin_token, product = await create_admin_product(
        client,
        db_session,
        stock_qty=5,
    )
    variant = product["variants"][0]
    user_token, address_id = await create_user_address_and_cart(
        client,
        variant_id=variant["id"],
    )
    slot = await create_test_delivery_slot(db_session)

    stock_response = await client.patch(
        f"/api/v1/products/{product['id']}/variants/{variant['id']}",
        headers=auth_header(admin_token),
        json={"stock_qty": 0},
    )
    assert stock_response.status_code == status.HTTP_200_OK

    checkout_response = await client.post(
        "/orders/checkout",
        headers=auth_header(user_token),
        json=checkout_payload(address_id, slot.id),
    )
    assert checkout_response.status_code == status.HTTP_409_CONFLICT
    assert checkout_response.json()["detail"] == f"Not enough stock for {product['name']}"


@pytest.mark.anyio
async def test_deleting_variant_after_checkout_does_not_affect_existing_order(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin_token, product = await create_admin_product(
        client,
        db_session,
        stock_qty=5,
    )

    variant_response = await client.post(
        f"/api/v1/products/{product['id']}/variants",
        headers=auth_header(admin_token),
        json={
            "label": "50g",
            "price": 800,
            "compare_at_price": None,
            "stock_qty": 5,
        },
    )
    assert variant_response.status_code == status.HTTP_201_CREATED
    variant_id = variant_response.json()["id"]

    user_token, address_id = await create_user_address_and_cart(
        client,
        variant_id=variant_id,
    )
    slot = await create_test_delivery_slot(db_session)

    checkout_response = await client.post(
        "/orders/checkout",
        headers=auth_header(user_token),
        json=checkout_payload(address_id, slot.id),
    )
    assert checkout_response.status_code == status.HTTP_201_CREATED
    order = checkout_response.json()

    delete_variant_response = await client.delete(
        f"/api/v1/products/{product['id']}/variants/{variant_id}",
        headers=auth_header(admin_token),
    )
    assert delete_variant_response.status_code == status.HTTP_204_NO_CONTENT

    detail_response = await client.get(
        f"/orders/{order['id']}", headers=auth_header(user_token)
    )
    assert detail_response.status_code == status.HTTP_200_OK
    assert detail_response.json()["id"] == order["id"]
    assert detail_response.json()["items"][0]["qty"] == order["items"][0]["qty"]

    list_response = await client.get("/orders", headers=auth_header(user_token))
    assert list_response.status_code == status.HTTP_200_OK
    assert list_response.json()["total"] == 1


@pytest.mark.anyio
async def test_deleting_product_after_checkout_does_not_affect_existing_order(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin_token, product = await create_admin_product(
        client,
        db_session,
        stock_qty=5,
    )
    variant_id = product["variants"][0]["id"]
    user_token, address_id = await create_user_address_and_cart(
        client,
        variant_id=variant_id,
    )
    slot = await create_test_delivery_slot(db_session)

    checkout_response = await client.post(
        "/orders/checkout",
        headers=auth_header(user_token),
        json=checkout_payload(address_id, slot.id),
    )
    assert checkout_response.status_code == status.HTTP_201_CREATED
    order = checkout_response.json()

    delete_response = await client.delete(
        f"/api/v1/products/{product['id']}",
        headers=auth_header(admin_token),
    )
    assert delete_response.status_code == status.HTTP_204_NO_CONTENT

    detail_response = await client.get(
        f"/orders/{order['id']}", headers=auth_header(user_token)
    )
    assert detail_response.status_code == status.HTTP_200_OK
    assert detail_response.json()["id"] == order["id"]
    assert detail_response.json()["items"][0]["qty"] == order["items"][0]["qty"]

    code_response = await client.get(
        f"/orders/code/{order['order_no']}", headers=auth_header(user_token)
    )
    assert code_response.status_code == status.HTTP_200_OK
    assert code_response.json()["id"] == order["id"]