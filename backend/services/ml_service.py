"""
Isolation Forest ML Service
============================
Complements the deterministic rule-based anomaly detection with unsupervised
anomaly scoring.  Identifies statistically unusual transaction patterns in the
reconciliation dataset without replacing any existing rules.

Design principles:
- Feature engineering uses only fields reliably present in reconciliation output.
- A minimum of 10 usable records is required for meaningful ML ranking; smaller
  datasets return a "ml_unavailable" status with a clear explanation.
- Anomaly scores are reported as-is; they are NOT labelled as fraud or tax evasion.
- The service is stateless: the model is fit fresh on each request (no persistence)
  because the dataset is small and user-uploaded data changes between sessions.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

try:
    from sklearn.ensemble import IsolationForest
    from sklearn.preprocessing import StandardScaler
    _SKLEARN_AVAILABLE = True
except ImportError:  # pragma: no cover
    _SKLEARN_AVAILABLE = False

logger = logging.getLogger(__name__)

# Minimum number of usable (non-NaN) rows needed before fitting a model.
# Below this threshold the scores are statistically meaningless.
MIN_RECORDS_FOR_ML = 10


def _engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Derive a numeric feature matrix from a reconciliation DataFrame.

    Input columns expected (from reconcile()):
      invoice_no, invoice_date, gstin,
      taxable_value, gst_amount,
      taxable_value_diff, gst_amount_diff,
      status, explanation

    Returns a DataFrame with only numeric feature columns.
    Rows where ALL features are NaN are dropped.
    """
    feat = pd.DataFrame(index=df.index)

    # Raw financial magnitude
    feat["taxable_value"] = pd.to_numeric(df.get("taxable_value"), errors="coerce")
    feat["gst_amount"] = pd.to_numeric(df.get("gst_amount"), errors="coerce")

    # Difference magnitude (fills NaN for MISSING/EXTRA records)
    feat["abs_taxable_diff"] = pd.to_numeric(df.get("taxable_value_diff"), errors="coerce").abs()
    feat["abs_gst_diff"] = pd.to_numeric(df.get("gst_amount_diff"), errors="coerce").abs()

    # Percentage taxable-value difference (guard against division by zero)
    tv = feat["taxable_value"].replace(0, np.nan)
    feat["pct_taxable_diff"] = (feat["abs_taxable_diff"] / tv * 100).clip(0, 200)

    # Effective GST rate implied by the taxable value (when both present)
    feat["implied_gst_rate"] = (feat["gst_amount"] / tv * 100).clip(0, 50)

    # Binary indicator: record has ANY difference
    feat["has_diff"] = (
        (feat["abs_taxable_diff"].fillna(0) > 0) |
        (feat["abs_gst_diff"].fillna(0) > 0)
    ).astype(float)

    # Binary indicator: record is missing from one side
    if "status" in df.columns:
        feat["is_missing"] = (df["status"] == "MISSING_IN_GST").astype(float)
        feat["is_extra"] = (df["status"] == "EXTRA_IN_GST").astype(float)
    else:
        feat["is_missing"] = 0.0
        feat["is_extra"] = 0.0

    # Fill NaN numeric differences with 0 (missing / extra records have no diff)
    feat["abs_taxable_diff"] = feat["abs_taxable_diff"].fillna(0)
    feat["abs_gst_diff"] = feat["abs_gst_diff"].fillna(0)
    feat["pct_taxable_diff"] = feat["pct_taxable_diff"].fillna(0)

    return feat


