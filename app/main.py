from fastapi import FastAPI, Request, status
from fastapi.staticfiles import StaticFiles
from app.routers import addresses, cart, category, auth, orders, products
from fastapi.middleware.cors import CORSMiddleware
from fastapi import APIRouter

origins = [
    "http://localhost.tiangolo.com",
    "https://localhost.tiangolo.com",
    "http://localhost",
    "http://127.0.0.1:7000",
    "http://localhost:7000"
]

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_v1 = APIRouter(prefix="/api/v1",tags=["API Version 1"])

api_v1.include_router(auth.router)
api_v1.include_router(category.router)
api_v1.include_router(products.router)
api_v1.include_router(cart.router)
api_v1.include_router(addresses.router)
api_v1.include_router(orders.router)


app.include_router(api_v1)

@app.get("/healthz")
def healthz():
    return {"status": "OK"}