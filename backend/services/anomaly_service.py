from typing import Any, Dict, List, Optional
from reconciliation.reconcile import reconcile
from services.validation import validate_gstin


def get_all_anomalies(sales_file: Any = "sales_register.csv", gstr1_file: Any = "gstr1.csv",
                      purchase_file: Any = "purchase_register.csv", gstr2a_file: Any = "gstr2a.csv",
                      sales_df: Optional[Any] = None, purchase_df: Optional[Any] = None) -> List[Dict[str, Any]]:
    """
    Deterministically computes anomalies across sales and purchase reconciliation datasets.
    Rules are transparent and documented:
    - HIGH: Missing in GST (potential loss of ITC or unfiled outward liability)
    - HIGH: Large tax difference (difference > ₹1,000)
    - HIGH: Duplicate invoice in source data
    - MEDIUM: Discrepancies <= ₹1,000
    - MEDIUM: Extra invoice in GST portal not in books
    - MEDIUM: Invalid GSTIN structure
    """
    anomalies: List[Dict[str, Any]] = []
    seen_invoices = set()

    # Reconcile Sales (Sales Register vs GSTR-1)
    if sales_df is None:
        sales_df = reconcile(sales_file, gstr1_file)
    for _, row in sales_df.iterrows():
        inv_no = str(row["invoice_no"])
        status = row["status"]
        gstin = str(row.get("gstin") or "")
        date = str(row.get("invoice_date") or "")
        tv_diff = row.get("taxable_value_diff")
        gst_diff = row.get("gst_amount_diff")
        source = "Sales (Register ↔ GSTR-1)"

        # Check duplicate
        if inv_no in seen_invoices:
            anomalies.append({
                "id": f"anom-dup-{inv_no}",
                "invoice_no": inv_no,
                "gstin": gstin,
                "source": source,
                "date": date,
                "type": "DUPLICATE_INVOICE",
                "severity": "HIGH",
                "difference": 0.0,
                "explanation": f"Duplicate invoice number '{inv_no}' identified across registers.",
                "action_recommended": "Verify books and eliminate duplicate entries before final return submission."
            })
        seen_invoices.add(inv_no)

        # Check GSTIN validity
        is_gstin_valid, _ = validate_gstin(gstin)
        if gstin and not is_gstin_valid:
            anomalies.append({
                "id": f"anom-gstin-{inv_no}",
                "invoice_no": inv_no,
                "gstin": gstin,
                "source": source,
                "date": date,
                "type": "INVALID_GSTIN",
                "severity": "MEDIUM",
                "difference": 0.0,
                "explanation": f"GSTIN '{gstin}' does not conform to the 15-character statutory format.",
                "action_recommended": "Update customer master data with verified 15-digit GSTIN."
            })

        if status == "MISSING_IN_GST":
            anomalies.append({
                "id": f"anom-mis-{inv_no}",
                "invoice_no": inv_no,
                "gstin": gstin,
                "source": source,
                "date": date,
                "type": "MISSING_IN_GST",
                "severity": "HIGH",
                "difference": float(row.get("taxable_value") or 0.0),
                "explanation": f"Sales invoice exists in internal books (Rs. {float(row.get('taxable_value') or 0.0):,.2f}) but is absent in GSTR-1 portal filing.",
                "action_recommended": "Add invoice to pending GSTR-1 outward supplies to prevent compliance notices."
            })
        elif status == "EXTRA_IN_GST":
            anomalies.append({
                "id": f"anom-ext-{inv_no}",
                "invoice_no": inv_no,
                "gstin": gstin,
                "source": source,
                "date": date,
                "type": "EXTRA_IN_GST",
                "severity": "MEDIUM",
                "difference": float(row.get("taxable_value") or 0.0),
                "explanation": "Invoice reported on GSTR-1 portal but omitted from internal sales register.",
                "action_recommended": "Review whether this outward invoice was booked in a different accounting month."
            })
        elif status == "MISMATCH":
            abs_diff = max(abs(float(tv_diff or 0.0)), abs(float(gst_diff or 0.0)))
            is_large = abs_diff >= 1000.0
            anomalies.append({
                "id": f"anom-mism-{inv_no}",
                "invoice_no": inv_no,
                "gstin": gstin,
                "source": source,
                "date": date,
                "type": "LARGE_TAX_DIFFERENCE" if is_large else "MISMATCH",
                "severity": "HIGH" if is_large else "MEDIUM",
                "difference": round(abs_diff, 2),
                "explanation": row.get("explanation") or f"Taxable value diff: Rs. {tv_diff}, GST diff: Rs. {gst_diff}",
                "action_recommended": "Reconcile rate, discount, or tax amount against physical copy."
            })

    # Reconcile Purchases (Purchase Register vs GSTR-2A)
    if purchase_df is None:
        purchase_df = reconcile(purchase_file, gstr2a_file)
    for _, row in purchase_df.iterrows():
        inv_no = str(row["invoice_no"])
        status = row["status"]
        gstin = str(row.get("gstin") or "")
        date = str(row.get("invoice_date") or "")
        tv_diff = row.get("taxable_value_diff")
        gst_diff = row.get("gst_amount_diff")
        source = "Purchase (Register ↔ GSTR-2A)"

        # Check duplicate
        if inv_no in seen_invoices:
            anomalies.append({
                "id": f"anom-dup-p-{inv_no}",
                "invoice_no": inv_no,
                "gstin": gstin,
                "source": source,
                "date": date,
                "type": "DUPLICATE_INVOICE",
                "severity": "HIGH",
                "difference": 0.0,
                "explanation": f"Duplicate purchase invoice number '{inv_no}' flagged.",
                "action_recommended": "Ensure this vendor bill has not been entered twice in accounts payable."
            })
        seen_invoices.add(inv_no)

        if status == "MISSING_IN_GST":
            anomalies.append({
                "id": f"anom-mis-p-{inv_no}",
                "invoice_no": inv_no,
                "gstin": gstin,
                "source": source,
                "date": date,
                "type": "MISSING_IN_GST",
                "severity": "HIGH",
                "difference": float(row.get("gst_amount") or 0.0),
                "explanation": f"Vendor invoice exists in your purchase register (ITC: Rs. {float(row.get('gst_amount') or 0.0):,.2f}) but supplier did not file in GSTR-2A.",
                "action_recommended": "Contact supplier to file GSTR-1; do not claim ineligible ITC without supplier filing."
            })
        elif status == "EXTRA_IN_GST":
            anomalies.append({
                "id": f"anom-ext-p-{inv_no}",
                "invoice_no": inv_no,
                "gstin": gstin,
                "source": source,
                "date": date,
                "type": "EXTRA_IN_GST",
                "severity": "MEDIUM",
                "difference": float(row.get("taxable_value") or 0.0),
                "explanation": "Supplier filed invoice in GSTR-2A, but it is not booked in purchase register.",
                "action_recommended": "Verify receipt of goods/services; enter in books to claim eligible ITC."
            })
        elif status == "MISMATCH":
            abs_diff = max(abs(float(tv_diff or 0.0)), abs(float(gst_diff or 0.0)))
            is_large = abs_diff >= 1000.0
            anomalies.append({
                "id": f"anom-mism-p-{inv_no}",
                "invoice_no": inv_no,
                "gstin": gstin,
                "source": source,
                "date": date,
                "type": "LARGE_TAX_DIFFERENCE" if is_large else "MISMATCH",
                "severity": "HIGH" if is_large else "MEDIUM",
                "difference": round(abs_diff, 2),
                "explanation": row.get("explanation") or f"Taxable value diff: Rs. {tv_diff}, GST diff: Rs. {gst_diff}",
                "action_recommended": "Request supplier to issue a credit/debit note or amend return in GSTR-1."
            })

    return anomalies
