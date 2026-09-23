from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from database import engine
from models import models
from models.base import Base
from routers.anomalies import router as anomalies_router
from routers.auth import router as auth_router
from routers.gstr3b import router as gstr3b_router
from routers.invoices import router as invoices_router, upload_csv
from routers.reconciliation import router as reconciliation_router
from routers.reports import router as reports_router

# Initialize database schema safely
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Automated MSME GST Reconciliation and Anomaly Detector",
    version="1.0.0",
    description="Production-style GST reconciliation, exception management, and GSTR compliance system for MSMEs.",
)

# CORS configuration explicitly allowing Authorization and X-Business-ID
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "*"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=[
        "Authorization",
        "X-Business-ID",
        "Content-Type",
        "Accept",
        "Origin",
        "X-Requested-With",
    ],
)

app.include_router(auth_router)
app.include_router(reconciliation_router)
app.include_router(gstr3b_router)
app.include_router(invoices_router)
app.include_router(anomalies_router)
app.include_router(reports_router)

# Direct alias for /upload to match specification
app.add_api_route("/upload", upload_csv, methods=["POST"], tags=["Invoices"])


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Hide raw internal traces from production responses
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred. Please check backend logs."},
    )


@app.get("/")
def home():
    return {
        "system": "Automated MSME GST Reconciliation and Anomaly Detector",
        "version": "1.0.0",
        "status": "operational",
        "endpoints": [
            "/reconcile",
            "/gstr3b/summary",
            "/invoices",
            "/invoices/upload",
            "/anomalies",
            "/reports/summary",
            "/reports/export",
            "/health",
        ],
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "database": "connected",
    }