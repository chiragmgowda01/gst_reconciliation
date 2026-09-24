import calendar
from datetime import date
import json
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from models.models import Business, Invoice
from reconciliation.reconcile import reconcile
from services.auth import get_current_business

router = APIRouter(tags=["Reconciliation"])


@router.get("/reconcile")
def run_reconciliation(
    tax_period: Optional[str] = Query(None, description="Optional tax period filter in YYYY-MM format (e.g., 2026-07)"),
    current_business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    # Validate tax_period if provided (format YYYY-MM, month 01-12 only)
    start_date = None
    end_date = None
    if tax_period is not None:
        period_str = tax_period.strip()
        match = re.match(r"^(\d{4})-(0[1-9]|1[0-2])$", period_str)
        if not match:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid tax_period format. Expected YYYY-MM with month between 01 and 12 (e.g., 2026-07).",
            )
        year = int(match.group(1))
        month = int(match.group(2))
        _, last_day = calendar.monthrange(year, month)
        start_date = date(year, month, 1)
        end_date = date(year, month, last_day)

    # Read invoice data from Supabase invoices table using SQLAlchemy
    # Tenant-isolated: only invoices belonging to current_business.id
    try:
        query = select(Invoice).where(Invoice.business_id == current_business.id)
        if start_date and end_date:
            query = query.where(Invoice.invoice_date >= start_date, Invoice.invoice_date <= end_date)

        invoices = db.scalars(query).all()
    except Exception:
        # Strictly return 503 without exposing raw internal database errors
        # NEVER silently fall back to CSV files
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Reconciliation data is temporarily unavailable.",
        )

    # Partition by the 4 valid source values
    sales_reg = []
    gstr1_reg = []
    purchase_reg = []
    gstr2a_reg = []

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
    sales_df = pd.DataFrame(sales_reg) if sales_reg else pd.DataFrame(columns=cols)
    gstr1_df = pd.DataFrame(gstr1_reg) if gstr1_reg else pd.DataFrame(columns=cols)
    purchase_df = pd.DataFrame(purchase_reg) if purchase_reg else pd.DataFrame(columns=cols)
    gstr2a_df = pd.DataFrame(gstr2a_reg) if gstr2a_reg else pd.DataFrame(columns=cols)

    # Execute safe reconciliation without dropping duplicates
    sales_res_df = reconcile(sales_df, gstr1_df)
    purchase_res_df = reconcile(purchase_df, gstr2a_df)

    sales_data = json.loads(sales_res_df.to_json(orient="records")) if not sales_res_df.empty else []
    purchase_data = json.loads(purchase_res_df.to_json(orient="records")) if not purchase_res_df.empty else []

    all_records = sales_data + purchase_data
    summary = {
        "business_id": current_business.id,
        "business_name": current_business.name,
        "gstin": current_business.gstin,
        "total_records": len(all_records),
        "matched": sum(1 for r in all_records if r.get("status") == "MATCH"),
        "mismatched": sum(1 for r in all_records if r.get("status") == "MISMATCH"),
        "missing_in_gst": sum(1 for r in all_records if r.get("status") == "MISSING_IN_GST"),
        "extra_in_gst": sum(1 for r in all_records if r.get("status") == "EXTRA_IN_GST"),
    }

    return {
        "sales": sales_data,
        "purchases": purchase_data,
        "summary": summary,
    }