def score_reconciliation(
    sales_df: pd.DataFrame,
    purchase_df: pd.DataFrame,
    contamination: float = 0.15,
    random_state: int = 42,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Fit an IsolationForest on the combined reconciliation data and return
    per-row anomaly scores.

    Parameters
    ----------
    sales_df, purchase_df : reconcile() output DataFrames
    contamination : expected proportion of outliers (default 15%)
    random_state : reproducibility seed

    Returns
    -------
    scored_rows : list of dicts with original row data plus ML fields:
        - ml_score      : raw IsolationForest decision function score
                          (more negative = more anomalous)
        - ml_is_outlier : bool — True if classified as outlier by IF
        - ml_feature_summary : short string describing dominant unusual feature
        - source        : "sales" | "purchase"

    meta : dict with keys:
        - ml_available  : bool
        - reason        : str (why ML is/isn't available)
        - n_records_used: int
        - n_outliers    : int
        - contamination : float
    """
    if not _SKLEARN_AVAILABLE:
        return [], {
            "ml_available": False,
            "reason": "scikit-learn is not installed in this environment.",
            "n_records_used": 0,
            "n_outliers": 0,
            "contamination": contamination,
        }

    # Combine both DataFrames, tagging source
    frames: List[pd.DataFrame] = []
    if not sales_df.empty:
        s = sales_df.copy()
        s["_source"] = "sales"
        frames.append(s)
    if not purchase_df.empty:
        p = purchase_df.copy()
        p["_source"] = "purchase"
        frames.append(p)

    if not frames:
        return [], {
            "ml_available": False,
            "reason": "No reconciliation records available to analyse.",
            "n_records_used": 0,
            "n_outliers": 0,
            "contamination": contamination,
        }

    combined = pd.concat(frames, ignore_index=True)
    features = _engineer_features(combined)

    # Drop rows where all features are NaN (completely unusable)
    usable_mask = features.notna().any(axis=1)
    usable_features = features[usable_mask].fillna(0)
    usable_combined = combined[usable_mask].reset_index(drop=True)
    usable_features = usable_features.reset_index(drop=True)

    n_usable = len(usable_features)
    if n_usable < MIN_RECORDS_FOR_ML:
        return [], {
            "ml_available": False,
            "reason": (
                f"Only {n_usable} usable records found. At least {MIN_RECORDS_FOR_ML} "
                "are required for Isolation Forest to produce meaningful anomaly rankings. "
                "Deterministic rules are still active."
            ),
            "n_records_used": n_usable,
            "n_outliers": 0,
            "contamination": contamination,
        }

    # Scale features
    scaler = StandardScaler()
    X = scaler.fit_transform(usable_features.values)

    # Fit Isolation Forest
    clf = IsolationForest(
        contamination=contamination,
        random_state=random_state,
        n_estimators=100,
    )
    clf.fit(X)

    raw_scores = clf.decision_function(X)   # higher = more normal
    predictions = clf.predict(X)            # -1 = outlier, 1 = inlier

    n_outliers = int((predictions == -1).sum())

    # Build per-row output
    scored_rows: List[Dict[str, Any]] = []
    feat_cols = usable_features.columns.tolist()

    for i in range(n_usable):
        row = usable_combined.iloc[i].to_dict()
        row_feat = usable_features.iloc[i]
        score = float(raw_scores[i])
        is_outlier = bool(predictions[i] == -1)

        # Produce a human-readable feature summary for why this row scored low
        feature_summary = _explain_features(row_feat, feat_cols, is_outlier)

        scored_rows.append({
            **{k: v for k, v in row.items() if not k.startswith("_")},
            "source": row.get("_source", "unknown"),
            "ml_score": round(score, 4),
            "ml_is_outlier": is_outlier,
            "ml_feature_summary": feature_summary,
        })

    meta: Dict[str, Any] = {
        "ml_available": True,
        "reason": "Isolation Forest analysis completed.",
        "n_records_used": n_usable,
        "n_outliers": n_outliers,
        "contamination": contamination,
    }

    return scored_rows, meta


def _explain_features(row_feat: pd.Series, feat_cols: List[str], is_outlier: bool) -> str:
    """
    Produce a brief natural-language summary of which features make this
    record unusual.  Avoids legal conclusions; only reports observed values.
    """
    if not is_outlier:
        return "No unusual numerical pattern detected."

    parts: List[str] = []

    tv = float(row_feat.get("taxable_value", 0) or 0)
    gst = float(row_feat.get("gst_amount", 0) or 0)
    abs_tv_diff = float(row_feat.get("abs_taxable_diff", 0) or 0)
    abs_gst_diff = float(row_feat.get("abs_gst_diff", 0) or 0)
    pct_diff = float(row_feat.get("pct_taxable_diff", 0) or 0)
    implied_rate = float(row_feat.get("implied_gst_rate", 0) or 0)
    is_missing = float(row_feat.get("is_missing", 0) or 0)
    is_extra = float(row_feat.get("is_extra", 0) or 0)

    if tv > 500_000:
        parts.append(f"unusually high taxable value (₹{tv:,.0f})")
    if abs_tv_diff > 10_000:
        parts.append(f"large taxable-value difference (₹{abs_tv_diff:,.0f})")
    if abs_gst_diff > 2_000:
        parts.append(f"large GST-amount difference (₹{abs_gst_diff:,.0f})")
    if pct_diff > 20:
        parts.append(f"high percentage discrepancy ({pct_diff:.1f}%)")
    if implied_rate > 0 and (implied_rate < 3 or implied_rate > 30):
        parts.append(f"atypical implied GST rate ({implied_rate:.1f}%)")
    if is_missing:
        parts.append("invoice absent from GST portal")
    if is_extra:
        parts.append("invoice not in internal books")

    if not parts:
        parts.append("combination of numerical features is statistically unusual")

    return "ML pattern: " + "; ".join(parts) + ". Recommend manual review."


def get_ml_anomalies(
    sales_df: pd.DataFrame,
    purchase_df: pd.DataFrame,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Public entry point.  Returns (ml_anomaly_list, meta).

    ml_anomaly_list items are formatted to match the anomaly service schema:
        id, invoice_no, gstin, source, date, type, severity,
        difference, explanation, action_recommended,
        ml_score, ml_is_outlier, ml_feature_summary
    """
    try:
        scored_rows, meta = score_reconciliation(sales_df, purchase_df)
    except Exception as exc:
        logger.warning("ML scoring failed: %s", exc, exc_info=True)
        return [], {
            "ml_available": False,
            "reason": f"ML scoring encountered an error: {type(exc).__name__}.",
            "n_records_used": 0,
            "n_outliers": 0,
            "contamination": 0.15,
        }

    anomalies: List[Dict[str, Any]] = []
    for row in scored_rows:
        if not row.get("ml_is_outlier"):
            continue

        inv_no = str(row.get("invoice_no", ""))
        src_label = (
            "Sales (Register ↔ GSTR-1)"
            if row.get("source") == "sales"
            else "Purchase (Register ↔ GSTR-2A)"
        )
        score = row.get("ml_score", 0.0)
        # Severity: more negative score → higher severity
        severity = "HIGH" if score < -0.15 else "MEDIUM"

        anomalies.append({
            "id": f"ml-{row.get('source', 'unk')}-{inv_no}",
            "invoice_no": inv_no,
            "gstin": str(row.get("gstin", "")),
            "source": src_label,
            "date": str(row.get("invoice_date", "")),
            "type": "ML_UNUSUAL_PATTERN",
            "severity": severity,
            "difference": round(
                abs(float(row.get("abs_taxable_diff") or 0)) +
                abs(float(row.get("abs_gst_diff") or 0)),
                2
            ),
            "explanation": row.get("ml_feature_summary", "Unusual numerical pattern detected."),
            "action_recommended": (
                "Isolation Forest identified this transaction as statistically unusual "
                "compared to the rest of the dataset. Review the underlying invoice and "
                "supporting documents. This flag does NOT imply any legal violation."
            ),
            "ml_score": row.get("ml_score"),
            "ml_is_outlier": True,
            "ml_feature_summary": row.get("ml_feature_summary", ""),
        })

    return anomalies, meta
