"""Rate limiting tests.

Limits are enforced by ``@limiter.limit(...)`` decorators on each route. There
is deliberately no ``SlowAPIMiddleware`` (it cannot resolve routes registered
through ``include_router`` on the installed FastAPI/Starlette) and no
``default_limits``.

Important consequence of the decorator approach: slowapi wraps the *route
function*, so a limit is checked only once FastAPI has resolved the request's
dependencies and reached the endpoint.  A request that fails a dependency
(a 401 from an auth guard, a 422 from body validation) is therefore rejected
*before* the counter runs and does not consume budget.  See
``test_requests_rejected_by_a_dependency_are_not_counted``.

Every test uses a unique client host.  slowapi keys counters by
``request.client.host``, so each test gets its own Redis bucket and the
counters expire on their own TTL -- no Redis cleanup is needed.
"""

import uuid

import anyio
import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

from app.core.deps import get_db
from app.core.rate_limiter import limiter
from app.main import app
from app.routers import auth, category, orders, products, shop_settings


def _unique_host() -> str:
    """A client host nobody else in this run (or a previous one) has used."""
    return f"rl-test-{uuid.uuid4().hex}"


def _make_client(host: str) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app, client=(host, 12345)),
        base_url="http://test",
    )


@pytest.fixture
async def make_rl_client(db_session):
    """Factory for clients with a unique source IP, wired to the test database.

    ``db_session`` (from conftest) creates the schema and rolls back per test;
    the dependency override mirrors the conftest ``client`` fixture, except the
    ASGI client address is randomised so each test gets its own rate-limit
    bucket.
    """
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    clients: list[AsyncClient] = []

    def _factory(host: str | None = None) -> AsyncClient:
        client = _make_client(host or _unique_host())
        clients.append(client)
        return client

    try:
        yield _factory
    finally:
        for client in clients:
            await client.aclose()
        app.dependency_overrides.clear()


def _iter_routes(routes):
    """Yield real endpoints, descending into lazily-included routers.

    FastAPI 0.14x hides everything registered via ``include_router`` behind a
    single ``_IncludedRouter`` placeholder that has no ``.endpoint``; the real
    routes are reachable through its ``effective_candidates()``.
    """
    for route in routes:
        candidates = getattr(route, "effective_candidates", None)
        if callable(candidates):
            yield from _iter_routes(candidates())
            continue
        sub = getattr(route, "routes", None)
        if sub:
            yield from _iter_routes(sub)
        if getattr(route, "endpoint", None) is not None:
            yield route


def _registered_limits(func):
    return limiter._route_limits.get(f"{func.__module__}.{func.__name__}", [])


def _amount(func) -> int:
    limits = _registered_limits(func)
    assert len(limits) == 1, f"{func.__name__} should have exactly one static limit"
    return limits[0].limit.amount


def _api_endpoints():
    for route in _iter_routes(app.routes):
        if (getattr(route, "path", "") or "").startswith("/api/v1"):
            yield route


EXPECTED_API_ROUTE_COUNT = 59


def test_every_api_route_is_decorated():
    """No /api/v1 route may be left without a @limiter.limit decorator."""
    missing = []
    seen = 0

    for route in _api_endpoints():
        seen += 1
        endpoint = route.endpoint
        if not _registered_limits(endpoint):
            methods = ",".join(sorted(getattr(route, "methods", None) or []))
            missing.append(f"{methods} {route.path} ({endpoint.__module__}.{endpoint.__name__})")

    assert missing == [], (
        "These routes have no rate limit (add @limiter.limit below the router "
        f"decorator, above the def): {missing}"
    )
    assert seen == EXPECTED_API_ROUTE_COUNT, (
        f"API surface changed: {seen} routes found, expected "
        f"{EXPECTED_API_ROUTE_COUNT}. If you added a route, give it a limit and "
        "bump EXPECTED_API_ROUTE_COUNT."
    )


def test_limits_are_positive():
    for route in _api_endpoints():
        for limit in _registered_limits(route.endpoint):
            assert limit.limit.amount > 0, f"{route.path} has a non-positive limit"


def test_limiter_has_no_global_default_limit():
    """A default limit would silently throttle *every* route, including /healthz."""
    assert limiter._default_limits == []
    assert limiter._application_limits == []
    assert limiter._route_limits, "no route limits registered at all"


@pytest.mark.anyio
async def test_healthz_is_not_rate_limited():
    async with _make_client(_unique_host()) as client:
        for _ in range(15):
            assert (await client.get("/healthz")).status_code == status.HTTP_200_OK


def test_healthz_has_no_route_limit():
    endpoint = next(
        (r.endpoint for r in _iter_routes(app.routes) if r.path == "/healthz"), None
    )
    assert endpoint is not None
    assert _registered_limits(endpoint) == []


