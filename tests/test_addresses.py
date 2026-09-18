import pytest
from httpx import AsyncClient
from fastapi import status
from tests.conftest import auth_header, create_test_user, login_user


# ========== AUTHENTICATION TESTS ============
# unauthenticated user get address 
@pytest.mark.anyio
async def test_unauthenticated_get_address(client: AsyncClient):
    response = await client.get("/api/v1/addresses")
    data = response.json()
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert data['detail'] == "Not authenticated"


@pytest.mark.anyio
async def test_unauthenticated_get_single_address(client: AsyncClient):
    response = await client.get("/api/v1/addresses/1")
    data = response.json()
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert data['detail'] == "Not authenticated"






# unauthenticated user create address
@pytest.mark.anyio
async def test_unauthenticated_create_address(client: AsyncClient):
    data = {
        "label": "Home",
        "line": "string",
        "unit": "string",
        "postal_code": "string",
        "phone": "string",
        "lat": 0,
        "lng": 0,
        "is_default": False
    }
    response = await client.post("/api/v1/addresses", json=data)
    data = response.json()
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert data['detail'] == "Not authenticated"


# unauthenticated user edit address
@pytest.mark.anyio
async def test_unauthenticated_edit_address(client: AsyncClient):
    data = {
        "label": "string",
        "line": "string",
        "unit": "string",
        "postal_code": "string",
        "phone": "string",
        "lat": 0,
        "lng": 0,
        "is_default": True
    }
    response = await client.patch("/api/v1/addresses/123", json=data)
    data = response.json()
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert data['detail'] == "Not authenticated"


# unauthenticated user set default address
@pytest.mark.anyio
async def test_unauthenticated_set_default_address(client: AsyncClient):
    data = {
        "label": "Home",
        "line": "string",
        "unit": "string",
        "postal_code": "string",
        "phone": "string",
        "lat": 0,
        "lng": 0,
        "is_default": False
    }
    response = await client.post("/api/v1/addresses/123/set-default", json=data)
    data = response.json()
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert data['detail'] == "Not authenticated"


# unauthenticated user delete address
@pytest.mark.anyio
async def test_unauthenticated_delete_address(client: AsyncClient):
    response = await client.delete("/api/v1/addresses/1")
    data = response.json()
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert data['detail'] == "Not authenticated"
 

# ========== AUTHORIZATION TESTS ============

# unauthoeized user get other user address
@pytest.mark.anyio
async def test_unauthorized_user_get_other_user_address(client: AsyncClient):
    await create_test_user(client)
    token1 = await login_user(client)
    headers1 = auth_header(token=token1)

    addr_resp = await client.post(
        "/api/v1/addresses",
        json={
            "label": "Home",
            "line": "User 1 St",
            "postal_code": "10000",
            "phone": "09121111111",
            "lat": 1.0,
            "lng": 1.0,
        },
        headers=headers1,
    )
    addr_id = addr_resp.json()["id"]

    await create_test_user(client, email="user2@example.com", phone="09122222222")
    token2 = await login_user(client, email="user2@example.com")
    headers2 = auth_header(token=token2)

    response = await client.get(f"/api/v1/addresses/{addr_id}", headers=headers2)
    assert response.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)



# unauthorized user set default on another user's address
@pytest.mark.anyio
async def test_unauthorized_user_set_default_other_user_address(client: AsyncClient):
    # User 1 creates an address
    await create_test_user(client, email="user1_def@example.com", phone="09121111111")
    token1 = await login_user(client, email="user1_def@example.com")
    headers1 = auth_header(token=token1)

    addr_resp = await client.post(
        "/api/v1/addresses",
        json={
            "label": "Home",
            "line": "User 1 St",
            "postal_code": "10000",
            "phone": "09121111111",
            "lat": 1.0,
            "lng": 1.0,
            "is_default": False,
        },
        headers=headers1,
    )
    addr_id = addr_resp.json()["id"]

    # User 2 attempts to set User 1's address as default
    await create_test_user(client, email="user2_def@example.com", phone="09122222222")
    token2 = await login_user(client, email="user2_def@example.com")
    headers2 = auth_header(token=token2)

    response = await client.post(
        f"/api/v1/addresses/{addr_id}/set-default", headers=headers2
    )
    assert response.status_code in (
        status.HTTP_403_FORBIDDEN,
        status.HTTP_404_NOT_FOUND,
    )


