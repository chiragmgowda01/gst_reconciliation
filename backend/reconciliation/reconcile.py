from pathlib import Path
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"


def _extract_gstin(row) -> str:
    return str(row.get("customer_gstin") or row.get("supplier_gstin") or "").strip()


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

    my_df["invoice_no"] = my_df["invoice_no"].astype(str).str.strip()
    gst_df["invoice_no"] = gst_df["invoice_no"].astype(str).str.strip()

    results = []

    my_inv = set(my_df["invoice_no"])
    gst_inv = set(gst_df["invoice_no"])

    common = my_inv & gst_inv
    only_my = my_inv - gst_inv
    only_gst = gst_inv - my_inv

    for inv in common:
        a = my_df[my_df["invoice_no"] == inv].iloc[0]
        b = gst_df[gst_df["invoice_no"] == inv].iloc[0]

        a_tv = float(a["taxable_value"])
        b_tv = float(b["taxable_value"])
        a_gst = float(a["gst_amount"])
        b_gst = float(b["gst_amount"])

        tv_diff = round(a_tv - b_tv, 2)
        gst_diff = round(a_gst - b_gst, 2)

        if tv_diff == 0 and gst_diff == 0:
            status = "MATCH"
            explanation = "Invoice matched across both internal records and GST portal."
        else:
            status = "MISMATCH"
            diff_reasons = []
            if tv_diff != 0:
                diff_reasons.append(f"Taxable value differs by Rs. {abs(tv_diff):,.2f}")
            if gst_diff != 0:
                diff_reasons.append(f"GST amount differs by Rs. {abs(gst_diff):,.2f}")
            explanation = ". ".join(diff_reasons) + " between internal books and GST filing."

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
        })

    for inv in only_my:
        a = my_df[my_df["invoice_no"] == inv].iloc[0]
        a_tv = float(a["taxable_value"])
        a_gst = float(a["gst_amount"])
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
            "explanation": "Invoice exists in internal register but was not found in GST portal filing.",
        })

    for inv in only_gst:
        b = gst_df[gst_df["invoice_no"] == inv].iloc[0]
        b_tv = float(b["taxable_value"])
        b_gst = float(b["gst_amount"])
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
            "explanation": "Invoice found on GST portal but is missing from internal register.",
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