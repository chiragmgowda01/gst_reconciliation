"""
GST API Integration Adapter
============================
This module provides a provider-independent integration interface for connecting
to an authorised GST Suvidha Provider (GSP) or the official GST API gateway.

IMPORTANT — Current Status:
    No live GST API credentials or provider have been selected/authorized.
    This module implements the full interface and an offline mock/fixture adapter
    that reads from the project's synthetic CSV data files.

    All responses are clearly labelled with:
        is_mock_data: true
        provider: "mock"
        data_source: "synthetic_csv"

    To enable live integration:
    1. Select an authorised GST Suvidha Provider (e.g. Karvy, NSDL, Tata Consultancy, etc.)
    2. Obtain API credentials from the GSP (client_id, client_secret, OTP-based auth)
    3. Set the environment variables listed in .env.example
    4. Implement a concrete GspAdapter subclass for your chosen provider

    Do NOT use fixture data as live GST data in production.
"""

from __future__ import annotations

import logging
import os
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Project root is two levels above this file: backend/services/ → backend/ → root/
_ROOT = Path(__file__).resolve().parents[2]
_DATA = _ROOT / "data"


# ─────────────────────────────────────────────────────────────
# Configuration (loaded from environment — never hardcoded)
# ─────────────────────────────────────────────────────────────

class GstApiConfig:
    """
    Reads GST API credentials from environment variables.
    All values are optional at import time; missing values raise at call time
    to give a clear error message.
    """

    @property
    def provider(self) -> str:
        return os.getenv("GST_API_PROVIDER", "mock")

    @property
    def base_url(self) -> Optional[str]:
        return os.getenv("GST_API_BASE_URL")

    @property
    def client_id(self) -> Optional[str]:
        return os.getenv("GST_API_CLIENT_ID")

    @property
    def client_secret(self) -> Optional[str]:
        return os.getenv("GST_API_CLIENT_SECRET")

    @property
    def timeout_seconds(self) -> int:
        return int(os.getenv("GST_API_TIMEOUT_SECONDS", "30"))

    @property
    def demo_mode(self) -> bool:
        return os.getenv("GST_API_DEMO_MODE", "true").lower() in ("1", "true", "yes")

    def validate(self) -> None:
        """Raise ValueError if required fields are missing for live mode."""
        if self.provider == "mock" or self.demo_mode:
            return
        missing = []
        if not self.base_url:
            missing.append("GST_API_BASE_URL")
        if not self.client_id:
            missing.append("GST_API_CLIENT_ID")
        if not self.client_secret:
            missing.append("GST_API_CLIENT_SECRET")
        if missing:
            raise ValueError(
                f"GST API configuration is incomplete. Missing environment variables: "
                f"{', '.join(missing)}. See backend/.env.example for setup instructions."
            )


gst_config = GstApiConfig()


# ─────────────────────────────────────────────────────────────
# GSTIN format validation helpers
# ─────────────────────────────────────────────────────────────

_GSTIN_RE = re.compile(
    # State code: 01–37 (00 and 38–99 are invalid)
    r"^(0[1-9]|[12][0-9]|3[0-7])"
    r"[A-Z]{5}"             # PAN first 5 alpha chars (uppercase only)
    r"[0-9]{4}"             # PAN 4 numeric chars
    r"[A-Z]"                # PAN 10th (entity type, uppercase only)
    r"[1-9A-Z]"             # Registration order (1–9, A–Z)
    r"Z"                    # Always literal 'Z'
    r"[0-9A-Z]$"            # Checksum character
)


def validate_gstin_format(gstin: str) -> bool:
    """
    Validate a GSTIN against its documented 15-character structural pattern.

    IMPORTANT: A format-valid GSTIN is NOT confirmed as registered or active.
    Format checks catch malformed strings only. Actual registration status
    can only be verified through the official GST Common Portal API.

    Note: Lowercase GSTINs are intentionally rejected — the official portal
    issues GSTINs in uppercase only. Callers must normalise case themselves
    if they want case-insensitive matching.
    """
    if not gstin or not isinstance(gstin, str):
        return False
    # Use fullmatch (not match) to reject strings with trailing characters.
    # Do NOT call .upper() — lowercase input is treated as invalid.
    return bool(_GSTIN_RE.fullmatch(gstin.strip()))


