import calendar
from datetime import date
import io
import re
from typing import Optional
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from models.models import Business, Invoice
# pyrefly: ignore[missing-import]
from reconciliation.reconcile import reconcile
from services.anomaly_service import get_all_anomalies
from services.auth import get_business_with_fallback, get_current_business

router = APIRouter(prefix="/reports", tags=["Reports"])


def get_business_reconciled_dfs(
    current_business: Business,
    db: Session,
    purchase_source: str = "gstr2a",
    tax_period: Optional[str] = None,
):
    norm_ps = purchase_source.strip().lower() if purchase_source else "gstr2a"
    if norm_ps not in {"gstr2a", "gstr2b"}:
        norm_ps = "gstr2a"

    start_date, end_date = None, None
    if tax_period and tax_period.strip():
        period_str = tax_period.strip()
        m = re.match(r"^(\d{4})-(0[1-9]|1[0-2])$", period_str)
        if not m:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid tax_period format '{tax_period}'. Expected YYYY-MM with month 01-12 (e.g. 2026-07).",
            )
        year, month = int(m.group(1)), int(m.group(2))
        _, last_day = calendar.monthrange(year, month)
        start_date = date(year, month, 1)
        end_date = date(year, month, last_day)

    invoices = []
    try:
        query = select(Invoice).where(Invoice.business_id == current_business.id)
        if start_date and end_date:
            query = query.where(Invoice.invoice_date >= start_date, Invoice.invoice_date <= end_date)
        invoices = db.scalars(query).all()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service unavailable. Report data cannot be retrieved.",
        )

    cols = ["invoice_no", "invoice_date", "gstin", "taxable_value", "gst_amount"]

    if invoices:
        sales_reg, gstr1_reg, purchase_reg, gstr2a_reg, gstr2b_reg = [], [], [], [], []
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
            elif inv.source == "gstr2b":
                gstr2b_reg.append(item)

        sales_df = reconcile(
            pd.DataFrame(sales_reg) if sales_reg else pd.DataFrame(columns=cols),
            pd.DataFrame(gstr1_reg) if gstr1_reg else pd.DataFrame(columns=cols),
        )
        target_purchase_gst = gstr2b_reg if norm_ps == "gstr2b" else gstr2a_reg
        purchase_df = reconcile(
            pd.DataFrame(purchase_reg) if purchase_reg else pd.DataFrame(columns=cols),
            pd.DataFrame(target_purchase_gst) if target_purchase_gst else pd.DataFrame(columns=cols),
        )
        if norm_ps == "gstr2b" and not purchase_df.empty:
            note_gstr2b = (
                "Vendor invoice recorded in purchase register is missing in GSTR-2B. "
                "Note: This does not automatically prove statutory ITC ineligibility; supplier may have filed after the 11th/13th cut-off date."
            )
            missing_mask = purchase_df["status"] == "MISSING_IN_GST"
            purchase_df.loc[missing_mask, "explanation"] = note_gstr2b
            purchase_df.loc[missing_mask, "reason"] = note_gstr2b
        return sales_df, purchase_df

    # A business with no rows for this period has no reconciliation data.
    # Synthetic fixtures are served only by the GST simulator, never metrics.
    empty_res = pd.DataFrame(columns=cols + [
        "status", "expected_taxable_value", "actual_taxable_value",
        "expected_gst_amount", "actual_gst_amount",
        "taxable_value_diff", "gst_amount_diff", "explanation", "reason"
    ])
    return empty_res, empty_res.copy()


