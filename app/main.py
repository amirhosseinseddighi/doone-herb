from fastapi import FastAPI, status
from app.routers import auth
from app.routers.admin import auth as admin_auth

app = FastAPI()

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(admin_auth.router, prefix="/api/admin/auth", tags=["admin_auth"])

@app.get("/healthz")
def healthz():
    return {"status": "OK"}