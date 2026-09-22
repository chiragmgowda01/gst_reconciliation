from fastapi import FastAPI

from database import engine
from models.base import Base
from models import models

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="GST Reconciliation System"
)


@app.get("/")
def home():
    return {
        "message": "GST Reconciliation API is running"
    }


@app.get("/health")
def health():
    return {
        "status": "ok"
    }