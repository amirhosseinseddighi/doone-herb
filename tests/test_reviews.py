from datetime import time
from typing import Any

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Review
from app.models.order import DeliverySlot, DeliverySlotKind
from tests.conftest import auth_header, create_test_user, login_user
from tests.test_category import create_admin, create_category, product_payload
from tests.test_orders import checkout_payload
from tests.test_products import create_product

# =========== HELPERS ============

async def create_delivery_slot(db_session: AsyncSession):
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

async def checkout_order(
    client: AsyncClient,
    db_session: AsyncSession,
    user_token: str,
    variant_id: int,
) -> dict[str, Any]:
    address_response = await client.post(
        "/api/v1/addresses",
        headers=auth_header(user_token),
        json={
            "label": "Home",
            "line": "Main St 1",
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
        headers=auth_header(user_token),
        json={"product_variant_id": variant_id, "qty": 1},
    )
    assert cart_response.status_code == status.HTTP_200_OK

    slot = await create_delivery_slot(db_session)
    checkout_response = await client.post(
        "/api/v1/orders/checkout",
        headers=auth_header(user_token),
        json=checkout_payload(address_id, slot.id),
    )
    assert checkout_response.status_code == status.HTTP_201_CREATED
    return checkout_response.json()

async def create_review(
    client: AsyncClient,
    user_token: str,
    product_id: int,
    stars: int = 5,
    text: str = "Great mint!",
    order_id: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "product_id": product_id,
        "stars": stars,
        "text": text,
    }
    if order_id is not None:
        payload["order_id"] = order_id

    response = await client.post(
        "/api/v1/reviews",
        headers=auth_header(user_token),
        json=payload,
    )
    assert response.status_code == status.HTTP_201_CREATED
    return response.json()

# ========== TESTS ==============

@pytest.mark.anyio
async def test_user_can_create_review(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin_token = await create_admin(client, db_session)
    category = await create_category(client, admin_token, "Herbs")
    product = await create_product(client, admin_token, category["id"], "Mint")

    await create_test_user(client)
    user_token = await login_user(client)

    response = await client.post(
        "/api/v1/reviews",
        headers=auth_header(user_token),
        json={"product_id": product["id"], "stars": 4, "text": "Very fresh"},
    )

    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert body["product_id"] == product["id"]
    assert body["stars"] == 4
    assert body["text"] == "Very fresh"
    assert body["parent_id"] is None
    assert body["user"]["name"] == "The Test User"
    assert body["replies"] == []

    stored = await db_session.scalar(select(Review).where(Review.id == body["id"]))
    assert stored is not None
    assert stored.stars == 4

@pytest.mark.anyio
async def test_user_cannot_review_same_product_twice(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin_token = await create_admin(client, db_session)
    category = await create_category(client, admin_token, "Herbs")
    product = await create_product(client, admin_token, category["id"], "Mint")

    await create_test_user(client)
    user_token = await login_user(client)
    await create_review(client, user_token, product["id"])

    duplicate = await client.post(
        "/api/v1/reviews",
        headers=auth_header(user_token),
        json={"product_id": product["id"], "stars": 2, "text": "Changed my mind"},
    )

    assert duplicate.status_code == status.HTTP_400_BAD_REQUEST
    assert duplicate.json()["detail"] == "You have already reviewed this product"

@pytest.mark.anyio
async def test_review_with_unknown_product_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
):
    await create_test_user(client)
    user_token = await login_user(client)

    response = await client.post(
        "/api/v1/reviews",
        headers=auth_header(user_token),
        json={"product_id": 99999, "stars": 5, "text": "Ghost review"},
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "Product not found"

@pytest.mark.anyio
async def test_review_stars_must_be_between_1_and_5(
    client: AsyncClient,
    db_session: AsyncSession,
):
    await create_test_user(client)
    user_token = await login_user(client)

    for stars in (0, 6):
        response = await client.post(
            "/api/v1/reviews",
            headers=auth_header(user_token),
            json={"product_id": 1, "stars": stars, "text": "Bad stars"},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

@pytest.mark.anyio
async def test_review_with_order_must_contain_the_product(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin_token = await create_admin(client, db_session)
    category = await create_category(client, admin_token, "Herbs")
    product = await create_product(client, admin_token, category["id"], "Mint")

    await create_test_user(client)
    user_token = await login_user(client)

    # an order that exists but doesn't contain the product
    other_product = await create_product(client, admin_token, category["id"], "Basil")
    order = await checkout_order(
        client, db_session, user_token, other_product["variants"][0]["id"]
    )

    response = await client.post(
        "/api/v1/reviews",
        headers=auth_header(user_token),
        json={
            "product_id": product["id"],
            "stars": 5,
            "text": "Never bought this",
            "order_id": order["id"],
        },
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["detail"] == "Product was not part of this order"

@pytest.mark.anyio
async def test_review_with_order_belonging_to_another_user_is_forbidden(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin_token = await create_admin(client, db_session)
    category = await create_category(client, admin_token, "Herbs")
    product = await create_product(client, admin_token, category["id"], "Mint")

    await create_test_user(client)
    user_token = await login_user(client)

    order = await checkout_order(
        client, db_session, user_token, product["variants"][0]["id"]
    )

    # a different user tries to review using the first user's order
    await create_test_user(
        client, email="intruder@example.com", phone="09121231237"
    )
    intruder_token = await login_user(client, email="intruder@example.com")

    response = await client.post(
        "/api/v1/reviews",
        headers=auth_header(intruder_token),
        json={
            "product_id": product["id"],
            "stars": 5,
            "text": "Not my order",
            "order_id": order["id"],
        },
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["detail"] == "Order does not belong to the current user"

@pytest.mark.anyio
async def test_product_reviews_are_listed_with_pagination(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin_token = await create_admin(client, db_session)
    category = await create_category(client, admin_token, "Herbs")
    product = await create_product(client, admin_token, category["id"], "Mint")

    for i in range(3):
        email = f"reviewer{i}@example.com"
        await create_test_user(client, email=email, phone=f"0912123124{i}")
        token = await login_user(client, email=email)
        await create_review(client, token, product["id"], stars=i + 1, text=f"Review {i}")

    response = await client.get(
        f"/api/v1/reviews/product/{product['id']}", params={"limit": 2}
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["total"] == 3
    assert body["limit"] == 2
    assert len(body["items"]) == 2

    page2 = await client.get(
        f"/api/v1/reviews/product/{product['id']}", params={"offset": 2, "limit": 2}
    )
    assert page2.status_code == status.HTTP_200_OK
    assert len(page2.json()["items"]) == 1

@pytest.mark.anyio
async def test_admin_can_reply_to_review(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin_token = await create_admin(client, db_session)
    category = await create_category(client, admin_token, "Herbs")
    product = await create_product(client, admin_token, category["id"], "Mint")

    await create_test_user(client)
    user_token = await login_user(client)
    review = await create_review(client, user_token, product["id"])

    reply_response = await client.post(
        f"/api/v1/reviews/{review['id']}/reply",
        headers=auth_header(admin_token),
        json={"text": "Thanks for the feedback!"},
    )

    assert reply_response.status_code == status.HTTP_201_CREATED
    reply = reply_response.json()
    assert reply["parent_id"] == review["id"]
    assert reply["stars"] is None
    assert reply["text"] == "Thanks for the feedback!"

    # the reply shows up nested under the review
    listing = await client.get(f"/api/v1/reviews/product/{product['id']}")
    assert listing.status_code == status.HTTP_200_OK
    items = listing.json()["items"]
    assert len(items) == 1
    assert [r["id"] for r in items[0]["replies"]] == [reply["id"]]

@pytest.mark.anyio
async def test_cannot_reply_to_a_reply(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin_token = await create_admin(client, db_session)
    category = await create_category(client, admin_token, "Herbs")
    product = await create_product(client, admin_token, category["id"], "Mint")

    await create_test_user(client)
    user_token = await login_user(client)
    review = await create_review(client, user_token, product["id"])

    reply_response = await client.post(
        f"/api/v1/reviews/{review['id']}/reply",
        headers=auth_header(admin_token),
        json={"text": "First reply"},
    )
    assert reply_response.status_code == status.HTTP_201_CREATED
    reply_id = reply_response.json()["id"]

    nested = await client.post(
        f"/api/v1/reviews/{reply_id}/reply",
        headers=auth_header(admin_token),
        json={"text": "Nested reply"},
    )

    assert nested.status_code == status.HTTP_400_BAD_REQUEST
    assert nested.json()["detail"] == "Cannot reply to a reply; replies only nest one level deep"

@pytest.mark.anyio
async def test_author_can_update_own_review(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin_token = await create_admin(client, db_session)
    category = await create_category(client, admin_token, "Herbs")
    product = await create_product(client, admin_token, category["id"], "Mint")

    await create_test_user(client)
    user_token = await login_user(client)
    review = await create_review(client, user_token, product["id"], stars=3)

    response = await client.patch(
        f"/api/v1/reviews/{review['id']}",
        headers=auth_header(user_token),
        json={"stars": 5, "text": "Even better after a week"},
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["stars"] == 5
    assert body["text"] == "Even better after a week"

@pytest.mark.anyio
async def test_other_user_cannot_update_or_delete_someone_elses_review(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin_token = await create_admin(client, db_session)
    category = await create_category(client, admin_token, "Herbs")
    product = await create_product(client, admin_token, category["id"], "Mint")

    await create_test_user(client)
    user_token = await login_user(client)
    review = await create_review(client, user_token, product["id"])

    await create_test_user(client, email="other@example.com", phone="09121231238")
    other_token = await login_user(client, email="other@example.com")

    update_response = await client.patch(
        f"/api/v1/reviews/{review['id']}",
        headers=auth_header(other_token),
        json={"text": "Hacked review"},
    )
    assert update_response.status_code == status.HTTP_403_FORBIDDEN
    assert update_response.json()["detail"] == "Not authorized to modify this review"

    delete_response = await client.delete(
        f"/api/v1/reviews/{review['id']}",
        headers=auth_header(other_token),
    )
    assert delete_response.status_code == status.HTTP_403_FORBIDDEN

@pytest.mark.anyio
async def test_admin_can_update_and_delete_any_review(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin_token = await create_admin(client, db_session)
    category = await create_category(client, admin_token, "Herbs")
    product = await create_product(client, admin_token, category["id"], "Mint")

    await create_test_user(client)
    user_token = await login_user(client)
    review = await create_review(client, user_token, product["id"])

    update_response = await client.patch(
        f"/api/v1/reviews/{review['id']}",
        headers=auth_header(admin_token),
        json={"text": "Moderated text"},
    )
    assert update_response.status_code == status.HTTP_200_OK
    assert update_response.json()["text"] == "Moderated text"

    delete_response = await client.delete(
        f"/api/v1/reviews/{review['id']}",
        headers=auth_header(admin_token),
    )
    assert delete_response.status_code == status.HTTP_204_NO_CONTENT

    stored = await db_session.scalar(select(Review).where(Review.id == review["id"]))
    assert stored is None

@pytest.mark.anyio
async def test_user_can_delete_own_review(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin_token = await create_admin(client, db_session)
    category = await create_category(client, admin_token, "Herbs")
    product = await create_product(client, admin_token, category["id"], "Mint")

    await create_test_user(client)
    user_token = await login_user(client)
    review = await create_review(client, user_token, product["id"])

    delete_response = await client.delete(
        f"/api/v1/reviews/{review['id']}",
        headers=auth_header(user_token),
    )
    assert delete_response.status_code == status.HTTP_204_NO_CONTENT

    stored = await db_session.scalar(select(Review).where(Review.id == review["id"]))
    assert stored is None

@pytest.mark.anyio
async def test_my_reviews_listing(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin_token = await create_admin(client, db_session)
    category = await create_category(client, admin_token, "Herbs")
    product_a = await create_product(client, admin_token, category["id"], "Mint")
    product_b = await create_product(client, admin_token, category["id"], "Basil")

    await create_test_user(client)
    user_token = await login_user(client)
    review_a = await create_review(client, user_token, product_a["id"])
    review_b = await create_review(client, user_token, product_b["id"])

    response = await client.get("/api/v1/reviews/me", headers=auth_header(user_token))

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["total"] == 2
    ids = {r["id"] for r in body["items"]}
    assert ids == {review_a["id"], review_b["id"]}

    # replies are not listed as top-level items
    reply_response = await client.post(
        f"/api/v1/reviews/{review_a['id']}/reply",
        headers=auth_header(admin_token),
        json={"text": "Reply"},
    )
    assert reply_response.status_code == status.HTTP_201_CREATED

    me_again = await client.get("/api/v1/reviews/me", headers=auth_header(user_token))
    assert me_again.status_code == status.HTTP_200_OK
    assert me_again.json()["total"] == 2
