from fastapi import FastAPI
from routers.reconciliation import router as reconciliation_router

from fastapi.middleware.cors import CORSMiddleware
from routers.gstr3b import router as gstr3b_router
from database import engine
from models.base import Base
from models import models

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="GST Reconciliation System"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(reconciliation_router)
app.include_router(gstr3b_router)
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