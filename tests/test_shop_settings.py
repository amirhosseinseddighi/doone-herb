import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.general import ShopSettings
from tests.conftest import auth_header, create_test_user, login_user
from tests.test_category import create_admin

# ========== TESTS ==============

@pytest.mark.anyio
async def test_admin_can_create_setting(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin_token = await create_admin(client, db_session)

    response = await client.post(
        "/api/v1/settings",
        headers=auth_header(admin_token),
        json={"key": "delivery_radius_km", "value": "15"},
    )

    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert body["key"] == "delivery_radius_km"
    assert body["value"] == "15"

    stored = await db_session.scalar(
        select(ShopSettings).where(ShopSettings.key == "delivery_radius_km")
    )
    assert stored is not None
    assert stored.value == "15"

@pytest.mark.anyio
async def test_create_setting_with_duplicate_key_returns_400(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin_token = await create_admin(client, db_session)

    first = await client.post(
        "/api/v1/settings",
        headers=auth_header(admin_token),
        json={"key": "shop_open", "value": "true"},
    )
    assert first.status_code == status.HTTP_201_CREATED

    duplicate = await client.post(
        "/api/v1/settings",
        headers=auth_header(admin_token),
        json={"key": "shop_open", "value": "false"},
    )

    assert duplicate.status_code == status.HTTP_400_BAD_REQUEST
    assert duplicate.json()["detail"] == "Setting key 'shop_open' already exists"

@pytest.mark.anyio
async def test_public_can_read_settings(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin_token = await create_admin(client, db_session)
    await client.post(
        "/api/v1/settings",
        headers=auth_header(admin_token),
        json={"key": "shop_open", "value": "true"},
    )
    await client.post(
        "/api/v1/settings",
        headers=auth_header(admin_token),
        json={"key": "delivery_radius_km", "value": "15"},
    )

    list_response = await client.get("/api/v1/settings")
    assert list_response.status_code == status.HTTP_200_OK
    keys = [s["key"] for s in list_response.json()]
    assert keys == ["delivery_radius_km", "shop_open"]

    by_key = await client.get("/api/v1/settings/shop_open")
    assert by_key.status_code == status.HTTP_200_OK
    assert by_key.json()["value"] == "true"

    missing = await client.get("/api/v1/settings/nope")
    assert missing.status_code == status.HTTP_404_NOT_FOUND
    assert missing.json()["detail"] == "Setting with key 'nope' not found"

@pytest.mark.anyio
async def test_settings_search_filters_by_key(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin_token = await create_admin(client, db_session)
    await client.post(
        "/api/v1/settings",
        headers=auth_header(admin_token),
        json={"key": "delivery_radius_km", "value": "15"},
    )
    await client.post(
        "/api/v1/settings",
        headers=auth_header(admin_token),
        json={"key": "shop_open", "value": "true"},
    )

    response = await client.get("/api/v1/settings", params={"search": "delivery"})

    assert response.status_code == status.HTTP_200_OK
    assert [s["key"] for s in response.json()] == ["delivery_radius_km"]

@pytest.mark.anyio
async def test_admin_can_update_setting(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin_token = await create_admin(client, db_session)
    created = await client.post(
        "/api/v1/settings",
        headers=auth_header(admin_token),
        json={"key": "delivery_radius_km", "value": "15"},
    )
    assert created.status_code == status.HTTP_201_CREATED

    response = await client.patch(
        "/api/v1/settings/delivery_radius_km",
        headers=auth_header(admin_token),
        json={"value": "20"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["value"] == "20"

    missing = await client.patch(
        "/api/v1/settings/nope",
        headers=auth_header(admin_token),
        json={"value": "1"},
    )
    assert missing.status_code == status.HTTP_404_NOT_FOUND

@pytest.mark.anyio
async def test_admin_can_bulk_upsert_settings(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin_token = await create_admin(client, db_session)
    await client.post(
        "/api/v1/settings",
        headers=auth_header(admin_token),
        json={"key": "shop_open", "value": "true"},
    )

    response = await client.put(
        "/api/v1/settings/bulk",
        headers=auth_header(admin_token),
        json={
            "settings": [
                {"key": "shop_open", "value": "false"},
                {"key": "delivery_radius_km", "value": "15"},
            ]
        },
    )

    assert response.status_code == status.HTTP_200_OK
    body = {s["key"]: s["value"] for s in response.json()}
    assert body == {"shop_open": "false", "delivery_radius_km": "15"}

    stored = await db_session.scalar(
        select(ShopSettings).where(ShopSettings.key == "shop_open")
    )
    assert stored is not None
    assert stored.value == "false"

@pytest.mark.anyio
async def test_admin_can_delete_setting(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin_token = await create_admin(client, db_session)
    created = await client.post(
        "/api/v1/settings",
        headers=auth_header(admin_token),
        json={"key": "shop_open", "value": "true"},
    )
    assert created.status_code == status.HTTP_201_CREATED

    delete_response = await client.delete(
        "/api/v1/settings/shop_open",
        headers=auth_header(admin_token),
    )
    assert delete_response.status_code == status.HTTP_204_NO_CONTENT

    stored = await db_session.scalar(
        select(ShopSettings).where(ShopSettings.key == "shop_open")
    )
    assert stored is None

    by_key = await client.get("/api/v1/settings/shop_open")
    assert by_key.status_code == status.HTTP_404_NOT_FOUND

@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method", "path", "json"),
    [
        ("post", "/api/v1/settings", {"key": "k", "value": "v"}),
        ("patch", "/api/v1/settings/k", {"value": "v"}),
        ("put", "/api/v1/settings/bulk", {"settings": [{"key": "k", "value": "v"}]}),
        ("delete", "/api/v1/settings/k", None),
    ],
)
async def test_unauthenticated_setting_routes_require_login(
    client: AsyncClient,
    method: str,
    path: str,
    json: dict[str, object] | None,
):
    response = await client.request(method, path, json=json)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "Not authenticated"