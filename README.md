# Doone Herb — Backend API

An async FastAPI backend for an online herb shop: product browsing, guest and authenticated carts, checkout with delivery slots, order management, product reviews, image uploads, role-based admin tools, Redis caching, and rate limiting.

![Python](https://img.shields.io/badge/python-3.13+-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.141+-009688)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791)
![Redis](https://img.shields.io/badge/Redis-7-DC382D)

## Table of contents

- [Features](#features)
- [Tech stack](#tech-stack)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Development](#development)
- [API reference](#api-reference)
- [Design notes](#design-notes)
- [Project structure](#project-structure)

## Features

| Area | Highlights |
|---|---|
| **Auth & users** | Register, login (JWT bearer), forgot/reset password via email token, change password, profile update (email is immutable) |
| **Roles** | `customer`, `owner`, `manager`, `packer` — enforced per endpoint |
| **Catalog** | Categories (soft-delete, images, sorting); products (featured/hidden, slug, keyword tags); variants (price, compare-at price, SKU, stock); image upload/reorder/delete; time-bound offers with badge labels |
| **Cart** | Guest carts via token cookie, user carts, stock enforcement, automatic guest → user merge on login/signup |
| **Orders** | Checkout with server-side pricing (subtotal, delivery fee, total), delivery slots with cutoff times (Redis-cached), guarded status transitions with event history, staff fulfillment/tracking and cancellation, customer order history and order-number lookup |
| **Reviews** | Star-rated product reviews, one-level staff replies, edit/delete by author or staff, Redis-cached pages invalidated on write |
| **Shop settings** | Staff-only key/value settings with CRUD and bulk upsert |
| **Infrastructure** | Per-endpoint rate limiting, structured request logging, `/healthz`, CORS for the local frontend |

## Tech stack

| Concern | Choice |
|---|---|
| Framework | FastAPI 0.141+ (Pydantic v2) on Python 3.13+ |
| Database | PostgreSQL 16 via async SQLAlchemy 2.0 (asyncpg), Alembic migrations |
| Cache / rate limits | Redis 7 (response caching + slowapi) |
| Auth | JWT (PyJWT), argon2 hashing (pwdlib) |
| Images | Pillow, local storage under `media/` |
| Config / logging | pydantic-settings, structlog |
| Testing | pytest + httpx `AsyncClient` |
| Tooling | uv, Docker, docker-compose |

## Quick start

**Prerequisites:** Docker with Compose (recommended), or Python 3.13, [uv](https://docs.astral.sh/uv/), PostgreSQL 16 and Redis 7 for a local setup.

### With Docker

```bash
git clone <repo>
cd doone-herb
cp .env.example .env        # then edit the values (see Configuration)

docker compose up --build

# Migrations are not run automatically, so apply them once the stack is up:
docker compose exec app uv run alembic upgrade head
```

| Service | URL |
|---|---|
| API | http://localhost:8000/api/v1 |
| Interactive docs (Swagger) | http://localhost:8000/docs |
| Health check | http://localhost:8000/healthz |
| Frontend | http://localhost:7000 |

### Without Docker

```bash
cp .env.example .env        # point POSTGRES_HOST and REDIS_URL at localhost
uv sync --locked
uv run alembic upgrade head
uv run fastapi dev --host 0.0.0.0 --port 8000 --proxy-headers
```

`fastapi dev` enables auto-reload. For production, use `fastapi run` instead.

### Seed data (optional)

```bash
uv run python scripts/seed.py              # baseline data
uv run python scripts/seed_large_data.py   # large dataset for load/pagination testing
```

## Configuration

Copy `.env.example` to `.env`. The main variables:

| Variable | Description | Example |
|---|---|---|
| `ENVIRONMENT` | `DEV` or `PROD` (controls log format) | `DEV` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `APP_PORT` | App listen port | `8000` |
| `FRONTEND_URL` | Frontend origin (CORS) | `http://localhost:7000` |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Database credentials (also used by the `postgres` service) | `app` / `…` / `shopdb` |
| `POSTGRES_HOST` / `POSTGRES_PORT` | Database host and port | `postgres` / `5432` |
| `REDIS_URL` | Redis connection string | `redis://redis:6379/0` |
| `JWT_SECRET` | Secret for signing JWTs | long random string |
| `JWT_ALGORITHM` | JWT algorithm | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access token lifetime | `60` |
| `RESET_TOKEN_PREFIX` / `RESET_TOKEN_TTL_SECONDS` | Password-reset token key prefix and TTL | `pwd_reset:` / `3600` |
| `MAIL_SERVER` / `MAIL_PORT` / `MAIL_USERNAME` / `MAIL_PASSWORD` / `MAIL_FROM` | SMTP settings for reset emails | Mailtrap sandbox |
| `GUEST_CART_MAX_AGE` | Guest cart cookie lifetime (seconds) | `2592000` |
| `PRODUCT_IMAGE_UPLOAD_DIRECTORY` | Image storage path | `media/products` |
| `MAX_IMAGE_SIZE_MEGA_BYTE` | Max upload size in MB | `5` |
| `EXPORT_SECRET` | Secret used for exports | long random string |

> **Security:** never commit `.env`, and replace `JWT_SECRET` and `EXPORT_SECRET` with strong random values outside local development.

## Development

### Migrations

```bash
uv run alembic revision --autogenerate -m "describe the change"
uv run alembic upgrade head
```

### Tests

The suite needs PostgreSQL and Redis (the Compose services work).

```bash
uv sync --locked            # includes dev dependencies
uv run pytest
```

Tests cover auth, categories, products, cart, orders, addresses, reviews, shop settings, and rate limiting. `tests/conftest.py` provides the async client, DB session management, and fast password hashing.

## API reference

All routes are mounted under `/api/v1`. Full request/response schemas are available in the interactive docs at `/docs`.

### Auth — `/auth`

| Method | Path | Description |
|---|---|---|
| POST | `/register` | Create a customer account |
| POST | `/login` | Get a JWT bearer token (5/min) |
| GET / PATCH | `/me` | View / update your profile |
| POST | `/forget-password` | Request a reset email |
| POST | `/reset-password` | Reset password with token |
| POST | `/change-password` | Change password (authenticated) |
| GET | `/admin/users` | Paginated customer list (staff) |

### Catalog — `/categories`, `/products`

| Method | Path | Description |
|---|---|---|
| GET | `/categories`, `/categories/{id}` | List (searchable) / detail with products |
| POST / PATCH / DELETE | `/categories[/{id}]` | Category CRUD (staff) |
| POST / DELETE | `/categories/{id}/image` | Category image (staff) |
| GET | `/products`, `/products/{slug}` | Search/list (active offers included) / detail |
| POST / PATCH / DELETE | `/products[/{id}]` | Product CRUD (staff) |
| POST / GET / PATCH / DELETE | `/products/{id}/images` | Product gallery (staff for writes) |
| POST / PATCH / DELETE | `/products/{id}/variants[/{variant_id}]` | Variant management (staff) |

### Cart — `/cart`

| Method | Path | Description |
|---|---|---|
| GET | `/cart` | Current cart (guest cookie or user) |
| POST | `/cart` | Add item (stock-checked) |
| PATCH | `/cart/{item_id}` | Update quantity |
| DELETE | `/cart/{item_id}` · `/cart` | Remove item · clear cart |

### Orders — `/orders`

| Method | Path | Description |
|---|---|---|
| GET | `/delivery-slots` | Active delivery slots (Redis-cached) |
| POST | `/checkout` | Place an order from the cart (authenticated) |
| GET | `/orders`, `/orders/{id}`, `/orders/code/{no}` | Your orders / by ID / by order number |
| POST | `/orders/{id}/cancel` | Cancel a cancellable order |
| GET | `/admin/all` | All orders with filters (staff) |
| PATCH | `/orders/{id}/status` | Status transition, guarded (staff) |
| PATCH | `/orders/{id}/fulfillment` | Set tracking code (staff) |

### Reviews — `/reviews`

| Method | Path | Description |
|---|---|---|
| GET | `/product/{id}` | Paginated reviews (Redis-cached) |
| GET | `/me` | Your reviews |
| POST | `/` | Create a review (optionally tied to an order) |
| POST | `/{id}/reply` | Staff reply |
| PATCH / DELETE | `/{id}` | Edit / delete (author or staff) |

### Settings — `/settings`

| Method | Path | Description |
|---|---|---|
| GET | `/settings`, `/settings/{key}` | Read settings |
| POST · PUT · PATCH · DELETE | `/settings`, `/bulk`, `/{key}` | Create · bulk upsert · update · delete (staff) |

### Health

`GET /healthz` → `{"status": "OK"}`

## Design notes

- **Rate limiting.** Limits are enforced with slowapi, keyed by client IP and stored in Redis (e.g. login 5/min, register 5/hour, product listing 2/s). Because routers are mounted under a prefixed `APIRouter`, slowapi's middleware doesn't cover `/api/v1`, so each route applies its own `@limiter.limit(...)` decorator.
- **Logout.** Authentication is stateless JWT; "logout" means the token expires (`ACCESS_TOKEN_EXPIRE_MINUTES`). There is no server-side revocation.
- **Caching.** Delivery slots and review pages are cached in Redis; review caches are invalidated on write.
- **Images.** Uploads are processed with Pillow and written to `media/` (mounted as a volume in Compose so files survive restarts), capped by `MAX_IMAGE_SIZE_MEGA_BYTE`.

## Project structure

```
.
├── app/
│   ├── main.py              # App, routers, lifespan, /healthz
│   ├── middleware.py        # Access-logging middleware
│   ├── core/                # config, deps (DB/auth/cart identity), security, rate limiter, logging
│   ├── db/                  # Async engine/session, Redis client
│   ├── models/              # SQLAlchemy 2.0 models
│   ├── routers/             # v1 routes: auth, categories, products, cart, orders,
│   │                        #            addresses, reviews, settings
│   ├── schemas/             # Pydantic v2 schemas
│   └── utils/               # Image processing, SKU generation, email
├── alembic/                 # Migration env + versions
├── scripts/                 # seed.py, seed_large_data.py
├── tests/                   # pytest suite
├── frontend/                # Static frontend served by Compose
├── templates/               # HTML email templates
├── docker-compose.yml       # app, postgres, redis, frontend
├── Dockerfile               # Multi-stage build with uv
├── pyproject.toml
└── .env.example
```