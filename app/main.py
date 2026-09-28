from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.staticfiles import StaticFiles
import structlog
from sqlalchemy import text
from app.middleware import ASGILoggingMiddleware
from app.routers import (
    addresses,
    cart,
    category,
    auth,
    orders,
    products,
    shop_settings,
    review
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi import APIRouter
from app.core.logging_config import setup_logging
from app.core.config import settings

origins = [
    "http://localhost.tiangolo.com",
    "https://localhost.tiangolo.com",
    "http://localhost",
    "http://127.0.0.1:7000",
    "http://localhost:7000"
]
logger = structlog.get_logger()

@asynccontextmanager
async def lifespan(app: FastAPI):
    IS_DEV = settings.ENVIRONMENT != "PROD"
    setup_logging(is_dev=IS_DEV)

    logger.info("Application setup completed! starting server...")

    yield

    logger.info("Application is shutting down!")





app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(ASGILoggingMiddleware)

api_v1 = APIRouter(prefix="/api/v1")

api_v1.include_router(auth.router)
api_v1.include_router(category.router)
api_v1.include_router(products.router)
api_v1.include_router(cart.router)
api_v1.include_router(addresses.router)
api_v1.include_router(orders.router)
api_v1.include_router(shop_settings.router)
api_v1.include_router(review.router)

app.include_router(api_v1)

@app.get("/healthz")
def healthz():
    return {"status": "OK"}