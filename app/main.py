from fastapi import FastAPI, status
from app.routers import auth

app = FastAPI()

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])

@app.get("/healthz")
def healthz():
    return {"status": "OK"}