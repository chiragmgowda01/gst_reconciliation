from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from models.models import Business
from routers.reports import get_business_reconciled_dfs
from services.anomaly_service import get_all_anomalies
from services.auth import get_current_business
from services.ml_service import get_ml_anomalies

router = APIRouter(prefix="/anomalies", tags=["Anomalies"])


@router.get("")
def list_anomalies(
    severity: Optional[str] = Query(None, description="Filter by HIGH, MEDIUM, LOW"),
    type: Optional[str] = Query(None, description="Filter by anomaly type"),
    search: Optional[str] = Query(None, description="Search by invoice number or GSTIN"),
    include_ml: bool = Query(True, description="Include Isolation Forest ML-flagged patterns"),
    current_business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    """
    Returns deterministic rule-based anomalies combined with optional
    Isolation Forest ML-flagged unusual transaction patterns.

    Rule-based findings:
        MISSING_IN_GST, EXTRA_IN_GST, MISMATCH, LARGE_TAX_DIFFERENCE,
        DUPLICATE_INVOICE, INVALID_GSTIN

    ML-based findings (when include_ml=true and sufficient data exists):
        ML_UNUSUAL_PATTERN — statistically unusual numerical transaction patterns.
        These do NOT constitute legal findings.
    """
    sales_df, purchase_df = get_business_reconciled_dfs(current_business, db)

    # Deterministic rule-based anomalies
    rule_anomalies = get_all_anomalies(sales_df=sales_df, purchase_df=purchase_df)
    if current_business.id != 1:
        rule_anomalies = [a for a in rule_anomalies if a.get("gstin") == current_business.gstin]

    # Isolation Forest ML anomalies (complementary, not replacement)
    ml_anomalies: list = []
    ml_meta: dict = {"ml_available": False, "reason": "ML analysis not requested."}
    if include_ml:
        ml_anomalies_raw, ml_meta = get_ml_anomalies(sales_df, purchase_df)
        if current_business.id != 1:
            ml_anomalies_raw = [
                a for a in ml_anomalies_raw if a.get("gstin") == current_business.gstin
            ]
        # De-duplicate: skip ML flag if the same invoice is already flagged by rules
        rule_invoice_nos = {a["invoice_no"] for a in rule_anomalies}
        ml_anomalies = [
            a for a in ml_anomalies_raw if a["invoice_no"] not in rule_invoice_nos
        ]

    all_anomalies = rule_anomalies + ml_anomalies

    # Apply filters
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
            if s in a["invoice_no"].lower() or s in a["gstin"].lower()
            or s in a.get("explanation", "").lower()
        ]

    counts = {
        "total": len(all_anomalies),
        "high": sum(1 for a in all_anomalies if a["severity"] == "HIGH"),
        "medium": sum(1 for a in all_anomalies if a["severity"] == "MEDIUM"),
        "low": sum(1 for a in all_anomalies if a["severity"] == "LOW"),
        "rule_based": len(rule_anomalies),
        "ml_flagged": len(ml_anomalies),
    }

    return {
        "counts": counts,
        "total_filtered": len(filtered),
        "ml_meta": ml_meta,
        "items": filtered,
    }
