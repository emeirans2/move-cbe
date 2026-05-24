from fastapi import FastAPI
from app.models.database import init_db
from app.api.routes import router

app = FastAPI(title="MOVE CBE", version="0.1.0")

@app.on_event("startup")
def startup():
    init_db()

@app.get("/health")
def health():
    return {"status": "ok", "service": "MOVE CBE"}

app.include_router(router)
