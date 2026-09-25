from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from models.models import Business
from routers.reports import get_business_reconciled_dfs
from services.anomaly_service import get_all_anomalies
from services.auth import get_current_business

router = APIRouter(prefix="/anomalies", tags=["Anomalies"])


@router.get("")
def list_anomalies(
    severity: Optional[str] = Query(None, description="Filter by HIGH, MEDIUM, LOW"),
    type: Optional[str] = Query(None, description="Filter by anomaly type"),
    search: Optional[str] = Query(None, description="Search by invoice number or GSTIN"),
    current_business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    sales_df, purchase_df = get_business_reconciled_dfs(current_business, db)
    all_anomalies = get_all_anomalies(sales_df=sales_df, purchase_df=purchase_df)
    if current_business.id != 1:
        all_anomalies = [a for a in all_anomalies if a.get("gstin") == current_business.gstin]

    filtered = all_anomalies
    if severity:
        sev_upper = severity.strip().upper()
        filtered = [a for a in filtered if a["severity"] == sev_upper]
    if type:
        type_upper = type.strip().upper()
        filtered = [a for a in filtered if a["type"] == type_upper]
    if search:
        s = search.strip().lower()
        filtered = [
            a for a in filtered
            if s in a["invoice_no"].lower() or s in a["gstin"].lower() or s in a["explanation"].lower()
        ]

    counts = {
        "total": len(all_anomalies),
        "high": sum(1 for a in all_anomalies if a["severity"] == "HIGH"),
        "medium": sum(1 for a in all_anomalies if a["severity"] == "MEDIUM"),
        "low": sum(1 for a in all_anomalies if a["severity"] == "LOW"),
    }

    return {
        "counts": counts,
        "total_filtered": len(filtered),
        "items": filtered,
    }
