import pytest
from httpx import AsyncClient
from fastapi import status
from tests.conftest import auth_header, create_test_user, login_user


# empty db return empty addresses
@pytest.mark.anyio
async def test_get_authenticated_user_addresses_empty(client: AsyncClient):
    test_user = await create_test_user(client)
    token = await login_user(client)
    test_user_authentication_headers = auth_header(token=token)

    response = await client.get("/api/addresses", headers=test_user_authentication_headers)

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == []

# guest user can't get his addresses
# having two default address