@router.get("/summary")
def get_reports_summary(
    purchase_source: str = Query("gstr2a", description="gstr2a or gstr2b"),
    tax_period: Optional[str] = Query(None, description="Optional YYYY-MM period"),
    current_business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    norm_ps = purchase_source.strip().lower() if purchase_source else "gstr2a"
    if norm_ps not in {"gstr2a", "gstr2b"}:
        norm_ps = "gstr2a"

    try:
        has_db_records = db.scalar(
            select(Invoice.id).where(Invoice.business_id == current_business.id).limit(1)
        ) is not None
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service unavailable. Report data cannot be retrieved.",
        )

    sales_df, purchase_df = get_business_reconciled_dfs(
        current_business, db, purchase_source=norm_ps, tax_period=tax_period
    )
    purchase_label = "GSTR-2B" if norm_ps == "gstr2b" else "GSTR-2A"
    anomalies = get_all_anomalies(
        sales_df=sales_df, purchase_df=purchase_df, purchase_label=purchase_label
    )

    def calc_stats(df: pd.DataFrame):
        total = len(df)
        matched = int((df["status"] == "MATCH").sum()) if not df.empty else 0
        mismatched = int((df["status"] == "MISMATCH").sum()) if not df.empty else 0
        missing = int((df["status"] == "MISSING_IN_GST").sum()) if not df.empty else 0
        extra = int((df["status"] == "EXTRA_IN_GST").sum()) if not df.empty else 0
        match_rate = round((matched / total * 100), 1) if total > 0 else None

        taxable_total = float(df["taxable_value"].dropna().sum()) if not df.empty else 0.0
        gst_total = float(df["gst_amount"].dropna().sum()) if not df.empty else 0.0

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

    total_combined = sales_stats["total_records"] + purchase_stats["total_records"]
    matched_combined = sales_stats["matched"] + purchase_stats["matched"]

    has_reconciliation_data = total_combined > 0
    data_source_mode = "BUSINESS_DATABASE" if has_db_records else "EMPTY_BUSINESS"

    return {
        "business_id": current_business.id,
        "business_name": current_business.name,
        "purchase_source": norm_ps,
        "tax_period": tax_period,
        "data_source_mode": data_source_mode,
        "is_synthetic_demo": False,
        "has_data": has_reconciliation_data,
        "live_portal_sync": False,
        "sales_summary": sales_stats,
        "purchase_summary": purchase_stats,
        "anomalies_summary": {
            "total_exceptions": len(anomalies),
            "high_risk": sum(1 for a in anomalies if a["severity"] == "HIGH"),
            "medium_risk": sum(1 for a in anomalies if a["severity"] == "MEDIUM"),
            "low_risk": sum(1 for a in anomalies if a["severity"] == "LOW"),
        },
        "audit_health_score": round((matched_combined / total_combined) * 100, 1) if has_reconciliation_data else None,
        "audit_health_status": "available" if has_reconciliation_data else "no_data",
    }


