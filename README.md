# Doone Herb — Backend API

A production-style, async FastAPI backend for an online herb shop. It powers product browsing, guest and authenticated shopping carts, checkout with delivery slots, order management, password reset by email, product reviews with nested replies, image uploads, role-based admin operations, Redis-backed caching, and rate limiting.

## Tech stack

- **Framework:** FastAPI 0.141+ (Pydantic v2)
- **Python:** 3.13+
- **Database:** PostgreSQL 16, async SQLAlchemy 2.0 (asyncpg driver)
- **Cache / rate-limit store:** Redis 7 (slowapi rate limits + response caching)
- **Migrations:** Alembic
- **Auth:** JWT (PyJWT), argon2 password hashing (pwdlib)
- **Images:** Pillow, local file storage under `media/`
- **Validation / config:** pydantic-settings
- **Logging:** structlog
- **Testing:** pytest + httpx AsyncClient
- **Dependency management:** uv
- **Container:** Docker + docker-compose (app, postgres, redis, frontend)

## Features

- **Authentication & users**
  - Register, login (JWT bearer), logout-by-expiry
  - Forgot / reset password (email token, server-side TTL)
  - Change password for authenticated users
  - Profile update (name/phone; email is immutable)
  - Role-based access: customer, owner, manager, packer
- **Catalog**
  - Categories (soft-delete, image upload, sorting)
  - Products (featured/hidden, slug, keyword tags, variants)
  - Product variants (price, compare-at price, SKU, stock, soft-delete)
  - Product images (upload, reorder, delete)
  - Time-bound offers with badge labels
- **Cart**
  - Guest carts (token cookie) and authenticated user carts
  - Add/update/remove items with stock enforcement
  - Guest cart merged into user cart on login/signup
- **Orders**
  - Checkout from cart with server-side pricing (subtotal, delivery fee, total)
  - Delivery slots with cutoff times, cached in Redis
  - Order status lifecycle with staff-transition guardrails and status events
  - Staff can update fulfillment/tracking and cancel orders
  - Customers can list and view their own orders (order number lookup)
- **Reviews**
  - Top-level product reviews with star rating
  - Nested staff replies (one level deep)
  - Review edit/delete by author or staff
  - Redis-cached review pages with invalidation on write
- **Shop settings**
  - Key/value shop settings (CRUD + bulk upsert), staff-only
- **Infrastructure**
  - Rate limiting per endpoint via slowapi (keyed by client IP)
  - Structured request logging (structlog)
  - Health check at `/healthz`
  - CORS configured for the local frontend

## Project structure

```
.
├── app/
│   ├── main.py              # FastAPI app, routers, lifespan, /healthz
│   ├── middleware.py        # ASGI access logging middleware
│   ├── core/
│   │   ├── config.py        # Pydantic settings (.env)
│   │   ├── deps.py          # DB session, auth roles, cart identity
│   │   ├── security.py      # JWT, password hashing, reset tokens
│   │   ├── rate_limiter.py  # slowapi limiter
│   │   └── logging_config.py
│   ├── db/
│   │   ├── database.py      # Async engine, session, Base
│   │   └── redis_cli.py     # Redis client
│   ├── models/              # SQLAlchemy 2.0 models (users, products, orders, …)
│   ├── routers/             # API v1 route modules (/auth, /categories, /products,
│   │   │                    # /cart, /orders, /addresses, /reviews, /settings)
│   ├── schemas/             # Pydantic v2 request/response schemas
│   └── utils/               # Image processing, SKU generation, email
├── alembic/                 # Alembic migration env + versions
├── scripts/                 # seed.py, seed_large_data.py
├── tests/                   # pytest suite
├── frontend/                # Static frontend served by docker-compose
├── templates/               # HTML email templates
├── docker-compose.yml       # app, postgres, redis, frontend services
├── Dockerfile               # multi-stage build with uv
├── pyproject.toml           # project metadata + dependencies
├── .env.example             # environment variable template
└── README.md
```

## Requirements

- Docker and docker-compose (recommended), or
- Python 3.13, uv, PostgreSQL 16, Redis 7 for local development

## Getting started

### 1. Clone and configure

```bash
git clone <repo>
cd doone-herb
cp .env.example .env
# edit .env with your values (see Environment variables below)
```

### 2. Run with Docker (recommended)

```bash
docker compose up --build
```

The API is then available at `http://localhost:8000/api/v1`, with a health check at `http://localhost:8000/healthz`. The frontend is served at `http://localhost:7000`.

### 3. Run locally (without Docker)

```bash
# install dependencies (production only)
uv sync --locked --no-dev

# run migrations
uv run alembic upgrade head

# start the app
uv run fastapi dev --host 0.0.0.0 --port 8000 --proxy-headers
```

`fastapi dev` enables reload and is the same command used in the Dockerfile `CMD`.

## Environment variables

Copy `.env.example` to `.env` and adjust. Key variables:

