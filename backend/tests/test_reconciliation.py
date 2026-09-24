import pandas as pd
import pytest
from reconciliation.reconcile import reconcile


def test_reconciliation_match():
    my_data = pd.DataFrame([{
        "invoice_no": "INV-101",
        "invoice_date": "2026-07-01",
        "customer_gstin": "29AAAAA1111A1Z5",
        "taxable_value": 10000.0,
        "gst_amount": 1800.0,
    }])
    gst_data = pd.DataFrame([{
        "invoice_no": "INV-101",
        "invoice_date": "2026-07-01",
        "customer_gstin": "29AAAAA1111A1Z5",
        "taxable_value": 10000.0,
        "gst_amount": 1800.0,
    }])

    res = reconcile(my_data, gst_data)
    assert len(res) == 1
    row = res.iloc[0]
    assert row["status"] == "MATCH"
    assert row["taxable_value_diff"] == 0.0
    assert row["gst_amount_diff"] == 0.0


def test_reconciliation_mismatch():
    my_data = pd.DataFrame([{
        "invoice_no": "INV-102",
        "invoice_date": "2026-07-02",
        "customer_gstin": "29BBBBB2222B1Z5",
        "taxable_value": 20000.0,
        "gst_amount": 3600.0,
    }])
    gst_data = pd.DataFrame([{
        "invoice_no": "INV-102",
        "invoice_date": "2026-07-02",
        "customer_gstin": "29BBBBB2222B1Z5",
        "taxable_value": 18000.0,
        "gst_amount": 3240.0,
    }])

    res = reconcile(my_data, gst_data)
    assert len(res) == 1
    row = res.iloc[0]
    assert row["status"] == "MISMATCH"
    assert row["taxable_value_diff"] == 2000.0
    assert row["gst_amount_diff"] == 360.0
    assert "Taxable value differs" in row["explanation"]


def test_reconciliation_missing_in_gst():
    my_data = pd.DataFrame([{
        "invoice_no": "INV-103",
        "invoice_date": "2026-07-03",
        "customer_gstin": "29CCCCC3333C1Z5",
        "taxable_value": 15000.0,
        "gst_amount": 2700.0,
    }])
    gst_data = pd.DataFrame([], columns=["invoice_no", "invoice_date", "customer_gstin", "taxable_value", "gst_amount"])

    res = reconcile(my_data, gst_data)
    assert len(res) == 1
    row = res.iloc[0]
    assert row["status"] == "MISSING_IN_GST"
    assert row["taxable_value_diff"] is None
    assert row["gst_amount_diff"] is None
    assert "missing" in row["explanation"].lower() or "not found" in row["explanation"].lower()


def test_reconciliation_extra_in_gst():
    my_data = pd.DataFrame([], columns=["invoice_no", "invoice_date", "customer_gstin", "taxable_value", "gst_amount"])
    gst_data = pd.DataFrame([{
        "invoice_no": "INV-104",
        "invoice_date": "2026-07-04",
        "customer_gstin": "29DDDDD4444D1Z5",
        "taxable_value": 12000.0,
        "gst_amount": 2160.0,
    }])

    res = reconcile(my_data, gst_data)
    assert len(res) == 1
    row = res.iloc[0]
    assert row["status"] == "EXTRA_IN_GST"
    assert row["taxable_value_diff"] is None
    assert row["gst_amount_diff"] is None


def test_sales_and_purchase_file_reconciliation():
    sales = reconcile("sales_register.csv", "gstr1.csv")
    statuses = set(sales["status"])
    assert "MATCH" in statuses
    assert "MISMATCH" in statuses
    assert "MISSING_IN_GST" in statuses
    assert "EXTRA_IN_GST" in statuses

    purchases = reconcile("purchase_register.csv", "gstr2a.csv")
    p_statuses = set(purchases["status"])
    assert "MATCH" in p_statuses
    assert "MISMATCH" in p_statuses
    assert "MISSING_IN_GST" in p_statuses
    assert "EXTRA_IN_GST" in p_statuses


def test_reconciliation_duplicates_preserved():
    # Test duplicate invoice numbers in internal records
    my_data = pd.DataFrame([
        {
            "invoice_no": "INV-DUP-1",
            "invoice_date": "2026-07-01",
            "gstin": "29AAAAA1111A1Z5",
            "taxable_value": 10000.0,
            "gst_amount": 1800.0,
        },
        {
            "invoice_no": "INV-DUP-1",
            "invoice_date": "2026-07-01",
            "gstin": "29AAAAA1111A1Z5",
            "taxable_value": 10000.0,
            "gst_amount": 1800.0,
        },
    ])
    gst_data = pd.DataFrame([
        {
            "invoice_no": "INV-DUP-1",
            "invoice_date": "2026-07-01",
            "gstin": "29AAAAA1111A1Z5",
            "taxable_value": 10000.0,
            "gst_amount": 1800.0,
        },
    ])

    res = reconcile(my_data, gst_data)
    # Both duplicate rows must be preserved, none silently dropped by .iloc[0]
    assert len(res) == 2
    for _, row in res.iterrows():
        assert row["status"] == "MISMATCH"
        assert "Duplicate invoice number" in row["explanation"]


def test_reconciliation_duplicates_in_unilateral_sources():
    # Duplicate invoices only in my_data
    my_data = pd.DataFrame([
        {
            "invoice_no": "INV-DUP-MY",
            "invoice_date": "2026-07-01",
            "gstin": "29AAAAA1111A1Z5",
            "taxable_value": 5000.0,
            "gst_amount": 900.0,
        },
        {
            "invoice_no": "INV-DUP-MY",
            "invoice_date": "2026-07-01",
            "gstin": "29AAAAA1111A1Z5",
            "taxable_value": 5000.0,
            "gst_amount": 900.0,
        },
    ])
    gst_data = pd.DataFrame([], columns=["invoice_no", "invoice_date", "gstin", "taxable_value", "gst_amount"])

    res = reconcile(my_data, gst_data)
    assert len(res) == 2
    for _, row in res.iterrows():
        assert row["status"] == "MISSING_IN_GST"
        assert "Duplicate invoice" in row["explanation"]


def test_reconciliation_empty_dfs():
    empty_a = pd.DataFrame([], columns=["invoice_no", "invoice_date", "gstin", "taxable_value", "gst_amount"])
    empty_b = pd.DataFrame([], columns=["invoice_no", "invoice_date", "gstin", "taxable_value", "gst_amount"])
    res = reconcile(empty_a, empty_b)
    assert len(res) == 0

