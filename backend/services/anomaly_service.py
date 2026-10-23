from typing import Any, Dict, List, Optional
from reconciliation.reconcile import reconcile
from services.validation import validate_gstin


def get_all_anomalies(sales_file: Any = "sales_register.csv", gstr1_file: Any = "gstr1.csv",
                      purchase_file: Any = "purchase_register.csv", gstr2a_file: Any = "gstr2a.csv",
                      sales_df: Optional[Any] = None, purchase_df: Optional[Any] = None,
                      purchase_label: str = "GSTR-2A") -> List[Dict[str, Any]]:
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
        tax_period = date[:7] if len(date) >= 7 and date[4] == "-" else None
        tv_diff = row.get("taxable_value_diff")
        gst_diff = row.get("gst_amount_diff")
        exp_tv = row.get("expected_taxable_value")
        act_tv = row.get("actual_taxable_value")
        exp_gst = row.get("expected_gst_amount")
        act_gst = row.get("actual_gst_amount")
        source = "Sales (Register ↔ GSTR-1)"

        # Check duplicate
        if inv_no in seen_invoices:
            anomalies.append({
                "id": f"anom-dup-{inv_no}",
                "invoice_no": inv_no,
                "gstin": gstin,
                "source": source,
                "date": date,
                "tax_period": tax_period,
                "type": "DUPLICATE_INVOICE",
                "severity": "HIGH",
                "difference": 0.0,
                "compared_values": {
                    "books_value": exp_tv,
                    "portal_value": act_tv,
                },
                "explanation": f"Duplicate invoice number '{inv_no}' identified across registers.",
                "possible_causes": [
                    "Hypothesis: Same sales bill entered twice in accounting software.",
                    "Hypothesis: Amendment filed as fresh invoice on the portal.",
                ],
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
                "tax_period": tax_period,
                "type": "INVALID_GSTIN",
                "severity": "MEDIUM",
                "difference": 0.0,
                "compared_values": {
                    "recorded_gstin": gstin,
                },
                "explanation": f"GSTIN '{gstin}' does not conform to the 15-character statutory format.",
                "possible_causes": [
                    "Hypothesis: Typographical error during customer onboarding.",
                    "Hypothesis: PAN or State Code improperly recorded.",
                ],
                "action_recommended": "Update customer master data with verified 15-digit GSTIN."
            })

        if status == "MISSING_IN_GST":
            anomalies.append({
                "id": f"anom-mis-{inv_no}",
                "invoice_no": inv_no,
                "gstin": gstin,
                "source": source,
                "date": date,
                "tax_period": tax_period,
                "type": "MISSING_IN_GST",
                "severity": "HIGH",
                "difference": float(row.get("taxable_value") or 0.0),
                "compared_values": {
                    "books_taxable": exp_tv,
                    "books_gst": exp_gst,
                    "portal_taxable": None,
                    "portal_gst": None,
                },
                "explanation": f"Sales invoice exists in internal books (Rs. {float(row.get('taxable_value') or 0.0):,.2f}) but is absent in GSTR-1 portal filing.",
                "possible_causes": [
                    "Hypothesis: Invoice omitted from GSTR-1 filing upload.",
                    "Hypothesis: Invoice belongs to a different return period.",
                ],
                "action_recommended": "Add invoice to pending GSTR-1 outward supplies to prevent compliance notices."
            })
        elif status == "EXTRA_IN_GST":
            anomalies.append({
                "id": f"anom-ext-{inv_no}",
                "invoice_no": inv_no,
                "gstin": gstin,
                "source": source,
                "date": date,
                "tax_period": tax_period,
                "type": "EXTRA_IN_GST",
                "severity": "MEDIUM",
                "difference": float(row.get("taxable_value") or 0.0),
                "compared_values": {
                    "books_taxable": None,
                    "portal_taxable": act_tv,
                    "portal_gst": act_gst,
                },
                "explanation": "Invoice reported on GSTR-1 portal but omitted from internal sales register.",
                "possible_causes": [
                    "Hypothesis: Outward invoice omitted from accounting software.",
                    "Hypothesis: Invoice recorded in a subsequent or preceding accounting month.",
                ],
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
                "tax_period": tax_period,
                "type": "LARGE_TAX_DIFFERENCE" if is_large else "MISMATCH",
                "severity": "HIGH" if is_large else "MEDIUM",
                "difference": round(abs_diff, 2),
                "compared_values": {
                    "books_taxable": exp_tv,
                    "portal_taxable": act_tv,
                    "taxable_diff": tv_diff,
                    "books_gst": exp_gst,
                    "portal_gst": act_gst,
                    "gst_diff": gst_diff,
                },
                "explanation": row.get("explanation") or f"Taxable value diff: Rs. {tv_diff}, GST diff: Rs. {gst_diff}",
                "possible_causes": [
                    "Hypothesis: Rate variance or line-item tax calculation mismatch.",
                    "Hypothesis: Post-sale trade discount or credit note not reflected in both systems.",
                ],
                "action_recommended": "Reconcile rate, discount, or tax amount against physical copy."
            })

    # Reconcile Purchases (Purchase Register vs GSTR-2A or GSTR-2B)
    if purchase_df is None:
        purchase_df = reconcile(purchase_file, gstr2a_file)
    for _, row in purchase_df.iterrows():
        inv_no = str(row["invoice_no"])
        status = row["status"]
        gstin = str(row.get("gstin") or "")
        date = str(row.get("invoice_date") or "")
        tax_period = date[:7] if len(date) >= 7 and date[4] == "-" else None
        tv_diff = row.get("taxable_value_diff")
        gst_diff = row.get("gst_amount_diff")
        exp_tv = row.get("expected_taxable_value")
        act_tv = row.get("actual_taxable_value")
        exp_gst = row.get("expected_gst_amount")
        act_gst = row.get("actual_gst_amount")
        source = f"Purchase (Register ↔ {purchase_label})"

        # Check duplicate
        if inv_no in seen_invoices:
            anomalies.append({
                "id": f"anom-dup-p-{inv_no}",
                "invoice_no": inv_no,
                "gstin": gstin,
                "source": source,
                "date": date,
                "tax_period": tax_period,
                "type": "DUPLICATE_INVOICE",
                "severity": "HIGH",
                "difference": 0.0,
                "compared_values": {
                    "books_value": exp_tv,
                    "portal_value": act_tv,
                },
                "explanation": f"Duplicate purchase invoice number '{inv_no}' flagged.",
                "possible_causes": [
                    "Hypothesis: Supplier bill entered twice in accounts payable.",
                    "Hypothesis: Replacement bill received without cancelling original entry.",
                ],
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
                "tax_period": tax_period,
                "type": "MISSING_IN_GST",
                "severity": "HIGH",
                "difference": float(row.get("gst_amount") or 0.0),
                "compared_values": {
                    "books_taxable": exp_tv,
                    "books_gst": exp_gst,
                    "portal_taxable": None,
                    "portal_gst": None,
                },
                "explanation": (
                    f"Vendor invoice exists in your purchase register (ITC: Rs. {float(row.get('gst_amount') or 0.0):,.2f}) "
                    f"but supplier did not file in {purchase_label}."
                ),
                "possible_causes": [
                    "Hypothesis: Supplier has not yet filed their GSTR-1.",
                    "Hypothesis: Supplier filed after the monthly cut-off date (under Rule 36(4)).",
                    "Hypothesis: Supplier entered incorrect recipient GSTIN in their filing.",
                ],
                "action_recommended": "Contact supplier to file GSTR-1; do not claim ineligible ITC without supplier filing."
            })
        elif status == "EXTRA_IN_GST":
            anomalies.append({
                "id": f"anom-ext-p-{inv_no}",
                "invoice_no": inv_no,
                "gstin": gstin,
                "source": source,
                "date": date,
                "tax_period": tax_period,
                "type": "EXTRA_IN_GST",
                "severity": "MEDIUM",
                "difference": float(row.get("taxable_value") or 0.0),
                "compared_values": {
                    "books_taxable": None,
                    "portal_taxable": act_tv,
                    "portal_gst": act_gst,
                },
                "explanation": f"Supplier filed invoice in {purchase_label}, but it is not booked in purchase register.",
                "possible_causes": [
                    "Hypothesis: Vendor bill received but not yet entered in accounts payable.",
                    "Hypothesis: Inadvertent invoice uploaded against your GSTIN by another supplier.",
                ],
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
                "tax_period": tax_period,
                "type": "LARGE_TAX_DIFFERENCE" if is_large else "MISMATCH",
                "severity": "HIGH" if is_large else "MEDIUM",
                "difference": round(abs_diff, 2),
                "compared_values": {
                    "books_taxable": exp_tv,
                    "portal_taxable": act_tv,
                    "taxable_diff": tv_diff,
                    "books_gst": exp_gst,
                    "portal_gst": act_gst,
                    "gst_diff": gst_diff,
                },
                "explanation": row.get("explanation") or f"Taxable value diff: Rs. {tv_diff}, GST diff: Rs. {gst_diff}",
                "possible_causes": [
                    "Hypothesis: Discrepancy in invoice amount or tax rate entered in accounts payable.",
                    "Hypothesis: Supplier issued a debit/credit note not yet accounted for in internal ledger.",
                ],
                "action_recommended": "Request supplier to issue a credit/debit note or amend return in GSTR-1."
            })

    return anomalies