# unauthoeized user edit other user address
@pytest.mark.anyio
async def test_unauthorized_user_edit_other_user_address(client: AsyncClient):
    await create_test_user(client)
    token1 = await login_user(client)
    headers1 = auth_header(token=token1)

    addr_resp = await client.post(
        "/api/v1/addresses",
        json={
            "label": "Home",
            "line": "User 1 St",
            "postal_code": "10000",
            "phone": "09121111111",
            "lat": 1.0,
            "lng": 1.0,
        },
        headers=headers1,
    )
    addr_id = addr_resp.json()["id"]

    await create_test_user(client, email="user2@example.com", phone="09122222222")
    token2 = await login_user(client, email="user2@example.com")
    headers2 = auth_header(token=token2)

    response = await client.patch(
        f"/api/v1/addresses/{addr_id}",
        json={"label": "Hacked"},
        headers=headers2,
    )
    assert response.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)


# unauthoeized user delete other user address
@pytest.mark.anyio
async def test_unauthorized_user_delete_other_user_address(client: AsyncClient):
    await create_test_user(client)
    token1 = await login_user(client)
    headers1 = auth_header(token=token1)

    addr_resp = await client.post(
        "/api/v1/addresses",
        json={
            "label": "Home",
            "line": "User 1 St",
            "postal_code": "10000",
            "phone": "09121111111",
            "lat": 1.0,
            "lng": 1.0,
        },
        headers=headers1,
    )
    addr_id = addr_resp.json()["id"]

    await create_test_user(client, email="user2@example.com", phone="09122222222")
    token2 = await login_user(client, email="user2@example.com")
    headers2 = auth_header(token=token2)

    response = await client.delete(f"/api/v1/addresses/{addr_id}", headers=headers2)
    assert response.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)


# ========== FUNCTIONALITY TEST =============
# empty db return empty addresses
@pytest.mark.anyio
async def test_get_authenticated_user_addresses_empty(client: AsyncClient):
    test_user = await create_test_user(client)
    token = await login_user(client)
    test_user_authentication_headers = auth_header(token=token)

    response = await client.get("/api/v1/addresses", headers=test_user_authentication_headers)

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == []


# create address with empty(null) fields
@pytest.mark.anyio
async def test_create_address_with_null_required_fields(client: AsyncClient):
    await create_test_user(client)
    token = await login_user(client)
    headers = auth_header(token=token)

    payload = {
        "label": None,
        "line": None,
        "postal_code": None,
        "phone": None,
        "lat": None,
        "lng": None,
    }
    response = await client.post("/api/v1/addresses", json=payload, headers=headers)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# create address with empty JSON (don't put any keys in the json)
@pytest.mark.anyio
async def test_create_address_with_empty_json(client: AsyncClient):
    await create_test_user(client)
    token = await login_user(client)
    headers = auth_header(token=token)

    response = await client.post("/api/v1/addresses", json={}, headers=headers)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# delete address that doesn't exists
