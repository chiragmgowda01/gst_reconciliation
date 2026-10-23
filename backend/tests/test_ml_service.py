"""
Tests for the Isolation Forest ML service.
Uses only in-memory DataFrames — does not touch the real database.
"""

import math
import numpy as np
import pandas as pd
import pytest

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.ml_service import (
    MIN_RECORDS_FOR_ML,
    _engineer_features,
    get_ml_anomalies,
    score_reconciliation,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_sales_df(n: int = 20, seed: int = 42) -> pd.DataFrame:
    """Generate a plausible sales reconciliation DataFrame."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        tv = float(rng.integers(10_000, 200_000))
        gst = round(tv * 0.18, 2)
        tv_diff = float(rng.choice([0, 0, 0, 500, -500, 2000], p=[0.5, 0.1, 0.1, 0.1, 0.1, 0.1]))
        gst_diff = round(tv_diff * 0.18, 2)
        status = "MATCH" if tv_diff == 0 else "MISMATCH"
        rows.append({
            "invoice_no": f"S{i+1:03d}",
            "invoice_date": "2026-07-15",
            "gstin": "29ABCDE1234F1Z5",
            "taxable_value": tv,
            "gst_amount": gst,
            "taxable_value_diff": tv_diff,
            "gst_amount_diff": gst_diff,
            "status": status,
            "explanation": "Test invoice",
        })
    return pd.DataFrame(rows)


def make_purchase_df(n: int = 15, seed: int = 99) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        tv = float(rng.integers(5_000, 100_000))
        gst = round(tv * 0.12, 2)
        status = "MATCH"
        rows.append({
            "invoice_no": f"P{i+1:03d}",
            "invoice_date": "2026-07-20",
            "gstin": "29PQRST1234A1Z1",
            "taxable_value": tv,
            "gst_amount": gst,
            "taxable_value_diff": 0.0,
            "gst_amount_diff": 0.0,
            "status": status,
            "explanation": "Test purchase",
        })
    return pd.DataFrame(rows)


# ─── Feature engineering tests ─────────────────────────────────────────────────

def test_feature_engineering_returns_numeric_df():
    df = make_sales_df(5)
    feat = _engineer_features(df)
    assert isinstance(feat, pd.DataFrame)
    assert len(feat) == 5
    # All columns must be numeric
    for col in feat.columns:
        assert pd.api.types.is_numeric_dtype(feat[col]), f"{col} is not numeric"


def test_feature_engineering_handles_nan_diffs():
    """MISSING_IN_GST rows have None diffs — should be filled with 0."""
    row = {
        "invoice_no": "S001",
        "invoice_date": "2026-07-01",
        "gstin": "29AAAAA1111A1Z5",
        "taxable_value": 50000.0,
        "gst_amount": 9000.0,
        "taxable_value_diff": None,
        "gst_amount_diff": None,
        "status": "MISSING_IN_GST",
        "explanation": "Missing",
    }
    df = pd.DataFrame([row])
    feat = _engineer_features(df)
    assert feat["abs_taxable_diff"].iloc[0] == 0.0
    assert feat["abs_gst_diff"].iloc[0] == 0.0
    assert feat["is_missing"].iloc[0] == 1.0


def test_feature_engineering_handles_empty_df():
    df = pd.DataFrame(columns=["invoice_no", "taxable_value", "gst_amount",
                                "taxable_value_diff", "gst_amount_diff", "status"])
    feat = _engineer_features(df)
    assert feat.empty


def test_feature_engineering_invalid_numeric_strings():
    """Non-numeric values in numeric columns should become NaN, not crash."""
    row = {
        "invoice_no": "S001",
        "taxable_value": "abc",
        "gst_amount": "xyz",
        "taxable_value_diff": None,
        "gst_amount_diff": None,
        "status": "MATCH",
    }
    feat = _engineer_features(pd.DataFrame([row]))
    # taxable_value and gst_amount parse as NaN — should not raise
    assert len(feat) == 1


# ─── score_reconciliation tests ───────────────────────────────────────────────

def test_score_reconciliation_returns_all_rows():
    sales_df = make_sales_df(20)
    purchase_df = make_purchase_df(15)
    scored, meta = score_reconciliation(sales_df, purchase_df)
    assert meta["ml_available"] is True
    assert meta["n_records_used"] == 35
    # Every row should be in the result
    assert len(scored) == 35


def test_score_reconciliation_all_rows_have_ml_fields():
    sales_df = make_sales_df(15)
    scored, _ = score_reconciliation(sales_df, pd.DataFrame())
    for row in scored:
        assert "ml_score" in row
        assert "ml_is_outlier" in row
        assert "ml_feature_summary" in row
        assert isinstance(row["ml_score"], float)
        assert isinstance(row["ml_is_outlier"], bool)


def test_score_reconciliation_small_dataset_returns_unavailable():
    """Fewer than MIN_RECORDS_FOR_ML rows must NOT produce ML results."""
    sales_df = make_sales_df(MIN_RECORDS_FOR_ML - 1)
    scored, meta = score_reconciliation(sales_df, pd.DataFrame())
    assert meta["ml_available"] is False
    assert len(scored) == 0
    assert str(MIN_RECORDS_FOR_ML) in meta["reason"]


def test_score_reconciliation_empty_inputs():
    scored, meta = score_reconciliation(pd.DataFrame(), pd.DataFrame())
    assert meta["ml_available"] is False
    assert len(scored) == 0


def test_score_reconciliation_exactly_minimum_records():
    """Exactly MIN_RECORDS_FOR_ML rows should produce results."""
    sales_df = make_sales_df(MIN_RECORDS_FOR_ML)
    scored, meta = score_reconciliation(sales_df, pd.DataFrame())
    assert meta["ml_available"] is True
    assert len(scored) == MIN_RECORDS_FOR_ML


def test_score_reconciliation_outlier_fraction_reasonable():
    """With contamination=0.15, outlier fraction should be around 15%."""
    sales_df = make_sales_df(50)
    purchase_df = make_purchase_df(30)
    scored, meta = score_reconciliation(sales_df, purchase_df, contamination=0.15)
    assert meta["ml_available"] is True
    outlier_count = sum(1 for r in scored if r["ml_is_outlier"])
    assert meta["n_outliers"] == outlier_count
    # Fraction should be approximately 15% — allow some tolerance
    fraction = outlier_count / len(scored)
    assert 0.05 <= fraction <= 0.30, f"Outlier fraction {fraction:.2f} outside expected range"


# ─── get_ml_anomalies tests ───────────────────────────────────────────────────

def test_get_ml_anomalies_schema():
    """Returned anomaly dicts must match the anomaly service schema."""
    sales_df = make_sales_df(25)
    purchase_df = make_purchase_df(20)
    anomalies, meta = get_ml_anomalies(sales_df, purchase_df)
    # May or may not have anomalies, but meta must be present
    assert isinstance(meta, dict)
    assert "ml_available" in meta
    for a in anomalies:
        for field in ("id", "invoice_no", "gstin", "source", "date",
                      "type", "severity", "difference", "explanation",
                      "action_recommended", "ml_score", "ml_is_outlier"):
            assert field in a, f"Missing field '{field}' in ML anomaly"
        assert a["type"] == "ML_UNUSUAL_PATTERN"
        assert a["severity"] in ("HIGH", "MEDIUM", "LOW")
        assert isinstance(a["ml_score"], float)
        assert isinstance(a["ml_is_outlier"], bool)
        assert a["ml_is_outlier"] is True  # only outliers returned


def test_get_ml_anomalies_no_fraud_label():
    """ML explanations must NOT mention 'fraud' or 'tax evasion'."""
    sales_df = make_sales_df(25)
    anomalies, _ = get_ml_anomalies(sales_df, pd.DataFrame())
    for a in anomalies:
        explanation_lower = a["explanation"].lower()
        action_lower = a["action_recommended"].lower()
        assert "fraud" not in explanation_lower, "ML output must not mention fraud"
        assert "evasion" not in explanation_lower, "ML output must not mention tax evasion"
        assert "fraud" not in action_lower
        assert "evasion" not in action_lower


def test_get_ml_anomalies_small_dataset_graceful():
    """Small dataset should return empty anomaly list with clear explanation, not crash."""
    tiny_df = make_sales_df(3)
    anomalies, meta = get_ml_anomalies(tiny_df, pd.DataFrame())
    assert anomalies == []
    assert meta["ml_available"] is False
    assert meta["reason"]  # Must provide a human-readable reason


def test_get_ml_anomalies_all_nan_values():
    """Rows with all-NaN features should be handled gracefully."""
    df = pd.DataFrame([{
        "invoice_no": f"X{i}",
        "invoice_date": "2026-07-01",
        "gstin": "",
        "taxable_value": None,
        "gst_amount": None,
        "taxable_value_diff": None,
        "gst_amount_diff": None,
        "status": "MISSING_IN_GST",
        "explanation": "",
    } for i in range(15)])
    # Should not crash — either return empty or provide meta
    try:
        anomalies, meta = get_ml_anomalies(df, pd.DataFrame())
        assert isinstance(anomalies, list)
        assert isinstance(meta, dict)
    except Exception as exc:
        pytest.fail(f"get_ml_anomalies raised unexpectedly: {exc}")
