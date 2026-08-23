from fastapi import FastAPI, status
from app.routers import auth,category
from app.routers.admin import auth as admin_auth

app = FastAPI()

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(admin_auth.router, prefix="/api/admin/auth", tags=["admin_auth"])
app.include_router(category.router, prefix="/api/categories")

@app.get("/healthz")
def healthz():
    return {"status": "OK"}