| Variable | Description | Example |
|---|---|---|
| `REDIS_URL` | Redis connection string | `redis://redis:6379/0` |
| `JWT_SECRET` | Secret for signing JWTs | strong random string |
| `JWT_ALGORITHM` | JWT algorithm | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access token lifetime | `60` |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Postgres credentials | `app` / `…` / `shopdb` |
| `POSTGRES_HOST` / `POSTGRES_PORT` | Postgres host/port | `postgres` / `5432` |
| `APP_PORT` | App listen port | `8000` |
| `ENVIRONMENT` | `DEV` or `PROD` (controls logging format) | `DEV` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `GUEST_CART_MAX_AGE` | Guest cart cookie TTL (seconds) | `2592000` |
| `RESET_TOKEN_PREFIX` / `RESET_TOKEN_TTL_SECONDS` | Password reset token settings | `pwd_reset:` / `3600` |
| `MAIL_SERVER` / `MAIL_PORT` / `MAIL_USERNAME` / `MAIL_PASSWORD` / `MAIL_FROM` | SMTP for reset emails | mailtrap sandbox |
| `EXPORT_SECRET` | Secret used for exports | random string |
| `FRONTEND_URL` | Frontend origin | `http://localhost:7000` |

Postgres credentials are also provided to the `postgres` service via `docker-compose.yml`.

## Database migrations

Migrations are managed with Alembic.

```bash
# create a new migration
uv run alembic revision --autogenerate -m "description"

# apply migrations
uv run alembic upgrade head
```

In Docker, migrations must be applied against the running `app` service (the compose file does not auto-run them on startup).

## Testing

Tests require PostgreSQL and Redis (they run against the container services by default).

```bash
# install dev dependencies
uv sync --locked

# run the test suite
uv run pytest
```

The test suite (`tests/`) covers auth, categories, products, cart, orders, addresses, reviews, shop settings, and rate limiting. `tests/conftest.py` provides the async client fixture, database session management, and fast password hashing for tests.

## API overview

All API routes are mounted under `/api/v1`.

### Authentication (`/api/v1/auth`)
- `POST /register` — create a new customer account
- `POST /login` — JWT bearer token (rate limited: 5/min)
- `GET /me` — current user profile
- `PATCH /me` — update profile
- `GET /admin/users` — paginated customer list (staff)
- `POST /forget-password` — request password reset email
- `POST /reset-password` — reset password with token
- `POST /change-password` — change password (authenticated)

### Catalog (`/api/v1/categories`, `/api/v1/products`)
- `GET /categories` — paginated active categories (search)
- `GET /categories/{id}` — category detail with products
- `POST /categories` / `PATCH` / `DELETE` — staff category CRUD
- `POST/DELETE /categories/{id}/image` — category image upload
- `GET /products` — paginated products (search, active offers loaded)
- `GET /products/{slug}` — product detail
- `POST /products` / `PATCH` / `DELETE` — staff product CRUD
- `POST/GET/PATCH/DELETE /products/{id}/images` — product gallery
- `POST/PATCH/DELETE /products/{id}/variants/{variant_id}` — variant management

### Cart (`/api/v1/cart`)
- `GET /cart` — current cart (guest token cookie or user cart)
- `POST /cart` — add item (stock-checked)
- `PATCH /cart/{item_id}` — update quantity
- `DELETE /cart/{item_id}` / `DELETE /cart` — remove item / clear cart

### Orders (`/api/v1/orders`)
- `GET /delivery-slots` — active delivery slots (Redis cached)
- `POST /checkout` — place order from cart (authenticated)
- `GET /orders` / `GET /orders/{id}` / `GET /orders/code/{no}` — customer orders
- `POST /orders/{id}/cancel` — cancel a cancellable order
- `GET /admin/all` — staff: all orders with filters
- `PATCH /orders/{id}/status` — staff status transition (guarded)
- `PATCH /orders/{id}/fulfillment` — staff: tracking code

### Reviews (`/api/v1/reviews`)
- `GET /product/{id}` — paginated reviews for a product (Redis cached)
- `GET /me` — current user's reviews
- `POST /` — create a review (optionally tied to an order)
- `POST /{id}/reply` — staff reply to a review
- `PATCH /{id}` / `DELETE /{id}` — edit/delete (author or staff)

### Settings (`/api/v1/settings`)
- `GET /settings` / `GET /settings/{key}` — read shop settings
- `POST /settings` / `PUT /bulk` / `PATCH /{key}` / `DELETE /{key}` — staff-only writes

### Health
- `GET /healthz` — `{"status": "OK"}`

## Rate limiting

Endpoints are rate limited with **slowapi**, keyed by client IP (e.g. login 5/min, register 5/hour, product listing 2/second). Limits live in Redis. Because routers are included under a prefixed `APIRouter`, slowapi's default middleware-based limiting does not cover `/api/v1` routes; each route applies its own `@limiter.limit(...)` decorator directly.

## Image uploads

Product and category images are processed with Pillow and written to `media/` (configured via `PRODUCT_IMAGE_UPLOAD_DIRECTORY`, default `media/products`). The compose file mounts `media` into the app container so uploads persist across restarts. Max size is `MAX_IMAGE_SIZE_MEGA_BYTE` (default 5 MB).