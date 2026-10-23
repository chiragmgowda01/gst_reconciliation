"""
GSTR-3B Router
==============
Provides:
  GET /gstr3b/summary  — GSTR-3B period summary (existing, DB-backed)
  GET /gstr3b/cross-form — Cross-form comparison between GSTR-1/2A and GSTR-3B

Cross-form analysis compares compatible aggregated figures only:
  - GSTR-1 outward-supply total (Sales Register + GSTR-1 reconciled tax) vs
    GSTR-3B Table 3.1 output tax
  - GSTR-2A ITC total vs GSTR-3B Table 4(A) eligible ITC

Differences are reported as investigation recommendations, NOT as confirmed errors.
GSTR-2B is not yet available in the dataset; its absence is documented explicitly.
"""

from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from models.models import Business, Invoice
from services.auth import get_current_business

router = APIRouter(prefix="/gstr3b", tags=["GSTR-3B"])

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"


def _load_gstr3b_row(tax_period: Optional[str]):
    """Load GSTR-3B CSV summary for the given period, or the first available row."""
    try:
        df = pd.read_csv(DATA / "gstr3b.csv")
        if df.empty:
            return None, None
        if tax_period:
            match = df[df["tax_period"].astype(str) == tax_period.strip()]
            if not match.empty:
                return match.iloc[0], tax_period.strip()
        row = df.iloc[0]
        return row, str(row["tax_period"])
    except Exception:
        return None, None


def _get_db_invoice_sums(business_id: int, db: Session, start_date=None, end_date=None):
    """
    Sum taxable_value and gst_amount by source type for the given business.
    Returns dict: source -> {taxable_value: float, gst_amount: float}
    """
    query = select(Invoice).where(Invoice.business_id == business_id)
    if start_date and end_date:
        query = query.where(
            Invoice.invoice_date >= start_date,
            Invoice.invoice_date <= end_date,
        )
    invoices = db.scalars(query).all()

    sums: dict = {}
    for inv in invoices:
        src = inv.source
        if src not in sums:
            sums[src] = {"taxable_value": 0.0, "gst_amount": 0.0, "count": 0}
        sums[src]["taxable_value"] += inv.taxable_value or 0
        sums[src]["gst_amount"] += inv.gst_amount or 0
        sums[src]["count"] += 1
    return sums