ENFORCED_CASES = [
    ("GET", "/api/v1/categories", category.get_all_categories, {}, status.HTTP_200_OK),
    ("GET", "/api/v1/products", products.get_all_products, {}, status.HTTP_200_OK),
    ("GET", "/api/v1/settings", shop_settings.get_all_settings, {}, status.HTTP_200_OK),
    ("GET", "/api/v1/orders/delivery-slots", orders.list_delivery_slots, {}, status.HTTP_200_OK),
    (
        "POST",
        "/api/v1/auth/login",
        auth.login,
        {"data": {"username": "nobody@example.com", "password": "wrong-password"}},
        status.HTTP_401_UNAUTHORIZED,
    ),
    (
        "POST",
        "/api/v1/auth/forget-password",
        auth.forget_password,
        {"json": {"email": "nobody@example.com"}},
        status.HTTP_202_ACCEPTED,
    ),
]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "method,path,func,kwargs,allowed_status",
    ENFORCED_CASES,
    ids=[f"{m} {p}" for m, p, _, _, _ in ENFORCED_CASES],
)
async def test_route_blocks_once_limit_is_reached(
    make_rl_client, method, path, func, kwargs, allowed_status
):
    """The route serves up to `amount` requests, then returns 429."""
    amount = _amount(func)
    client = make_rl_client()

    for i in range(amount):
        response = await client.request(method, path, **kwargs)
        assert response.status_code != status.HTTP_429_TOO_MANY_REQUESTS, (
            f"{method} {path} throttled early, on request {i + 1} of {amount}"
        )
        assert response.status_code == allowed_status, (
            f"{method} {path} returned {response.status_code}, "
            f"expected {allowed_status}"
        )

    blocked = await client.request(method, path, **kwargs)
    assert blocked.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert blocked.json()["detail"]


@pytest.mark.anyio
async def test_hourly_limit_blocks_after_its_window_budget(make_rl_client):
    """A per-hour limit goes through the same code path as a per-second one."""
    assert str(_registered_limits(auth.forget_password)[0].limit) == "3 per 1 hour"
    client = make_rl_client()

    for _ in range(3):
        response = await client.post(
            "/api/v1/auth/forget-password", json={"email": "nobody@example.com"}
        )
        assert response.status_code == status.HTTP_202_ACCEPTED

    blocked = await client.post(
        "/api/v1/auth/forget-password", json={"email": "nobody@example.com"}
    )
    assert blocked.status_code == status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.anyio
async def test_limit_is_per_client_ip(make_rl_client):
    """Exhausting one client must not affect another."""
    amount = _amount(auth.login)
    creds = {"data": {"username": "nobody@example.com", "password": "wrong-password"}}
    first, second = make_rl_client(), make_rl_client()

    for _ in range(amount):
        assert (await first.post("/api/v1/auth/login", **creds)).status_code != 429
    assert (await first.post("/api/v1/auth/login", **creds)).status_code == 429

    for _ in range(amount):
        response = await second.post("/api/v1/auth/login", **creds)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.anyio
async def test_limit_is_per_endpoint(make_rl_client):
    """Exhausting one endpoint must not block a different endpoint."""
    amount = _amount(auth.login)
    creds = {"data": {"username": "nobody@example.com", "password": "wrong-password"}}
    client = make_rl_client()

    for _ in range(amount + 1):
        await client.post("/api/v1/auth/login", **creds)
    assert (await client.post("/api/v1/auth/login", **creds)).status_code == 429

    response = await client.post(
        "/api/v1/auth/forget-password", json={"email": "nobody@example.com"}
    )
    assert response.status_code == status.HTTP_202_ACCEPTED


@pytest.mark.anyio
async def test_window_resets(make_rl_client):
    """A per-second window opens again once it elapses."""
    assert str(_registered_limits(auth.login)[0].limit) == "5 per 1 minute"
    assert str(_registered_limits(category.get_all_categories)[0].limit) == "2 per 1 second"
    client = make_rl_client()

    for _ in range(2):
        assert (await client.get("/api/v1/categories")).status_code != 429
    assert (await client.get("/api/v1/categories")).status_code == 429

    await anyio.sleep(1.1)

    response = await client.get("/api/v1/categories")
    assert response.status_code != status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.anyio
async def test_counters_are_shared_through_redis(make_rl_client):
    """Counters live in Redis, so a new connection from the same host shares them."""
    host = _unique_host()
    amount = _amount(category.get_all_categories)

    first = make_rl_client(host)
    for _ in range(amount):
        assert (await first.get("/api/v1/categories")).status_code != 429

    second = make_rl_client(host)
    assert (await second.get("/api/v1/categories")).status_code == 429


@pytest.mark.anyio
async def test_requests_rejected_by_a_dependency_are_not_counted(make_rl_client):
    """Documents a caveat of the decorator approach.

    The limit wraps the route function, so FastAPI runs dependencies first.  A
    request an auth guard rejects never reaches the counter and is not
    throttled.  Swap to middleware-based limiting if unauthenticated traffic to
    guarded routes must also be capped.
    """
    client = make_rl_client()
    for _ in range(20):
        response = await client.get("/api/v1/addresses")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.status_code != status.HTTP_429_TOO_MANY_REQUESTS