@pytest.mark.anyio
async def test_delete_address_that_does_not_exist(client: AsyncClient):
    await create_test_user(client)
    token = await login_user(client)
    headers = auth_header(token=token)

    response = await client.delete("/api/v1/addresses/99999", headers=headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND


# guest user can't get his addresses
@pytest.mark.anyio
async def test_guest_user_cannot_get_addresses(client: AsyncClient):
    response = await client.get("/api/v1/addresses")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# having two default address
@pytest.mark.anyio
async def test_having_two_default_addresses_resets_previous_default(client: AsyncClient):
    await create_test_user(client)
    token = await login_user(client)
    headers = auth_header(token=token)

    # First address set as default
    await client.post(
        "/api/v1/addresses",
        json={
            "label": "Home",
            "line": "First St",
            "postal_code": "11111",
            "phone": "09120000000",
            "lat": 0.0,
            "lng": 0.0,
            "is_default": True,
        },
        headers=headers,
    )

    # Second address set as default
    addr2 = (
        await client.post(
            "/api/v1/addresses",
            json={
                "label": "Work",
                "line": "Second St",
                "postal_code": "22222",
                "phone": "09120000000",
                "lat": 0.0,
                "lng": 0.0,
                "is_default": True,
            },
            headers=headers,
        )
    ).json()

    # Fetch all user addresses to ensure only one remains as default
    all_addresses = (await client.get("/api/v1/addresses", headers=headers)).json()
    defaults = [a for a in all_addresses if a["is_default"]]

    assert len(defaults) == 1
    assert defaults[0]["id"] == addr2["id"]


# set default on address that doesn't exist
@pytest.mark.anyio
async def test_set_default_address_not_found(client: AsyncClient):
    await create_test_user(client)
    token = await login_user(client)
    headers = auth_header(token=token)

    response = await client.post("/api/v1/addresses/99999/set-default", headers=headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND


# invalid address_id path parameter (type error)
@pytest.mark.anyio
async def test_set_default_address_invalid_id_type(client: AsyncClient):
    await create_test_user(client)
    token = await login_user(client)
    headers = auth_header(token=token)

    response = await client.post("/api/v1/addresses/invalid_id/set-default", headers=headers)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# ========== NORMAL BEHAVIOR TESTS ============

@pytest.mark.anyio
async def test_create_and_get_address_success(client: AsyncClient):
    await create_test_user(client)
    token = await login_user(client)
    headers = auth_header(token=token)

    payload = {
        "label": "Home",
        "line": "123 Main St",
        "unit": "Apt 4B",
        "postal_code": "12345",
        "phone": "09121234567",
        "lat": 35.6892,
        "lng": 51.3890,
        "is_default": False,
    }

    create_res = await client.post("/api/v1/addresses", json=payload, headers=headers)
    assert create_res.status_code == status.HTTP_201_CREATED
    data = create_res.json()
    assert data["label"] == payload["label"]
    assert "id" in data

    get_res = await client.get(f"/api/v1/addresses/{data['id']}", headers=headers)
    assert get_res.status_code == status.HTTP_200_OK
    assert get_res.json()["id"] == data["id"]


@pytest.mark.anyio
async def test_update_address_success(client: AsyncClient):
    await create_test_user(client)
    token = await login_user(client)
    headers = auth_header(token=token)

    created = (
        await client.post(
            "/api/v1/addresses",
            json={
                "label": "Home",
                "line": "Old Street",
                "postal_code": "00000",
                "phone": "09120000000",
                "lat": 0.0,
                "lng": 0.0,
            },
            headers=headers,
        )
    ).json()

    update_res = await client.patch(
        f"/api/v1/addresses/{created['id']}",
        json={"label": "Work", "unit": "Suite 100"},
        headers=headers,
    )

    assert update_res.status_code == status.HTTP_200_OK
    updated_data = update_res.json()
    assert updated_data["label"] == "Work"
    assert updated_data["unit"] == "Suite 100"


@pytest.mark.anyio
async def test_delete_address_success(client: AsyncClient):
    await create_test_user(client)
    token = await login_user(client)
    headers = auth_header(token=token)

    created = (
        await client.post(
            "/api/v1/addresses",
            json={
                "label": "Temp",
                "line": "To Delete",
                "postal_code": "00000",
                "phone": "09120000000",
                "lat": 0.0,
                "lng": 0.0,
            },
            headers=headers,
        )
    ).json()

    del_res = await client.delete(f"/api/v1/addresses/{created['id']}", headers=headers)
    assert del_res.status_code == status.HTTP_204_NO_CONTENT

    get_res = await client.get(f"/api/v1/addresses/{created['id']}", headers=headers)
    assert get_res.status_code == status.HTTP_404_NOT_FOUND



# successfully set an existing address as default and verify previous default is unset
@pytest.mark.anyio
async def test_set_default_address_success(client: AsyncClient):
    await create_test_user(client)
    token = await login_user(client)
    headers = auth_header(token=token)

    # 1. Create Address A (currently default)
    addr_a = (
        await client.post(
            "/api/v1/addresses",
            json={
                "label": "Home",
                "line": "First St",
                "postal_code": "11111",
                "phone": "09120000000",
                "lat": 0.0,
                "lng": 0.0,
                "is_default": True,
            },
            headers=headers,
        )
    ).json()

    # 2. Create Address B (not default)
    addr_b = (
        await client.post(
            "/api/v1/addresses",
            json={
                "label": "Work",
                "line": "Second St",
                "postal_code": "22222",
                "phone": "09120000000",
                "lat": 0.0,
                "lng": 0.0,
                "is_default": False,
            },
            headers=headers,
        )
    ).json()

    # 3. Call endpoint to set Address B as default
    response = await client.post(
        f"/api/v1/addresses/{addr_b['id']}/set-default", headers=headers
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == addr_b["id"]
    assert data["is_default"] is True

    # 4. Verify only Address B remains marked as default across all user addresses
    all_addresses = (await client.get("/api/v1/addresses", headers=headers)).json()
    
    addr_a_refreshed = next(a for a in all_addresses if a["id"] == addr_a["id"])
    addr_b_refreshed = next(a for a in all_addresses if a["id"] == addr_b["id"])

    assert addr_a_refreshed["is_default"] is False
    assert addr_b_refreshed["is_default"] is True


# calling set-default on an address that is already default returns 200 OK without errors
@pytest.mark.anyio
async def test_set_default_address_idempotent(client: AsyncClient):
    await create_test_user(client)
    token = await login_user(client)
    headers = auth_header(token=token)

    addr = (
        await client.post(
            "/api/v1/addresses",
            json={
                "label": "Home",
                "line": "Main St",
                "postal_code": "12345",
                "phone": "09120000000",
                "lat": 0.0,
                "lng": 0.0,
                "is_default": True,
            },
            headers=headers,
        )
    ).json()

    # Call endpoint on already-default address
    response = await client.post(
        f"/api/v1/addresses/{addr['id']}/set-default", headers=headers
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["is_default"] is True