# ─────────────────────────────────────────────────────────────
# CSV loading utilities
# ─────────────────────────────────────────────────────────────

def _load_csv(filename: str, required_columns: List[str]) -> pd.DataFrame:
    """
    Load a CSV from the data directory with UTF-8-sig decoding.
    Raises FileNotFoundError or ValueError with clear messages.
    """
    path = _DATA / filename
    if not path.exists():
        raise FileNotFoundError(
            f"Required data file not found: {path}. "
            "Ensure the synthetic CSV fixtures are present in the data/ directory."
        )
    try:
        df = pd.read_csv(path, encoding="utf-8-sig", dtype=str)
    except Exception as exc:
        raise ValueError(f"Failed to parse CSV file '{filename}': {exc}") from exc

    df.columns = [c.strip() for c in df.columns]
    missing = [c for c in required_columns if c not in df.columns]
    if missing:
        raise ValueError(
            f"CSV file '{filename}' is missing required columns: {missing}. "
            f"Found columns: {list(df.columns)}"
        )
    return df


def _invoice_columns_outward() -> List[str]:
    return ["invoice_no", "invoice_date", "customer_gstin", "taxable_value", "gst_amount"]


def _invoice_columns_inward() -> List[str]:
    return ["invoice_no", "invoice_date", "supplier_gstin", "taxable_value", "gst_amount"]


def _filter_by_period(df: pd.DataFrame, tax_period: Optional[str], date_col: str = "invoice_date") -> pd.DataFrame:
    """
    Filter rows by tax_period (YYYY-MM) using the invoice date column.
    Returns all rows when tax_period is None or empty.
    """
    if not tax_period or df.empty:
        return df
    year_month = tax_period.strip()[:7]  # Ensure YYYY-MM
    # Match rows whose invoice_date starts with YYYY-MM
    mask = df[date_col].astype(str).str.startswith(year_month)
    return df[mask].copy()


def _filter_by_gstin(df: pd.DataFrame, counterparty_gstin: Optional[str], gstin_col: str) -> pd.DataFrame:
    """Filter rows by counterparty GSTIN (case-insensitive)."""
    if not counterparty_gstin or df.empty:
        return df
    return df[df[gstin_col].astype(str).str.upper() == counterparty_gstin.strip().upper()].copy()


def _df_to_records(df: pd.DataFrame, gstin_col: str, source: str, tax_period: Optional[str]) -> List[Dict[str, Any]]:
    """Convert a filtered invoice DataFrame to a list of normalised dicts."""
    records = []
    for _, row in df.iterrows():
        try:
            tv = float(str(row.get("taxable_value", 0)).replace(",", "") or 0)
            ga = float(str(row.get("gst_amount", 0)).replace(",", "") or 0)
        except (ValueError, TypeError):
            tv, ga = 0.0, 0.0
        records.append({
            "invoice_no": str(row.get("invoice_no", "")).strip(),
            "invoice_date": str(row.get("invoice_date", "")).strip(),
            "gstin": str(row.get(gstin_col, "")).strip(),
            "taxable_value": tv,
            "gst_amount": ga,
            "source": source,
            "is_mock_data": True,
            "data_source": "synthetic_csv",
            "provider": "mock",
            "tax_period": tax_period,
        })
    return records


# ─────────────────────────────────────────────────────────────
# Provider interface (Abstract Base Class)
# ─────────────────────────────────────────────────────────────

