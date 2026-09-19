from uuid import uuid4

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category, Product, ProductVariant
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


@pytest.mark.anyio
async def test_new_guest_get_cart_sets_cookie_and_returns_empty_cart(client: AsyncClient):
	response = await client.get("/api/v1/cart")

	assert response.status_code == status.HTTP_200_OK
	assert response.json()["items"] == []
	assert response.json()["total_items"] == 0
	assert response.json()["guest_token"]
	assert "guest_cart_token" in response.cookies


@pytest.mark.anyio
async def test_guest_can_add_and_read_cart_totals(
	client: AsyncClient,
	db_session: AsyncSession,
):
	variant = await create_test_variant(db_session, price=1500, stock_qty=5)

	response = await client.post(
		"/api/v1/cart",
		json={"product_variant_id": variant.id, "qty": 2},
	)

	assert response.status_code == status.HTTP_200_OK
	cart_response = await client.get("/api/v1/cart")
	data = cart_response.json()

	assert data["total_items"] == 2
	assert data["total_price"] == 3000
	assert data["items"] == [
		{
			"id": data["items"][0]["id"],
			"product_variant_id": variant.id,
			"qty": 2,
			"product_name": "Mint",
			"variant_label": "100g",
			"price": 1500,
			"stock_qty": 5,
			"subtotal": 3000,
		}
	]


@pytest.mark.anyio
async def test_adding_existing_item_increases_quantity_and_respects_stock(
	client: AsyncClient,
	db_session: AsyncSession,
):
	variant = await create_test_variant(db_session, stock_qty=3)
	payload = {"product_variant_id": variant.id, "qty": 2}

	first_response = await client.post("/api/v1/cart", json=payload)
	second_response = await client.post("/api/v1/cart", json=payload)

	assert first_response.status_code == status.HTTP_200_OK
	assert second_response.status_code == status.HTTP_400_BAD_REQUEST
	assert "exceeds stock" in second_response.json()["detail"]


@pytest.mark.anyio
async def test_cart_rejects_unknown_variant_and_excess_quantity(
	client: AsyncClient,
	db_session: AsyncSession,
):
	variant = await create_test_variant(db_session, stock_qty=2)

	unknown_response = await client.post(
		"/api/v1/cart",
		json={"product_variant_id": 999999, "qty": 1},
	)
	excess_response = await client.post(
		"/api/v1/cart",
		json={"product_variant_id": variant.id, "qty": 3},
	)

	assert unknown_response.status_code == status.HTTP_404_NOT_FOUND
	assert unknown_response.json()["detail"] == "Product variant not found"
	assert excess_response.status_code == status.HTTP_400_BAD_REQUEST
	assert excess_response.json()["detail"] == "Not enough quantity in stock"


@pytest.mark.anyio
async def test_cart_item_can_be_updated_deleted_and_cleared(
	client: AsyncClient,
	db_session: AsyncSession,
):
	variant = await create_test_variant(db_session, price=2000, stock_qty=5)
	await client.post(
		"/api/v1/cart",
		json={"product_variant_id": variant.id, "qty": 1},
	)
	item_id = (await client.get("/api/v1/cart")).json()["items"][0]["id"]

	update_response = await client.patch(
		f"/api/v1/cart/{item_id}",
		json={"qty": 3},
	)
	assert update_response.status_code == status.HTTP_200_OK
	assert update_response.json()["total_price"] == 6000

	delete_response = await client.delete(f"/api/v1/cart/{item_id}")
	assert delete_response.status_code == status.HTTP_200_OK
	assert delete_response.json()["message"] == "Item removed from cart"

	await client.post(
		"/api/v1/cart",
		json={"product_variant_id": variant.id, "qty": 1},
	)
	clear_response = await client.delete("/api/v1/cart")
	assert clear_response.status_code == status.HTTP_200_OK
	assert clear_response.json()["items"] == []
	assert clear_response.json()["total_items"] == 0


@pytest.mark.anyio
async def test_cart_operations_require_an_identity(client: AsyncClient):
	response = await client.delete("/api/v1/cart")

	assert response.status_code == status.HTTP_404_NOT_FOUND
	assert response.json()["detail"] == "Cart not found"


@pytest.mark.anyio
async def test_guest_carts_cannot_access_each_others_items(
	client: AsyncClient,
	db_session: AsyncSession,
):
	variant = await create_test_variant(db_session)

	await client.post(
		"/api/v1/cart",
		json={"product_variant_id": variant.id, "qty": 1},
	)
	first_token = client.cookies["guest_cart_token"]

	second_client = AsyncClient(
		transport=client._transport,
		base_url="http://test",
		cookies={"guest_cart_token": "another-guest-token"},
	)
	try:
		response = await second_client.get("/api/v1/cart")
	finally:
		await second_client.aclose()

	assert first_token != "another-guest-token"
	assert response.status_code == status.HTTP_200_OK
	assert response.json()["items"] == []


@pytest.mark.anyio
async def test_guest_cart_items_merge_into_existing_authenticated_cart(
	client: AsyncClient,
	db_session: AsyncSession,
):
	guest_variant = await create_test_variant(db_session, price=1000)
	user_variant = await create_test_variant(db_session, price=2500)
	email = f"merge-existing-{uuid4().hex}@example.com"

	await create_test_user(client, email=email)
	token = await login_user(client, email=email)
	user_cart_response = await client.post(
		"/api/v1/cart",
		json={"product_variant_id": user_variant.id, "qty": 1},
		headers=auth_header(token),
	)
	assert user_cart_response.status_code == status.HTTP_200_OK

	guest_client = AsyncClient(
		transport=client._transport,
		base_url="http://test",
	)
	try:
		guest_response = await guest_client.post(
			"/api/v1/cart",
			json={"product_variant_id": guest_variant.id, "qty": 2},
		)
		assert guest_response.status_code == status.HTTP_200_OK
		guest_token = guest_client.cookies["guest_cart_token"]
	finally:
		await guest_client.aclose()

	client.cookies.clear()
	client.cookies.update({"guest_cart_token": guest_token})
	await login_user(client, email=email)

	merged_cart_response = await client.get(
		"/api/v1/cart",
		headers=auth_header(token),
	)

	assert merged_cart_response.status_code == status.HTTP_200_OK
	merged_cart = merged_cart_response.json()
	assert merged_cart["user_id"]
	assert {
		item["product_variant_id"]: item["qty"]
		for item in merged_cart["items"]
	} == {
		guest_variant.id: 2,
		user_variant.id: 1,
	}


@pytest.mark.anyio
async def test_guest_cart_becomes_authenticated_user_cart_when_user_has_no_cart(
	client: AsyncClient,
	db_session: AsyncSession,
):
	variant = await create_test_variant(db_session, price=1800)
	email = f"merge-new-{uuid4().hex}@example.com"

	await client.post(
		"/api/v1/cart",
		json={"product_variant_id": variant.id, "qty": 3},
	)
	guest_cart_before_login = (await client.get("/api/v1/cart")).json()

	await create_test_user(client, email=email)
	token = await login_user(client, email=email)
	user_cart_response = await client.get(
		"/api/v1/cart",
		headers=auth_header(token),
	)

	assert user_cart_response.status_code == status.HTTP_200_OK
	user_cart = user_cart_response.json()
	assert user_cart["id"] == guest_cart_before_login["id"]
	assert user_cart["user_id"]
	assert user_cart["guest_token"] == ""
	assert user_cart["items"][0]["product_variant_id"] == variant.id
	assert user_cart["items"][0]["qty"] == 3