@router.get("/export")
def export_report_csv(
    report_type: str = Query("sales", description="Target report catalogue ID"),
    purchase_source: str = Query("gstr2a", description="gstr2a or gstr2b for purchase reports"),
    tax_period: Optional[str] = Query(None, description="Optional YYYY-MM period"),
    current_business: Business = Depends(get_business_with_fallback),
    db: Session = Depends(get_db),
):
    norm_ps = purchase_source.strip().lower() if purchase_source else "gstr2a"
    if norm_ps not in {"gstr2a", "gstr2b"}:
        norm_ps = "gstr2a"

    sales_df, purchase_df = get_business_reconciled_dfs(
        current_business, db, purchase_source=norm_ps, tax_period=tax_period
    )

    output = io.StringIO()
    rt = report_type.strip().lower()
    period_suffix = f"_{tax_period.strip().replace('-', '_')}" if tax_period and tax_period.strip() else ""

    # ── 12-Item Report Catalogue ──
    # Group A: 6 Sales / Outward Supplies Reports
    if rt in {"sales", "sales_reconciliation", "sales_full"}:
        filename = f"gst_sales_reconciliation_register{period_suffix}.csv"
        sales_df.to_csv(output, index=False)
    elif rt in {"sales_matched"}:
        filename = f"gst_sales_matched_schedule{period_suffix}.csv"
        matched_df = sales_df[sales_df["status"] == "MATCH"] if not sales_df.empty else sales_df
        matched_df.to_csv(output, index=False)
    elif rt in {"sales_mismatches", "sales_variance"}:
        filename = f"gst_sales_tax_discrepancies{period_suffix}.csv"
        mismatched_df = sales_df[sales_df["status"] == "MISMATCH"] if not sales_df.empty else sales_df
        mismatched_df.to_csv(output, index=False)
    elif rt in {"sales_missing", "sales_unfiled"}:
        filename = f"gst_sales_missing_in_gstr1{period_suffix}.csv"
        missing_df = sales_df[sales_df["status"] == "MISSING_IN_GST"] if not sales_df.empty else sales_df
        missing_df.to_csv(output, index=False)
    elif rt in {"sales_extra", "sales_portal_extra"}:
        filename = f"gst_sales_extra_on_portal{period_suffix}.csv"
        extra_df = sales_df[sales_df["status"] == "EXTRA_IN_GST"] if not sales_df.empty else sales_df
        extra_df.to_csv(output, index=False)
    elif rt in {"sales_tax_liability", "sales_liability_schedule"}:
        filename = f"gst_outward_tax_liability_variance{period_suffix}.csv"
        cols_liability = [c for c in ["invoice_no", "invoice_date", "gstin", "taxable_value", "gst_amount",
                                     "expected_gst_amount", "actual_gst_amount", "gst_amount_diff", "status", "explanation"]
                         if c in sales_df.columns]
        liability_df = sales_df[cols_liability] if not sales_df.empty else sales_df
        liability_df.to_csv(output, index=False)

    # Group B: 6 Purchase / Inward ITC Reports (supports GSTR-2A and GSTR-2B)
    elif rt in {"purchases", "purchase_reconciliation", "purchase_full"}:
        filename = f"gst_purchase_{norm_ps}_reconciliation_register{period_suffix}.csv"
        purchase_df.to_csv(output, index=False)
    elif rt in {"purchase_matched"}:
        filename = f"gst_purchase_{norm_ps}_matched_itc_schedule{period_suffix}.csv"
        matched_df = purchase_df[purchase_df["status"] == "MATCH"] if not purchase_df.empty else purchase_df
        matched_df.to_csv(output, index=False)
    elif rt in {"purchase_mismatches", "purchase_variance"}:
        filename = f"gst_purchase_{norm_ps}_tax_discrepancies{period_suffix}.csv"
        mismatched_df = purchase_df[purchase_df["status"] == "MISMATCH"] if not purchase_df.empty else purchase_df
        mismatched_df.to_csv(output, index=False)
    elif rt in {"purchase_missing", "itc_at_risk"}:
        filename = f"gst_purchase_{norm_ps}_missing_itc_at_risk{period_suffix}.csv"
        missing_df = purchase_df[purchase_df["status"] == "MISSING_IN_GST"] if not purchase_df.empty else purchase_df
        missing_df.to_csv(output, index=False)
    elif rt in {"purchase_extra", "unrecorded_purchases"}:
        filename = f"gst_purchase_{norm_ps}_unbooked_vendor_invoices{period_suffix}.csv"
        extra_df = purchase_df[purchase_df["status"] == "EXTRA_IN_GST"] if not purchase_df.empty else purchase_df
        extra_df.to_csv(output, index=False)
    elif rt in {"itc_eligibility_variance", "itc_schedule"}:
        filename = f"gst_itc_eligibility_{norm_ps}_statement{period_suffix}.csv"
        cols_itc = [c for c in ["invoice_no", "invoice_date", "gstin", "taxable_value", "gst_amount",
                                "expected_gst_amount", "actual_gst_amount", "gst_amount_diff", "status", "explanation"]
                    if c in purchase_df.columns]
        itc_df = purchase_df[cols_itc] if not purchase_df.empty else purchase_df
        itc_df.to_csv(output, index=False)

    # Backward-compatible general schedules
    elif rt == "mismatches":
        filename = f"gst_all_mismatches_report{period_suffix}.csv"
        combined = pd.concat([
            sales_df[sales_df["status"] == "MISMATCH"] if not sales_df.empty else pd.DataFrame(),
            purchase_df[purchase_df["status"] == "MISMATCH"] if not purchase_df.empty else pd.DataFrame(),
        ], ignore_index=True)
        combined.to_csv(output, index=False)
    elif rt == "missing":
        filename = f"gst_all_missing_invoices_report{period_suffix}.csv"
        combined = pd.concat([
            sales_df[sales_df["status"] == "MISSING_IN_GST"] if not sales_df.empty else pd.DataFrame(),
            purchase_df[purchase_df["status"] == "MISSING_IN_GST"] if not purchase_df.empty else pd.DataFrame(),
        ], ignore_index=True)
        combined.to_csv(output, index=False)
    elif rt == "anomalies":
        filename = f"gst_audit_anomalies_exceptions{period_suffix}.csv"
        purchase_label = "GSTR-2B" if norm_ps == "gstr2b" else "GSTR-2A"
        anomalies = get_all_anomalies(
            sales_df=sales_df, purchase_df=purchase_df, purchase_label=purchase_label
        )
        df = pd.DataFrame(anomalies)
        df.to_csv(output, index=False)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid report_type '{report_type}'. Supported reports: "
                "sales, sales_matched, sales_mismatches, sales_missing, sales_extra, sales_tax_liability, "
                "purchases, purchase_matched, purchase_mismatches, purchase_missing, purchase_extra, itc_eligibility_variance, "
                "mismatches, missing, anomalies."
            ),
        )

    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )
