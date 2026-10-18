from asyncio import sleep
from typing import Any

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cart import CartItem
from app.models.category import Product, ProductVariant
from tests.conftest import auth_header, create_test_user, login_user
from tests.test_category import create_admin, create_category, product_payload

# =========== HELPERS ============

async def create_product(
    client: AsyncClient,
    admin_token: str,
    category_id: int,
    name: str = "Mint",
) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/products",
        headers=auth_header(admin_token),
        json=product_payload(category_id, name),
    )
    assert response.status_code == status.HTTP_201_CREATED
    return response.json()

# ========== TESTS ==============

@pytest.mark.anyio
async def test_admin_can_create_product(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin_token = await create_admin(client, db_session)
    category = await create_category(client, admin_token, "Herbs")

    response = await client.post(
        "/api/v1/products",
        headers=auth_header(admin_token),
        json=product_payload(category["id"], "Fresh Mint"),
    )

    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert body["name"] == "Fresh Mint"
    assert body["slug"] == "fresh-mint"
    assert body["category"]["id"] == category["id"]
    assert len(body["variants"]) == 1
    assert body["variants"][0]["label"] == "100g"
    assert body["variants"][0]["price"] == 1500
    assert body["variants"][0]["stock_qty"] == 10
    assert body["is_featured"] is False

@pytest.mark.anyio
async def test_create_product_with_unknown_category_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin_token = await create_admin(client, db_session)

    response = await client.post(
        "/api/v1/products",
        headers=auth_header(admin_token),
        json=product_payload(99999, "Ghost Mint"),
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "Category not found"

@pytest.mark.anyio
async def test_public_product_listing_excludes_hidden_and_deleted_products(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin_token = await create_admin(client, db_session)
    category = await create_category(client, admin_token, "Herbs")
    visible = await create_product(client, admin_token, category["id"], "Visible Mint")
    hidden = await create_product(client, admin_token, category["id"], "Hidden Mint")

    # out-of-stock products are hidden
    hidden_update = await client.patch(
        f"/api/v1/products/{hidden['id']}",
        headers=auth_header(admin_token),
        json={"is_hidden": True},
    )
    assert hidden_update.status_code == status.HTTP_200_OK

    delete_response = await client.delete(
        f"/api/v1/products/{visible['id']}",
        headers=auth_header(admin_token),
    )
    assert delete_response.status_code == status.HTTP_204_NO_CONTENT

    list_response = await client.get("/api/v1/products")
    assert list_response.status_code == status.HTTP_200_OK
    names = [p["name"] for p in list_response.json()["products"]]
    assert "Visible Mint" not in names
    assert "Hidden Mint" not in names

@pytest.mark.anyio
async def test_public_product_search_matches_name_and_description(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin_token = await create_admin(client, db_session)
    category = await create_category(client, admin_token, "Herbs")
    await create_product(client, admin_token, category["id"], "Peppermint")

    by_name = await client.get("/api/v1/products", params={"search": "pepper"})
    assert by_name.status_code == status.HTTP_200_OK
    assert [p["name"] for p in by_name.json()["products"]] == ["Peppermint"]

    by_description = await client.get(
        "/api/v1/products", params={"search": "Test product"}
    )
    assert by_description.status_code == status.HTTP_200_OK
    assert [p["name"] for p in by_description.json()["products"]] == ["Peppermint"]

    await sleep(1.1)  # stay under the 2/second rate limit

    no_match = await client.get("/api/v1/products", params={"search": "basil"})
    assert no_match.status_code == status.HTTP_200_OK
    assert no_match.json()["products"] == []

@pytest.mark.anyio
async def test_public_product_detail_by_slug(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin_token = await create_admin(client, db_session)
    category = await create_category(client, admin_token, "Herbs")
    product = await create_product(client, admin_token, category["id"], "Basil")

    response = await client.get(f"/api/v1/products/{product['slug']}")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["id"] == product["id"]
    assert response.json()["slug"] == "basil"

    missing = await client.get("/api/v1/products/does-not-exist")
    assert missing.status_code == status.HTTP_404_NOT_FOUND

@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method", "path", "json"),
    [
        ("post", "/api/v1/products", {"name": "Nope", "category_id": 1, "variants": []}),
        ("patch", "/api/v1/products/1", {"name": "Nope"}),
        ("delete", "/api/v1/products/1", None),
        ("post", "/api/v1/products/1/variants", {"label": "x", "price": 1, "stock_qty": 1}),
        ("delete", "/api/v1/products/1/variants/1", None),
        ("patch", "/api/v1/products/1/variants/1", {"price": 1}),
    ],
)
async def test_unauthenticated_product_routes_require_login(
    client: AsyncClient,
    method: str,
    path: str,
    json: dict[str, object] | None,
):
    response = await client.request(method, path, json=json)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "Not authenticated"

@pytest.mark.anyio
async def test_admin_can_update_product_and_slug_regenerates(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin_token = await create_admin(client, db_session)
    category = await create_category(client, admin_token, "Herbs")
    product = await create_product(client, admin_token, category["id"], "Old Mint")

    response = await client.patch(
        f"/api/v1/products/{product['id']}",
        headers=auth_header(admin_token),
        json={"name": "New Mint", "description": "Updated description"},
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["name"] == "New Mint"
    assert body["slug"] == "new-mint"
    assert body["description"] == "Updated description"

@pytest.mark.anyio
async def test_update_product_to_deleted_category_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin_token = await create_admin(client, db_session)
    category = await create_category(client, admin_token, "Doomed Category")
    other = await create_category(client, admin_token, "Other Category")
    product = await create_product(client, admin_token, other["id"], "Mint")

    delete_category_response = await client.delete(
        f"/api/v1/categories/{category['id']}",
        headers=auth_header(admin_token),
    )
    assert delete_category_response.status_code == status.HTTP_204_NO_CONTENT

    response = await client.patch(
        f"/api/v1/products/{product['id']}",
        headers=auth_header(admin_token),
        json={"category_id": category["id"]},
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "Target category not found or is deleted"

@pytest.mark.anyio
async def test_delete_product_soft_deletes_variants_and_clears_cart(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin_token = await create_admin(client, db_session)
    category = await create_category(client, admin_token, "Herbs")
    product = await create_product(client, admin_token, category["id"], "Mint")
    variant_id = product["variants"][0]["id"]

    await create_test_user(client)
    user_token = await login_user(client)
    cart_response = await client.post(
        "/api/v1/cart",
        headers=auth_header(user_token),
        json={"product_variant_id": variant_id, "qty": 1},
    )
    assert cart_response.status_code == status.HTTP_200_OK

    delete_response = await client.delete(
        f"/api/v1/products/{product['id']}",
        headers=auth_header(admin_token),
    )
    assert delete_response.status_code == status.HTTP_204_NO_CONTENT

    stored_product = await db_session.scalar(
        select(Product).where(Product.id == product["id"])
    )
    assert stored_product is not None
    assert stored_product.is_deleted is True
    assert stored_product.is_hidden is True

    stored_variant = await db_session.scalar(
        select(ProductVariant).where(ProductVariant.id == variant_id)
    )
    assert stored_variant is not None
    assert stored_variant.is_deleted is True

    cart_items = (
        await db_session.execute(select(CartItem).where(CartItem.product_variant_id == variant_id))
    ).scalars().all()
    assert cart_items == []

    # detail is gone for the public
    detail_response = await client.get(f"/api/v1/products/{product['slug']}")
    assert detail_response.status_code == status.HTTP_404_NOT_FOUND

@pytest.mark.anyio
async def test_admin_can_add_and_update_variant(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin_token = await create_admin(client, db_session)
    category = await create_category(client, admin_token, "Herbs")
    product = await create_product(client, admin_token, category["id"], "Mint")

    add_response = await client.post(
        f"/api/v1/products/{product['id']}/variants",
        headers=auth_header(admin_token),
        json={"label": "250g", "price": 2500, "compare_at_price": None, "stock_qty": 5},
    )
    assert add_response.status_code == status.HTTP_201_CREATED
    variant = add_response.json()
    assert variant["label"] == "250g"
    assert variant["price"] == 2500

    update_response = await client.patch(
        f"/api/v1/products/{product['id']}/variants/{variant['id']}",
        headers=auth_header(admin_token),
        json={"price": 2750, "stock_qty": 3},
    )
    assert update_response.status_code == status.HTTP_200_OK
    assert update_response.json()["price"] == 2750
    assert update_response.json()["stock_qty"] == 3

@pytest.mark.anyio
async def test_cannot_delete_the_only_remaining_variant(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin_token = await create_admin(client, db_session)
    category = await create_category(client, admin_token, "Herbs")
    product = await create_product(client, admin_token, category["id"], "Mint")
    variant_id = product["variants"][0]["id"]

    response = await client.delete(
        f"/api/v1/products/{product['id']}/variants/{variant_id}",
        headers=auth_header(admin_token),
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["detail"] == "Cannot delete the only remaining variant of a product"

@pytest.mark.anyio
async def test_admin_can_delete_one_of_multiple_variants(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin_token = await create_admin(client, db_session)
    category = await create_category(client, admin_token, "Herbs")
    product = await create_product(client, admin_token, category["id"], "Mint")

    add_response = await client.post(
        f"/api/v1/products/{product['id']}/variants",
        headers=auth_header(admin_token),
        json={"label": "250g", "price": 2500, "compare_at_price": None, "stock_qty": 5},
    )
    assert add_response.status_code == status.HTTP_201_CREATED
    extra_variant = add_response.json()

    delete_response = await client.delete(
        f"/api/v1/products/{product['id']}/variants/{extra_variant['id']}",
        headers=auth_header(admin_token),
    )
    assert delete_response.status_code == status.HTTP_204_NO_CONTENT

    stored_variant = await db_session.scalar(
        select(ProductVariant).where(ProductVariant.id == extra_variant["id"])
    )
    assert stored_variant is not None
    assert stored_variant.is_deleted is True

    detail_response = await client.get(f"/api/v1/products/{product['slug']}")
    assert detail_response.status_code == status.HTTP_200_OK
    variant_ids = [v["id"] for v in detail_response.json()["variants"]]
    assert extra_variant["id"] not in variant_ids
