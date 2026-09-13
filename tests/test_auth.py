from fastapi import status
import pytest
from httpx import AsyncClient
from tests.conftest import create_test_user, login_user, auth_header


# ========= LOGIN =============
@pytest.mark.anyio
async def test_user_wrong_password_login(client: AsyncClient):

    email: str = "user@example.com"
    user = await create_test_user(client, email = email)

    login_data = {
        "username": email,
        "password": "Wrong password"
    }

    response = await client.post(
        "/api/auth/login",
        data = login_data
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED, f"login with wrong password didn't return 401"
    assert response.json()['detail'] == 'Wrong Username or Password'


@pytest.mark.anyio
async def test_empty_login_felds():
    ...


@pytest.mark.anyio
async def test_wrong_email_format():
    ...

# test login with 'username + trailing space( )' combo
# test if username is case sensitive in login and registration


# test /api/auth/me with unauthenticated user
@pytest.mark.anyio
async def test_unauthenticated_get_current_user_info(client: AsyncClient):

    response = await client.get(
        "/api/auth/me"
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()['detail'] == 'Not authenticated'


# ======= AFTER LOGIN ==========

# test /api/auth/me
@pytest.mark.anyio
async def test_get_current_user_info(client: AsyncClient):

    email = "user@example.com"
    user = await create_test_user(client, email=email)
    token = await login_user(client)
    header = auth_header(token)


    response = await client.get(
        "/api/auth/me",
        headers=header
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()['email'] == email

# test login endpoint when user is logged in


# ======= REGISTRATION =========

# normal registration flow

# register two users with same username

# register two users with same phone number

# registration with missing fields

# registration with mismatched type fields

# registter 

# test registration endpoint when user is logged in


# ======= FORGET PASSWORD =========

# normal reset password flow

# test forget password endpoint when user is logged in


# ======= CHANGE PASSWORD =========

# normal change password flow