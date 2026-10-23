from pathlib import Path
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"


def _extract_gstin(row) -> str:
    if hasattr(row, "get"):
        return str(row.get("gstin") or row.get("customer_gstin") or row.get("supplier_gstin") or "").strip()
    return ""


def reconcile(my_source, gst_source):
    if isinstance(my_source, pd.DataFrame):
        my_df = my_source.copy()
    else:
        my_path = my_source if isinstance(my_source, Path) else (DATA / my_source)
        my_df = pd.read_csv(my_path)

    if isinstance(gst_source, pd.DataFrame):
        gst_df = gst_source.copy()
    else:
        gst_path = gst_source if isinstance(gst_source, Path) else (DATA / gst_source)
        gst_df = pd.read_csv(gst_path)

    # Ensure required columns exist
    for col in ["invoice_no", "invoice_date", "gstin", "taxable_value", "gst_amount"]:
        if col not in my_df.columns:
            my_df[col] = pd.Series(dtype=object)
        if col not in gst_df.columns:
            gst_df[col] = pd.Series(dtype=object)

    my_df["invoice_no"] = my_df["invoice_no"].astype(str).str.strip()
    gst_df["invoice_no"] = gst_df["invoice_no"].astype(str).str.strip()

    # Filter out empty placeholder rows if any
    my_df = my_df[my_df["invoice_no"] != ""].copy() if not my_df.empty else my_df
    gst_df = gst_df[gst_df["invoice_no"] != ""].copy() if not gst_df.empty else gst_df

    results = []

    my_inv = set(my_df["invoice_no"]) if not my_df.empty else set()
    gst_inv = set(gst_df["invoice_no"]) if not gst_df.empty else set()

    common = my_inv & gst_inv
    only_my = my_inv - gst_inv
    only_gst = gst_inv - my_inv

    for inv in sorted(common):
        my_matches = my_df[my_df["invoice_no"] == inv]
        gst_matches = gst_df[gst_df["invoice_no"] == inv]
        n_my = len(my_matches)
        n_gst = len(gst_matches)

        if n_my == 1 and n_gst == 1:
            a = my_matches.iloc[0]
            b = gst_matches.iloc[0]

            a_tv = float(a["taxable_value"])
            b_tv = float(b["taxable_value"])
            a_gst = float(a["gst_amount"])
            b_gst = float(b["gst_amount"])

            tv_diff = round(a_tv - b_tv, 2)
            gst_diff = round(a_gst - b_gst, 2)

            if tv_diff == 0 and gst_diff == 0:
                status = "MATCH"
                explanation = "Invoice matched across both internal records and GST portal."
                category = "MATCH"
                possible_causes = []
                action = "No action required. Reconciled successfully."
            else:
                status = "MISMATCH"
                diff_reasons = []
                if tv_diff != 0:
                    diff_reasons.append(f"Taxable value differs by Rs. {abs(tv_diff):,.2f}")
                if gst_diff != 0:
                    diff_reasons.append(f"GST amount differs by Rs. {abs(gst_diff):,.2f}")
                explanation = ". ".join(diff_reasons) + " between internal books and GST filing."
                category = "TAXABLE_AND_GST_MISMATCH" if (tv_diff != 0 and gst_diff != 0) else ("TAXABLE_VALUE_MISMATCH" if tv_diff != 0 else "GST_AMOUNT_MISMATCH")
                possible_causes = [
                    "Hypothesis: Data entry discrepancy in taxable value or rate in internal ledger.",
                    "Hypothesis: Commercial discount or credit/debit note applied on one side only.",
                    "Hypothesis: Rounding difference across line items.",
                ]
                action = "Compare physical invoice copy against filed portal return. Request amendment or credit/debit note if needed."

            results.append({
                "invoice_no": inv,
                "invoice_date": str(a.get("invoice_date") or b.get("invoice_date") or ""),
                "gstin": _extract_gstin(a) or _extract_gstin(b),
                "taxable_value": a_tv,
                "gst_amount": a_gst,
                "expected_taxable_value": a_tv,
                "actual_taxable_value": b_tv,
                "expected_gst_amount": a_gst,
                "actual_gst_amount": b_gst,
                "status": status,
                "taxable_value_diff": tv_diff,
                "gst_amount_diff": gst_diff,
                "explanation": explanation,
                "reason": explanation,
                "discrepancy_category": category,
                "possible_causes": possible_causes,
                "suggested_action": action,
            })
        else:
            # Safe duplicate handling: preserve every row without silent .iloc[0] drop
            max_len = max(n_my, n_gst)
            for idx in range(max_len):
                a = my_matches.iloc[idx] if idx < n_my else None
                b = gst_matches.iloc[idx] if idx < n_gst else None

                a_tv = float(a["taxable_value"]) if a is not None else None
                b_tv = float(b["taxable_value"]) if b is not None else None
                a_gst = float(a["gst_amount"]) if a is not None else None
                b_gst = float(b["gst_amount"]) if b is not None else None

                tv_diff = round(a_tv - b_tv, 2) if (a_tv is not None and b_tv is not None) else None
                gst_diff = round(a_gst - b_gst, 2) if (a_gst is not None and b_gst is not None) else None

                row_ref = a if a is not None else b
                explanation = f"Duplicate invoice number '{inv}' detected ({n_my} in books, {n_gst} in GST). Requires manual review."

                results.append({
                    "invoice_no": inv,
                    "invoice_date": str((a.get("invoice_date") if a is not None else "") or (b.get("invoice_date") if b is not None else "") or ""),
                    "gstin": _extract_gstin(row_ref),
                    "taxable_value": a_tv if a_tv is not None else b_tv,
                    "gst_amount": a_gst if a_gst is not None else b_gst,
                    "expected_taxable_value": a_tv,
                    "actual_taxable_value": b_tv,
                    "expected_gst_amount": a_gst,
                    "actual_gst_amount": b_gst,
                    "status": "MISMATCH",
                    "taxable_value_diff": tv_diff,
                    "gst_amount_diff": gst_diff,
                    "explanation": explanation,
                    "reason": explanation,
                    "discrepancy_category": "DUPLICATE_INVOICE",
                    "possible_causes": [
                        "Hypothesis: Multiple bills entered under identical numbering in internal accounting.",
                        "Hypothesis: Portal return filing contains duplicate entries or uncancelled original record alongside amendment.",
                    ],
                    "suggested_action": "Verify underlying invoice originals; eliminate duplicate entries prior to statutory submission.",
                })

    for inv in sorted(only_my):
        my_matches = my_df[my_df["invoice_no"] == inv]
        n_my = len(my_matches)
        for idx in range(n_my):
            a = my_matches.iloc[idx]
            a_tv = float(a["taxable_value"])
            a_gst = float(a["gst_amount"])
            explanation = "Invoice exists in internal register but was not found in GST portal filing."
            if n_my > 1:
                explanation = f"Duplicate invoice exists in internal register (entry {idx + 1} of {n_my}) and was not found in GST portal filing."

            results.append({
                "invoice_no": inv,
                "invoice_date": str(a.get("invoice_date") or ""),
                "gstin": _extract_gstin(a),
                "taxable_value": a_tv,
                "gst_amount": a_gst,
                "expected_taxable_value": a_tv,
                "actual_taxable_value": None,
                "expected_gst_amount": a_gst,
                "actual_gst_amount": None,
                "status": "MISSING_IN_GST",
                "taxable_value_diff": None,
                "gst_amount_diff": None,
                "explanation": explanation,
                "reason": explanation,
                "discrepancy_category": "MISSING_IN_GST",
                "possible_causes": [
                    "Hypothesis: Outward supply invoice not yet uploaded/submitted to GST portal.",
                    "Hypothesis: Inward purchase: Supplier has not filed GSTR-1, or filed after monthly cut-off date.",
                    "Hypothesis: Invoice recorded in a different tax period in internal books.",
                ],
                "suggested_action": "For outward sales, add invoice to pending GSTR-1 filing. For purchases, contact supplier to file return before claiming ITC.",
            })

    for inv in sorted(only_gst):
        gst_matches = gst_df[gst_df["invoice_no"] == inv]
        n_gst = len(gst_matches)
        for idx in range(n_gst):
            b = gst_matches.iloc[idx]
            b_tv = float(b["taxable_value"])
            b_gst = float(b["gst_amount"])
            explanation = "Invoice found on GST portal but is missing from internal register."
            if n_gst > 1:
                explanation = f"Duplicate invoice found on GST portal (entry {idx + 1} of {n_gst}) but is missing from internal register."

            results.append({
                "invoice_no": inv,
                "invoice_date": str(b.get("invoice_date") or ""),
                "gstin": _extract_gstin(b),
                "taxable_value": b_tv,
                "gst_amount": b_gst,
                "expected_taxable_value": None,
                "actual_taxable_value": b_tv,
                "expected_gst_amount": None,
                "actual_gst_amount": b_gst,
                "status": "EXTRA_IN_GST",
                "taxable_value_diff": None,
                "gst_amount_diff": None,
                "explanation": explanation,
                "reason": explanation,
                "discrepancy_category": "EXTRA_IN_GST",
                "possible_causes": [
                    "Hypothesis: Invoice booked on portal was omitted from internal ledger.",
                    "Hypothesis: Counterparty reported incorrect recipient GSTIN on the portal.",
                    "Hypothesis: Goods/services received and recorded in a preceding or succeeding accounting month.",
                ],
                "suggested_action": "Verify delivery challan and receipt of goods; book in purchase ledger if valid, or alert supplier if billed in error.",
            })

    return pd.DataFrame(results)


def show_result(title, df):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)

    print(df.to_string(index=False))

    print("\nSummary:")
    print(df["status"].value_counts())


if __name__ == "__main__":
    sales_result = reconcile(
        "sales_register.csv",
        "gstr1.csv"
    )

    purchase_result = reconcile(
        "purchase_register.csv",
        "gstr2a.csv"
    )

    show_result("SALES RECONCILIATION: SALES REGISTER vs GSTR-1", sales_result)
    show_result("PURCHASE RECONCILIATION: PURCHASE REGISTER vs GSTR-2A", purchase_result)