@router.get("/summary")
def gstr3b_summary(
    tax_period: Optional[str] = Query(None, description="Optional tax period filter YYYY-MM"),
    current_business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    """
    Returns GSTR-3B summary figures for the given tax period.
    Data is sourced from the GSTR-3B CSV file (represents filed return values).
    For multi-business setups, only business_id == 1 has sample data; others
    return zeros to prevent fabricating values for tenants with no GSTR-3B file.
    """
    row, period = _load_gstr3b_row(tax_period)
    resolved_period = period or (tax_period.strip() if tax_period else "2026-07")

    if row is None or current_business.id != 1:
        # Do not fabricate values for businesses without GSTR-3B data
        return {
            "business_id": current_business.id,
            "tax_period": resolved_period,
            "output_tax": 0.0,
            "eligible_itc": 0.0,
            "itc_reversed": 0.0,
            "net_itc": 0.0,
            "data_available": False,
            "note": "No GSTR-3B filing data available for this business. Upload GSTR-3B CSV to enable analysis.",
        }

    return {
        "business_id": current_business.id,
        "tax_period": resolved_period,
        "output_tax": float(row["output_tax"]),
        "eligible_itc": float(row["eligible_itc"]),
        "itc_reversed": float(row["itc_reversed"]),
        "net_itc": float(row["net_itc"]),
        "data_available": True,
    }


@router.get("/cross-form")
def gstr3b_cross_form(
    tax_period: Optional[str] = Query(None, description="Optional tax period filter YYYY-MM"),
    current_business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    """
    Cross-form comparison between detailed register data and GSTR-3B summary.

    Compares:
    1. Sales Register + GSTR-1 combined GST totals  vs  GSTR-3B Table 3.1 output tax
    2. Purchase Register ITC total  vs  GSTR-3B Table 4(A) eligible ITC
    3. Identifies tax-period inconsistencies and missing data

    Returns investigation recommendations — NOT confirmed compliance errors.
    GSTR-2B data is not yet supported; this is documented in the response.
    """
    import calendar
    import re
    from datetime import date as dt_date

    # Parse tax_period for DB filtering
    start_date, end_date = None, None
    resolved_period = None
    if tax_period:
        period_str = tax_period.strip()
        m = re.match(r"^(\d{4})-(0[1-9]|1[0-2])$", period_str)
        if m:
            year, month = int(m.group(1)), int(m.group(2))
            _, last_day = calendar.monthrange(year, month)
            start_date = dt_date(year, month, 1)
            end_date = dt_date(year, month, last_day)
            resolved_period = period_str

    # Load GSTR-3B CSV row
    gstr3b_row, csv_period = _load_gstr3b_row(tax_period)
    if resolved_period is None:
        resolved_period = csv_period or "2026-07"

    # Load DB invoice sums for this business
    try:
        db_sums = _get_db_invoice_sums(current_business.id, db, start_date, end_date)
    except Exception:
        db_sums = {}

    sales_reg_gst = db_sums.get("sales_register", {}).get("gst_amount", 0.0)
    gstr1_gst = db_sums.get("gstr1", {}).get("gst_amount", 0.0)
    purchase_reg_gst = db_sums.get("purchase_register", {}).get("gst_amount", 0.0)
    gstr2a_gst = db_sums.get("gstr2a", {}).get("gst_amount", 0.0)

    sales_reg_tv = db_sums.get("sales_register", {}).get("taxable_value", 0.0)
    gstr1_tv = db_sums.get("gstr1", {}).get("taxable_value", 0.0)
    purchase_reg_tv = db_sums.get("purchase_register", {}).get("taxable_value", 0.0)

    has_db_data = bool(db_sums)

    # GSTR-3B declared values
    gstr3b_available = (gstr3b_row is not None) and (current_business.id == 1)
    if gstr3b_available:
        gstr3b_output_tax = float(gstr3b_row["output_tax"])
        gstr3b_eligible_itc = float(gstr3b_row["eligible_itc"])
        gstr3b_itc_reversed = float(gstr3b_row["itc_reversed"])
        gstr3b_net_itc = float(gstr3b_row["net_itc"])
    else:
        gstr3b_output_tax = gstr3b_eligible_itc = gstr3b_itc_reversed = gstr3b_net_itc = 0.0

    # ── Cross-form comparison 1: Output tax liability ──
    # GSTR-1 total (filed outward supplies) vs GSTR-3B Table 3.1
    gstr1_to_gstr3b_diff = round(gstr1_gst - gstr3b_output_tax, 2)
    # Sales register vs GSTR-1 (outward supply agreement)
    sales_to_gstr1_diff = round(sales_reg_gst - gstr1_gst, 2)

    # ── Cross-form comparison 2: Input tax credit ──
    # GSTR-2A (supplier-filed ITC) vs GSTR-3B Table 4(A)
    gstr2a_to_gstr3b_diff = round(gstr2a_gst - gstr3b_eligible_itc, 2)
    # Purchase register vs GSTR-2A
    purchase_to_gstr2a_diff = round(purchase_reg_gst - gstr2a_gst, 2)

    # Net tax payable estimate
    estimated_net_tax = round(max(0.0, gstr3b_output_tax - gstr3b_net_itc), 2)

    # Build findings list
    findings = []

    if not has_db_data:
        findings.append({
            "finding_id": "cf-no-data",
            "category": "DATA_AVAILABILITY",
            "severity": "INFO",
            "description": "No invoice records found in the database for this business and period.",
            "recommendation": "Upload Sales Register, GSTR-1, Purchase Register, and GSTR-2A CSV files to enable cross-form analysis.",
        })
    else:
        if not gstr3b_available:
            findings.append({
                "finding_id": "cf-no-gstr3b",
                "category": "DATA_AVAILABILITY",
                "severity": "INFO",
                "description": "GSTR-3B summary data is not available for this business. Cross-form comparison against Table 3.1 and Table 4(A) cannot be performed.",
                "recommendation": "Add GSTR-3B data to enable full cross-form analysis.",
            })

        # Sales register vs GSTR-1
        if abs(sales_to_gstr1_diff) > 0.01:
            sev = "HIGH" if abs(sales_to_gstr1_diff) > 5000 else "MEDIUM"
            findings.append({
                "finding_id": "cf-sales-gstr1-diff",
                "category": "OUTWARD_SUPPLY_DISCREPANCY",
                "severity": sev,
                "register_value": round(sales_reg_gst, 2),
                "gst_portal_value": round(gstr1_gst, 2),
                "difference": sales_to_gstr1_diff,
                "description": (
                    f"Sales Register GST total (₹{sales_reg_gst:,.2f}) differs from "
                    f"GSTR-1 filed GST total (₹{gstr1_gst:,.2f}) by ₹{abs(sales_to_gstr1_diff):,.2f}."
                ),
                "possible_causes": [
                    "Invoices present in books but not yet filed in GSTR-1.",
                    "Invoices filed in GSTR-1 but not recorded in sales register.",
                    "Amendments or credit notes not reflected in one source.",
                    "Tax-period differences — some invoices may belong to a different period.",
                ],
                "recommendation": "Run the Sales Reconciliation report to identify specific mismatches. Investigate before filing GSTR-3B.",
            })

        # GSTR-1 vs GSTR-3B Table 3.1
        if gstr3b_available and abs(gstr1_to_gstr3b_diff) > 0.01:
            sev = "HIGH" if abs(gstr1_to_gstr3b_diff) > 5000 else "MEDIUM"
            findings.append({
                "finding_id": "cf-gstr1-gstr3b-diff",
                "category": "GSTR1_VS_GSTR3B_OUTPUT_TAX",
                "severity": sev,
                "register_value": round(gstr1_gst, 2),
                "gst_portal_value": gstr3b_output_tax,
                "difference": gstr1_to_gstr3b_diff,
                "description": (
                    f"GSTR-1 filed output tax (₹{gstr1_gst:,.2f}) differs from "
                    f"GSTR-3B Table 3.1 declared output tax (₹{gstr3b_output_tax:,.2f}) "
                    f"by ₹{abs(gstr1_to_gstr3b_diff):,.2f}."
                ),
                "possible_causes": [
                    "GSTR-3B filed before all GSTR-1 amendments were processed.",
                    "B2C or export supplies included differently between forms.",
                    "Amendments (GSTR-1A) not reflected in GSTR-3B.",
                ],
                "recommendation": (
                    "Verify GSTR-3B Table 3.1 matches the sum of all taxable outward "
                    "supplies from GSTR-1. File an amendment return if a material "
                    "difference exists. Consult your GST practitioner."
                ),
            })

        # Purchase register vs GSTR-2A
        if abs(purchase_to_gstr2a_diff) > 0.01:
            sev = "HIGH" if abs(purchase_to_gstr2a_diff) > 5000 else "MEDIUM"
            findings.append({
                "finding_id": "cf-purchase-gstr2a-diff",
                "category": "ITC_AVAILABILITY_DISCREPANCY",
                "severity": sev,
                "register_value": round(purchase_reg_gst, 2),
                "gst_portal_value": round(gstr2a_gst, 2),
                "difference": purchase_to_gstr2a_diff,
                "description": (
                    f"Purchase Register ITC total (₹{purchase_reg_gst:,.2f}) differs from "
                    f"GSTR-2A supplier-filed ITC (₹{gstr2a_gst:,.2f}) by "
                    f"₹{abs(purchase_to_gstr2a_diff):,.2f}."
                ),
                "possible_causes": [
                    "Supplier has not filed GSTR-1 for some invoices.",
                    "Purchase recorded in a different tax period than supplier filing.",
                    "Invoice amendments or credit notes not yet reflected.",
                ],
                "recommendation": (
                    "Only claim ITC for invoices confirmed in GSTR-2A/2B. Contact suppliers "
                    "for unfiled invoices. Do not claim ITC without supplier filing (Rule 36(4))."
                ),
            })

        # GSTR-2A vs GSTR-3B Table 4(A)
        if gstr3b_available and abs(gstr2a_to_gstr3b_diff) > 0.01:
            sev = "HIGH" if abs(gstr2a_to_gstr3b_diff) > 5000 else "MEDIUM"
            findings.append({
                "finding_id": "cf-gstr2a-gstr3b-diff",
                "category": "ITC_CLAIMED_VS_AVAILABLE",
                "severity": sev,
                "register_value": round(gstr2a_gst, 2),
                "gst_portal_value": gstr3b_eligible_itc,
                "difference": gstr2a_to_gstr3b_diff,
                "description": (
                    f"GSTR-2A available ITC (₹{gstr2a_gst:,.2f}) differs from "
                    f"GSTR-3B Table 4(A) eligible ITC claimed (₹{gstr3b_eligible_itc:,.2f}) "
                    f"by ₹{abs(gstr2a_to_gstr3b_diff):,.2f}."
                ),
                "possible_causes": [
                    "ITC claimed in GSTR-3B exceeds what is available in GSTR-2A.",
                    "Transition credit or RCM credit included in 4(A) claim.",
                    "GSTR-2B (auto-drafted) figures used instead of GSTR-2A.",
                ],
                "recommendation": (
                    "Verify GSTR-3B Table 4(A) does not exceed GSTR-2A totals without "
                    "a valid legal basis. Excess ITC claims may attract interest and penalty."
                ),
            })

        # ITC reversal note
        if gstr3b_available and gstr3b_itc_reversed > 0:
            findings.append({
                "finding_id": "cf-itc-reversal",
                "category": "ITC_REVERSAL_NOTE",
                "severity": "INFO",
                "register_value": gstr3b_eligible_itc,
                "gst_portal_value": gstr3b_net_itc,
                "difference": round(gstr3b_itc_reversed, 2),
                "description": (
                    f"GSTR-3B Table 4(B) shows ₹{gstr3b_itc_reversed:,.2f} of ITC reversed. "
                    f"Net ITC available in Electronic Credit Ledger: ₹{gstr3b_net_itc:,.2f}."
                ),
                "possible_causes": [
                    "Ineligible ITC under Section 17(5) (blocked credits).",
                    "Rule 42/43 reversal for exempt/non-business use.",
                    "Provisional ITC reversal pending supplier filing.",
                ],
                "recommendation": "Confirm reversal basis with your GST consultant. Maintain documentation for each reversed ITC item.",
            })

    # GSTR-2B disclaimer
    findings.append({
        "finding_id": "cf-gstr2b-disclaimer",
        "category": "DATA_AVAILABILITY",
        "severity": "INFO",
        "description": "GSTR-2B (auto-drafted ITC statement) is not yet integrated into this system.",
        "recommendation": "For final ITC reconciliation, cross-verify GSTR-2A figures against GSTR-2B from the GST portal once available.",
    })

    return {
        "business_id": current_business.id,
        "tax_period": resolved_period,
        "gstr3b_data_available": gstr3b_available,
        "register_data_available": has_db_data,
        "gstr3b_summary": {
            "output_tax": gstr3b_output_tax,
            "eligible_itc": gstr3b_eligible_itc,
            "itc_reversed": gstr3b_itc_reversed,
            "net_itc": gstr3b_net_itc,
            "estimated_net_tax_payable": estimated_net_tax,
        },
        "register_sums": {
            "sales_register_gst": round(sales_reg_gst, 2),
            "gstr1_gst": round(gstr1_gst, 2),
            "purchase_register_gst": round(purchase_reg_gst, 2),
            "gstr2a_gst": round(gstr2a_gst, 2),
            "sales_register_taxable": round(sales_reg_tv, 2),
            "gstr1_taxable": round(gstr1_tv, 2),
            "purchase_register_taxable": round(purchase_reg_tv, 2),
        },
        "cross_form_differences": {
            "sales_register_vs_gstr1_gst": sales_to_gstr1_diff,
            "gstr1_vs_gstr3b_output_tax": gstr1_to_gstr3b_diff if gstr3b_available else None,
            "purchase_register_vs_gstr2a_gst": purchase_to_gstr2a_diff,
            "gstr2a_vs_gstr3b_itc": gstr2a_to_gstr3b_diff if gstr3b_available else None,
        },
        "findings": findings,
        "total_findings": len(findings),
        "note": (
            "Cross-form differences are reported for investigation only. "
            "They do not constitute confirmed compliance errors. "
            "Consult a qualified GST practitioner before making any return amendments."
        ),
    }
