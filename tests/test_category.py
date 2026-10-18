from typing import Any

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category, Product
from app.models.identity import Roles, User
from tests.conftest import auth_header, create_test_user, login_user

# =========== HELPERS ============

async def create_admin(client: AsyncClient, db_session: AsyncSession) -> str:
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
    return await login_user(client, email="admin@example.com")

def category_payload(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "tint_color": "#E8F5E9",
        "dot_color": "#43A047",
        "sort_order": 0,
        "is_active": True,
    }

async def create_category(
    client: AsyncClient,
    admin_token: str,
    name: str,
) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/categories",
        headers=auth_header(admin_token),
        json=category_payload(name),
    )
    assert response.status_code == status.HTTP_201_CREATED
    return response.json()

def product_payload(category_id: int, name: str) -> dict[str, Any]:
    return {
        "name": name,
        "category_id": category_id,
        "variants": [
            {
                "label": "100g",
                "price": 1500,
                "compare_at_price": None,
                "stock_qty": 10,
            }
        ],
        "description": "Test product",
        "is_in_stock": True,
        "is_featured": False,
    }

# ========== TESTS ==============

@pytest.mark.anyio
async def test_admin_can_create_category(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin_token = await create_admin(client, db_session)

    response = await client.post(
        "/api/v1/categories",
        headers=auth_header(admin_token),
        json=category_payload("Fresh Herbs"),
    )

    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert body["name"] == "Fresh Herbs"
    assert body["slug"] == "fresh-herbs"
    assert body["tint_color"] == "#E8F5E9"
    assert body["dot_color"] == "#43A047"
    assert body["sort_order"] == 0
    assert body["is_active"] is True

    stored = await db_session.scalar(
        select(Category).where(Category.slug == "fresh-herbs")
    )
    assert stored is not None
    assert stored.name == "Fresh Herbs"

@pytest.mark.anyio
async def test_admin_can_create_category_with_unique_slug_when_name_collides(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin_token = await create_admin(client, db_session)

    first = await create_category(client, admin_token, "Spices")
    second = await create_category(client, admin_token, "Spices")

    assert first["slug"] == "spices"
    assert second["slug"] == "spices-1"

@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method", "path", "json"),
    [
        ("post", "/api/v1/categories", category_payload("Nope")),
        ("patch", "/api/v1/categories/1", {"name": "Nope"}),
        ("delete", "/api/v1/categories/1", None),
    ],
)
async def test_unauthenticated_category_routes_require_login(
    client: AsyncClient,
    method: str,
    path: str,
    json: dict[str, object] | None,
):
    response = await client.request(method, path, json=json)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "Not authenticated"

@pytest.mark.anyio
async def test_admin_can_update_category(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin_token = await create_admin(client, db_session)
    category = await create_category(client, admin_token, "Old Name")

    response = await client.patch(
        f"/api/v1/categories/{category['id']}",
        headers=auth_header(admin_token),
        json={"name": "New Name", "sort_order": 5},
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["name"] == "New Name"
    assert body["slug"] == "new-name"
    assert body["sort_order"] == 5
    # untouched fields keep their values
    assert body["tint_color"] == "#E8F5E9"
    assert body["is_active"] is True

@pytest.mark.anyio
async def test_admin_can_delete_category(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin_token = await create_admin(client, db_session)
    category = await create_category(client, admin_token, "Doomed")

    delete_response = await client.delete(
        f"/api/v1/categories/{category['id']}",
        headers=auth_header(admin_token),
    )
    assert delete_response.status_code == status.HTTP_204_NO_CONTENT

    # removed from the public listing
    list_response = await client.get("/api/v1/categories")
    assert list_response.status_code == status.HTTP_200_OK
    assert all(c["id"] != category["id"] for c in list_response.json()["categories"])

    # deleting again is a 404
    second_delete = await client.delete(
        f"/api/v1/categories/{category['id']}",
        headers=auth_header(admin_token),
    )
    assert second_delete.status_code == status.HTTP_404_NOT_FOUND

    stored = await db_session.scalar(
        select(Category).where(Category.id == category["id"])
    )
    assert stored is not None
    assert stored.is_deleted is True
    assert stored.is_active is False

@pytest.mark.anyio
async def test_deleting_category_keeps_products_but_hides_category(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin_token = await create_admin(client, db_session)
    category = await create_category(client, admin_token, "Herbs")

    product_response = await client.post(
        "/api/v1/products",
        headers=auth_header(admin_token),
        json=product_payload(category["id"], "Mint"),
    )
    assert product_response.status_code == status.HTTP_201_CREATED
    product = product_response.json()

    delete_response = await client.delete(
        f"/api/v1/categories/{category['id']}",
        headers=auth_header(admin_token),
    )
    assert delete_response.status_code == status.HTTP_204_NO_CONTENT

    # the product row itself is not deleted or orphaned
    stored_product = await db_session.scalar(
        select(Product).where(Product.id == product["id"])
    )
    assert stored_product is not None
    assert stored_product.is_deleted is False
    assert stored_product.category_id == category["id"]

    # the category disappears from the public listing
    list_response = await client.get("/api/v1/categories")
    assert list_response.status_code == status.HTTP_200_OK
    assert all(c["id"] != category["id"] for c in list_response.json()["categories"])

@pytest.mark.anyio
async def test_order_snapshot_survives_category_deletion(
    client: AsyncClient,
    db_session: AsyncSession,
):
    from tests.test_orders import (
        checkout_payload,
        create_test_delivery_slot,
        create_user_address_and_cart,
    )

    admin_token = await create_admin(client, db_session)
    category = await create_category(client, admin_token, "Snapshot Herbs")

    product_response = await client.post(
        "/api/v1/products",
        headers=auth_header(admin_token),
        json={
            "name": "Snapshot Mint",
            "category_id": category["id"],
            "variants": [
                {
                    "label": "250g",
                    "price": 2000,
                    "compare_at_price": None,
                    "stock_qty": 5,
                }
            ],
            "description": "Mint for snapshot test",
            "is_in_stock": True,
            "is_featured": False,
        },
    )
    assert product_response.status_code == status.HTTP_201_CREATED
    product = product_response.json()
    variant_id = product["variants"][0]["id"]

    user_token, address_id = await create_user_address_and_cart(
        client,
        variant_id=variant_id,
    )
    slot = await create_test_delivery_slot(db_session)

    checkout_response = await client.post(
        "/api/v1/orders/checkout",
        headers=auth_header(user_token),
        json=checkout_payload(address_id, slot.id),
    )
    assert checkout_response.status_code == status.HTTP_201_CREATED
    order = checkout_response.json()

    delete_response = await client.delete(
        f"/api/v1/categories/{category['id']}",
        headers=auth_header(admin_token),
    )
    assert delete_response.status_code == status.HTTP_204_NO_CONTENT

    detail_response = await client.get(
        f"/api/v1/orders/{order['id']}", headers=auth_header(user_token)
    )
    assert detail_response.status_code == status.HTTP_200_OK
    item = detail_response.json()["items"][0]
    assert item["name_snapshot"] == "Snapshot Mint"
    assert item["size_label_snapshot"] == "250g"
    assert item["unit_price_snapshot"] == 2000
    assert item["qty"] == 1