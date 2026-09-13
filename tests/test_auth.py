from fastapi import status
import pytest
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock
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
async def test_empty_login_felds(client: AsyncClient):
    response = await client.post(
        "/api/auth/login",
        data={"username": "", "password": ""}
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    response = await client.post(
        "/api/auth/login",
        data={}
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.anyio
async def test_wrong_email_format(client: AsyncClient):
    response = await client.post(
        "/api/auth/login",
        data={"username": "not-an-email", "password": "Pass@123456"}
    )
    assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_422_UNPROCESSABLE_CONTENT)


# test login with 'username + trailing space( )' combo
@pytest.mark.anyio
async def test_login_username_trailing_space(client: AsyncClient):
    email = "user@example.com"
    await create_test_user(client, email=email)

    response = await client.post(
        "/api/auth/login",
        data={"username": email + " ", "password": "Pass@123456"}
    )
    assert response.status_code != status.HTTP_200_OK


# test if username is case sensitive in login and registration
@pytest.mark.anyio
async def test_login_username_case_sensitivity(client: AsyncClient):
    email = "User@Example.com"
    await create_test_user(client, email=email)

    response = await client.post(
        "/api/auth/login",
        data={"username": email.lower(), "password": "Pass@123456"}
    )
    assert response.status_code in (status.HTTP_200_OK, status.HTTP_401_UNAUTHORIZED)


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
@pytest.mark.anyio
async def test_login_while_already_authenticated(client: AsyncClient):
    email = "user@example.com"
    await create_test_user(client, email=email)
    token = await login_user(client)
    header = auth_header(token)

    response = await client.post(
        "/api/auth/login",
        data={"username": email, "password": "Pass@123456"},
        headers=header
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


# ======= REGISTRATION =========

# normal registration flow
@pytest.mark.anyio
async def test_normal_registration(client: AsyncClient):
    response = await client.post(
        "/api/auth/register",
        json={
            "email": "newuser@example.com",
            "phone": "09121231235",
            "name": "New User",
            "password": "Pass@123456",
            "password_repeat": "Pass@123456"
        }
    )
    assert response.status_code == status.HTTP_201_CREATED


# register two users with same username
@pytest.mark.anyio
async def test_register_duplicate_email(client: AsyncClient):
    email = "dup@example.com"
    await create_test_user(client, email=email)

    response = await client.post(
        "/api/auth/register",
        json={
            "email": email,
            "phone": "09121231236",
            "name": "Second",
            "password": "Pass@123456",
            "password_repeat": "Pass@123456"
        }
    )
    assert response.status_code != status.HTTP_201_CREATED


# register two users with same phone number
@pytest.mark.anyio
async def test_register_duplicate_phone(client: AsyncClient):
    phone = "09121231234"
    await create_test_user(client, phone=phone)

    response = await client.post(
        "/api/auth/register",
        json={
            "email": "phone2@example.com",
            "phone": phone,
            "name": "Second",
            "password": "Pass@123456",
            "password_repeat": "Pass@123456"
        }
    )
    assert response.status_code != status.HTTP_201_CREATED


# registration with missing fields
@pytest.mark.anyio
async def test_registration_missing_fields(client: AsyncClient):
    base = {
        "email": "miss@example.com",
        "phone": "09121231237",
        "name": "Name",
        "password": "Pass@123456",
        "password_repeat": "Pass@123456"
    }
    for key in list(base.keys()):
        payload = {k: v for k, v in base.items() if k != key}
        response = await client.post("/api/auth/register", json=payload)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# registration with mismatched type fields
@pytest.mark.anyio
async def test_registration_mismatched_types(client: AsyncClient):
    response = await client.post(
        "/api/auth/register",
        json={
            "email": 123,
            "phone": 9121231234,
            "name": True,
            "password": 12345678,
            "password_repeat": 12345678
        }
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# registter 

# test registration endpoint when user is logged in
@pytest.mark.anyio
async def test_registration_while_authenticated(client: AsyncClient):
    await create_test_user(client)
    token = await login_user(client)
    header = auth_header(token)

    response = await client.post(
        "/api/auth/register",
        json={
            "email": "another@example.com",
            "phone": "09121231238",
            "name": "Another",
            "password": "Pass@123456",
            "password_repeat": "Pass@123456"
        },
        headers=header
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


# ======= FORGET PASSWORD =========

# normal forget password
@pytest.mark.anyio
async def test_forget_password_normal_flow(client: AsyncClient):
    email = "forget@example.com"
    await create_test_user(client, email=email)

    with patch(
        "app.routers.auth.send_password_reset_email", 
        new_callable=AsyncMock
    ) as mock_send:

        response = await client.post(
            "/api/auth/forget-password",
            json={"email": email}
        )
        assert response.status_code == status.HTTP_202_ACCEPTED

        mock_send.assert_awaited_once()

        kwargs = mock_send.call_args.kwargs

        print(mock_send.call_args)

        assert kwargs['to_email'] == email
        assert kwargs['name'] == "The Test User"
        assert "token" in kwargs



# TODO: forget password for email that doesn't exists


# reset password flow
@pytest.mark.anyio
async def test_forget_password_normal_flow(client: AsyncClient):
    email = "forget@example.com"
    await create_test_user(client, email=email)

    with patch(
        "app.routers.auth.send_password_reset_email", 
        new_callable=AsyncMock
    ) as mock_send:

        response = await client.post(
            "/api/auth/forget-password",
            json={"email": email}
        )
        assert response.status_code == status.HTTP_202_ACCEPTED

        mock_send.assert_awaited_once()

        kwargs = mock_send.call_args.kwargs

        print(mock_send.call_args)

        assert kwargs['to_email'] == email
        assert kwargs['name'] == "The Test User"
        assert "token" in kwargs

        token = kwargs['token']

    reset_password_response = await client.post(
        "/api/auth/reset-password",
        json = {
            "new_password": "Pass@321321",
            "password_repeat": "Pass@321321",
            "token": token
        }
    )


    assert reset_password_response.status_code == status.HTTP_200_OK
    assert reset_password_response.json()['message'] == 'Password reset successfully. You can now log in with your new password.'


# reset password with wrong token


# reset password with expired token


# test forget password endpoint when user is logged in
@pytest.mark.anyio
async def test_forget_password_while_authenticated(client: AsyncClient):
    email = "user@example.com"
    await create_test_user(client)
    token = await login_user(client)
    header = auth_header(token)

    response = await client.post(
        "/api/auth/forget-password",
        json={"email": email},
        headers=header
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST



# ======= CHANGE PASSWORD =========

# normal change password flow
@pytest.mark.anyio
async def test_change_password_normal_flow(client: AsyncClient):
    await create_test_user(client)
    token = await login_user(client)
    header = auth_header(token)

    response = await client.post(
        "/api/auth/change-password",
        json={
            "current_password": "Pass@123456",
            "new_password": "NewPass@123",
            "password_repeat": "NewPass@123"
        },
        headers=header
    )
    assert response.status_code == status.HTTP_200_OK