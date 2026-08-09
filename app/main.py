from fastapi import FastAPI, status

app = FastAPI()

@app.get("/healthz")
def healthz():
    return {"status": "OK"}