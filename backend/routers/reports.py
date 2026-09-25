import io
from typing import Optional
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from models.models import Business, Invoice
from reconciliation.reconcile import reconcile
from services.anomaly_service import get_all_anomalies
from services.auth import get_current_business

router = APIRouter(prefix="/reports", tags=["Reports"])


def get_business_reconciled_dfs(current_business: Business, db: Session):
    try:
        invoices = db.scalars(select(Invoice).where(Invoice.business_id == current_business.id)).all()
    except Exception:
        invoices = []

    if invoices:
        sales_reg, gstr1_reg, purchase_reg, gstr2a_reg = [], [], [], []
        for inv in invoices:
            item = {
                "invoice_no": inv.invoice_no,
                "invoice_date": inv.invoice_date.isoformat() if inv.invoice_date else "",
                "gstin": inv.gstin,
                "taxable_value": inv.taxable_value,
                "gst_amount": inv.gst_amount,
            }
            if inv.source == "sales_register":
                sales_reg.append(item)
            elif inv.source == "gstr1":
                gstr1_reg.append(item)
            elif inv.source == "purchase_register":
                purchase_reg.append(item)
            elif inv.source == "gstr2a":
                gstr2a_reg.append(item)

        cols = ["invoice_no", "invoice_date", "gstin", "taxable_value", "gst_amount"]
        sales_df = reconcile(pd.DataFrame(sales_reg) if sales_reg else pd.DataFrame(columns=cols),
                             pd.DataFrame(gstr1_reg) if gstr1_reg else pd.DataFrame(columns=cols))
        purchase_df = reconcile(pd.DataFrame(purchase_reg) if purchase_reg else pd.DataFrame(columns=cols),
                                pd.DataFrame(gstr2a_reg) if gstr2a_reg else pd.DataFrame(columns=cols))
        return sales_df, purchase_df

    # Fallback to CSV files
    sales_df = reconcile("sales_register.csv", "gstr1.csv")
    purchase_df = reconcile("purchase_register.csv", "gstr2a.csv")

    if current_business.id != 1:
        s_matches = sales_df[sales_df["gstin"] == current_business.gstin]
        p_matches = purchase_df[purchase_df["gstin"] == current_business.gstin]
        sales_df = s_matches if not s_matches.empty else sales_df
        purchase_df = p_matches if not p_matches.empty else purchase_df

    return sales_df, purchase_df


@router.get("/summary")
def get_reports_summary(
    current_business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    sales_df, purchase_df = get_business_reconciled_dfs(current_business, db)
    anomalies = [
        a for a in get_all_anomalies(sales_df=sales_df, purchase_df=purchase_df)
        if current_business.id == 1 or a.get("gstin") == current_business.gstin
    ]

    def calc_stats(df: pd.DataFrame):
        total = len(df)
        matched = int((df["status"] == "MATCH").sum())
        mismatched = int((df["status"] == "MISMATCH").sum())
        missing = int((df["status"] == "MISSING_IN_GST").sum())
        extra = int((df["status"] == "EXTRA_IN_GST").sum())
        match_rate = round((matched / total * 100), 1) if total > 0 else 0.0

        taxable_total = float(df["taxable_value"].dropna().sum())
        gst_total = float(df["gst_amount"].dropna().sum())

        return {
            "total_records": total,
            "matched": matched,
            "mismatched": mismatched,
            "missing_in_gst": missing,
            "extra_in_gst": extra,
            "match_rate_percentage": match_rate,
            "taxable_total": round(taxable_total, 2),
            "gst_total": round(gst_total, 2),
        }

    sales_stats = calc_stats(sales_df)
    purchase_stats = calc_stats(purchase_df)

    return {
        "business_id": current_business.id,
        "business_name": current_business.name,
        "sales_summary": sales_stats,
        "purchase_summary": purchase_stats,
        "anomalies_summary": {
            "total_exceptions": len(anomalies),
            "high_risk": sum(1 for a in anomalies if a["severity"] == "HIGH"),
            "medium_risk": sum(1 for a in anomalies if a["severity"] == "MEDIUM"),
            "low_risk": sum(1 for a in anomalies if a["severity"] == "LOW"),
        },
        "audit_health_score": round(
            ((sales_stats["matched"] + purchase_stats["matched"]) /
             max(1, (sales_stats["total_records"] + purchase_stats["total_records"]))) * 100,
            1
        )
    }


@router.get("/export")
def export_report_csv(
    report_type: str = Query("sales", description="sales, purchases, mismatches, missing, anomalies"),
    current_business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    sales_df, purchase_df = get_business_reconciled_dfs(current_business, db)

    output = io.StringIO()
    filename = f"gst_{report_type}_report.csv"

    if report_type == "sales":
        sales_df.to_csv(output, index=False)
    elif report_type == "purchases":
        purchase_df.to_csv(output, index=False)
    elif report_type == "mismatches":
        combined = pd.concat([
            sales_df[sales_df["status"] == "MISMATCH"],
            purchase_df[purchase_df["status"] == "MISMATCH"]
        ])
        combined.to_csv(output, index=False)
    elif report_type == "missing":
        combined = pd.concat([
            sales_df[sales_df["status"] == "MISSING_IN_GST"],
            purchase_df[purchase_df["status"] == "MISSING_IN_GST"]
        ])
        combined.to_csv(output, index=False)
    elif report_type == "anomalies":
        anomalies = get_all_anomalies(sales_df=sales_df, purchase_df=purchase_df)
        df = pd.DataFrame(anomalies)
        df.to_csv(output, index=False)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid report_type. Use sales, purchases, mismatches, missing, or anomalies",
        )

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
