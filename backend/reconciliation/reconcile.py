from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"


def reconcile(my_file, gst_file):
    my_df = pd.read_csv(DATA / my_file)
    gst_df = pd.read_csv(DATA / gst_file)

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

        tv_diff = round(float(a["taxable_value"]) - float(b["taxable_value"]), 2)
        gst_diff = round(float(a["gst_amount"]) - float(b["gst_amount"]), 2)

        if tv_diff == 0 and gst_diff == 0:
            status = "MATCH"
        else:
            status = "MISMATCH"

        results.append({
            "invoice_no": inv,
            "status": status,
            "taxable_value_diff": tv_diff,
            "gst_amount_diff": gst_diff
        })

    for inv in only_my:
        results.append({
            "invoice_no": inv,
            "status": "MISSING_IN_GST",
            "taxable_value_diff": None,
            "gst_amount_diff": None
        })

    for inv in only_gst:
        results.append({
            "invoice_no": inv,
            "status": "EXTRA_IN_GST",
            "taxable_value_diff": None,
            "gst_amount_diff": None
        })

    return pd.DataFrame(results)


def show_result(title, df):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)

    print(df.to_string(index=False))

    print("\nSummary:")
    print(df["status"].value_counts())


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