class GstApiAdapter(ABC):
    """
    Abstract interface for a GST API / GSP integration.

    Implement this class for each provider you intend to support.
    The concrete adapter handles authentication, request formatting,
    and response normalisation for that specific provider.
    """

    @abstractmethod
    def get_gstr1(
        self,
        gstin: str,
        tax_period: str,
        counterparty_gstin: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch GSTR-1 outward supply invoices for a given GSTIN and period.

        Parameters
        ----------
        gstin : str — 15-character GSTIN of the taxpayer
        tax_period : str — Period in YYYY-MM format
        counterparty_gstin : str, optional — Filter by customer GSTIN

        Returns
        -------
        Normalised list of invoice dicts compatible with the internal CSV schema:
          invoice_no, invoice_date, gstin, taxable_value, gst_amount
        """

    @abstractmethod
    def get_gstr2a(
        self,
        gstin: str,
        tax_period: str,
        counterparty_gstin: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch GSTR-2A auto-drafted inward supply invoices."""

    @abstractmethod
    def get_gstr2b(
        self,
        gstin: str,
        tax_period: str,
        counterparty_gstin: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch GSTR-2B static auto-drafted ITC statement invoices."""

    @abstractmethod
    def get_gstr3b_summary(self, gstin: str, tax_period: str) -> Dict[str, Any]:
        """
        Fetch GSTR-3B summary return values for a given period.

        Returns dict with keys:
          tax_period, output_tax, eligible_itc, itc_reversed, net_itc
        """

    @abstractmethod
    def authenticate(self) -> None:
        """Perform authentication / token refresh as required by the provider."""

    def healthcheck(self) -> Dict[str, Any]:
        """Optional healthcheck. Override in live adapters."""
        return {"status": "ok", "provider": "base"}


# ─────────────────────────────────────────────────────────────
# Mock / Fixture adapter — reads from synthetic CSV data files
# ─────────────────────────────────────────────────────────────

class MockGstAdapter(GstApiAdapter):
    """
    Offline mock adapter that reads from the project's synthetic CSV fixtures.

    Data sources:
        GSTR-1  → data/gstr1.csv      (outward supply filings on portal)
        GSTR-2A → data/gstr2a.csv     (dynamic inward from supplier filings)
        GSTR-2B → data/gstr2b.csv     (static auto-drafted ITC statement)
        GSTR-3B → data/gstr3b.csv     (monthly summary return)

    IMPORTANT:
        - data/sales_register.csv is the company's internal outward book — NOT gstr1.
        - data/purchase_register.csv is the company's internal inward book — NOT gstr2a/2b.
        - This adapter MUST NEVER be used to present data as live GST records.
        - All responses include `is_mock_data: true` and `provider: "mock"`.
        - GSTIN format validation is performed but does NOT confirm registration.
    """

    def authenticate(self) -> None:
        logger.info("[MockGstAdapter] No authentication required for mock/CSV adapter.")

    def healthcheck(self) -> Dict[str, Any]:
        return {
            "status": "ok",
            "provider": "mock",
            "is_mock_data": True,
            "data_source": "synthetic_csv",
            "note": (
                "This adapter reads from local synthetic CSV fixtures. "
                "No live GST portal connection is active."
            ),
        }

    def get_gstr1(
        self,
        gstin: str,
        tax_period: str,
        counterparty_gstin: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        logger.info(
            "[MockGstAdapter] Loading GSTR-1 from gstr1.csv for period=%s", tax_period
        )
        df = _load_csv("gstr1.csv", _invoice_columns_outward())
        df = _filter_by_period(df, tax_period)
        df = _filter_by_gstin(df, counterparty_gstin, "customer_gstin")
        return _df_to_records(df, "customer_gstin", "gstr1_csv", tax_period)

    def get_gstr2a(
        self,
        gstin: str,
        tax_period: str,
        counterparty_gstin: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        logger.info(
            "[MockGstAdapter] Loading GSTR-2A from gstr2a.csv for period=%s", tax_period
        )
        df = _load_csv("gstr2a.csv", _invoice_columns_inward())
        df = _filter_by_period(df, tax_period)
        df = _filter_by_gstin(df, counterparty_gstin, "supplier_gstin")
        return _df_to_records(df, "supplier_gstin", "gstr2a_csv", tax_period)

    def get_gstr2b(
        self,
        gstin: str,
        tax_period: str,
        counterparty_gstin: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        logger.info(
            "[MockGstAdapter] Loading GSTR-2B from gstr2b.csv for period=%s", tax_period
        )
        df = _load_csv("gstr2b.csv", _invoice_columns_inward())
        df = _filter_by_period(df, tax_period)
        df = _filter_by_gstin(df, counterparty_gstin, "supplier_gstin")
        return _df_to_records(df, "supplier_gstin", "gstr2b_csv", tax_period)

    def get_gstr3b_summary(self, gstin: str, tax_period: str) -> Dict[str, Any]:
        logger.info(
            "[MockGstAdapter] Loading GSTR-3B from gstr3b.csv for period=%s", tax_period
        )
        df = _load_csv("gstr3b.csv", ["tax_period", "output_tax", "eligible_itc", "itc_reversed", "net_itc"])

        # Filter by exact tax_period
        if tax_period:
            period_norm = tax_period.strip()[:7]
            matched = df[df["tax_period"].astype(str).str.strip() == period_norm]
        else:
            matched = df

        if matched.empty:
            # Return explicit empty signal — do not substitute another period silently
            return {
                "tax_period": tax_period,
                "output_tax": None,
                "eligible_itc": None,
                "itc_reversed": None,
                "net_itc": None,
                "is_mock_data": True,
                "data_source": "synthetic_csv",
                "provider": "mock",
                "found": False,
                "note": f"No GSTR-3B data found for tax period '{tax_period}' in the synthetic CSV fixture.",
            }

        row = matched.iloc[0]

        def _safe(col: str) -> Optional[float]:
            try:
                return float(str(row.get(col, "") or "").replace(",", ""))
            except (ValueError, TypeError):
                return None

        return {
            "tax_period": str(row.get("tax_period", tax_period)).strip(),
            "output_tax": _safe("output_tax"),
            "eligible_itc": _safe("eligible_itc"),
            "itc_reversed": _safe("itc_reversed"),
            "net_itc": _safe("net_itc"),
            "is_mock_data": True,
            "data_source": "synthetic_csv",
            "provider": "mock",
            "found": True,
        }


# ─────────────────────────────────────────────────────────────
# Factory
# ─────────────────────────────────────────────────────────────

def get_gst_adapter() -> GstApiAdapter:
    """
    Factory function — returns the appropriate adapter based on environment config.

    Currently only the mock/CSV adapter is implemented.

    To add a live adapter:
    1. Implement a subclass of GstApiAdapter for your GSP.
    2. Add a mapping here: e.g. {"nsdl": NsdlGspAdapter, "karvy": KarvyGspAdapter}
    3. Set GST_API_PROVIDER=nsdl (or your provider name) in backend/.env
    4. Ensure GST_API_BASE_URL, GST_API_CLIENT_ID, GST_API_CLIENT_SECRET are set.
    """
    provider = gst_config.provider.lower()

    if provider == "mock" or gst_config.demo_mode:
        logger.info(
            "[GstApiAdapter] Using mock/CSV adapter. "
            "Set GST_API_PROVIDER and GST_API_DEMO_MODE=false for live integration."
        )
        return MockGstAdapter()

    # Future provider implementations go here
    # if provider == "nsdl":
    #     gst_config.validate()
    #     return NsdlGspAdapter(gst_config)
    # if provider == "karvy":
    #     gst_config.validate()
    #     return KarvyGspAdapter(gst_config)

    raise NotImplementedError(
        f"GST API provider '{provider}' is not yet implemented. "
        "Currently supported: mock. "
        "See backend/services/gst_api_adapter.py for implementation instructions."
    )


# ─────────────────────────────────────────────────────────────
# Response normalisation helpers (preserved for compatibility)
# ─────────────────────────────────────────────────────────────

def normalise_invoice(raw: Dict[str, Any], source_type: str) -> Dict[str, Any]:
    """
    Normalise a raw provider invoice response to the internal schema.
    Safe defaults prevent KeyError on partial responses.
    """
    return {
        "invoice_no": str(raw.get("invoice_no") or raw.get("inum") or ""),
        "invoice_date": str(raw.get("invoice_date") or raw.get("idt") or ""),
        "gstin": str(raw.get("gstin") or raw.get("ctin") or ""),
        "taxable_value": float(raw.get("taxable_value") or raw.get("val") or 0),
        "gst_amount": float(raw.get("gst_amount") or raw.get("igst") or 0),
        "source": source_type,
    }


def validate_api_response(data: Any, expected_type: type, context: str) -> Any:
    """Simple type validation for API response objects."""
    if not isinstance(data, expected_type):
        raise ValueError(
            f"Invalid GST API response for {context}: "
            f"expected {expected_type.__name__}, got {type(data).__name__}."
        )
    return data
