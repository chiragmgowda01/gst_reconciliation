"""
GST API Integration Adapter
============================
This module provides a provider-independent integration interface for connecting
to an authorised GST Suvidha Provider (GSP) or the official GST API gateway.

IMPORTANT — Current Status:
    No live GST API credentials or provider have been selected/authorized.
    This module implements the full interface and an offline mock/fixture adapter
    for testing and demonstration purposes.

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
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


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
    def get_gstr1(self, gstin: str, tax_period: str) -> List[Dict[str, Any]]:
        """
        Fetch GSTR-1 outward supply invoices for a given GSTIN and period.

        Parameters
        ----------
        gstin : str — 15-character GSTIN of the taxpayer
        tax_period : str — Period in MMYYYY format (GST API convention)

        Returns
        -------
        Normalised list of invoice dicts compatible with the internal CSV schema:
          invoice_no, invoice_date, gstin, taxable_value, gst_amount
        """

    @abstractmethod
    def get_gstr2a(self, gstin: str, tax_period: str) -> List[Dict[str, Any]]:
        """Fetch GSTR-2A auto-drafted inward supply invoices."""

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
# Mock / Fixture adapter (for tests and labelled demo mode)
# ─────────────────────────────────────────────────────────────

class MockGstAdapter(GstApiAdapter):
    """
    Offline mock adapter that returns clearly-labelled fixture data.

    IMPORTANT: This adapter MUST NEVER be used to present data as live GST records.
    All responses include `is_mock_data: true` to prevent ambiguity.

    Use cases:
    - Unit and integration tests
    - Demonstrations when no live GSP credentials are available
    - Local development without internet access
    """

    FIXTURE_PERIOD = "072026"  # July 2026 in GST API MMYYYY format

    def authenticate(self) -> None:
        logger.info("[MockGstAdapter] No authentication required for mock adapter.")

    def get_gstr1(self, gstin: str, tax_period: str) -> List[Dict[str, Any]]:
        logger.info(
            "[MockGstAdapter] Returning mock GSTR-1 data for GSTIN=%s period=%s",
            gstin[:6] + "XXXX" if gstin else "UNKNOWN",  # Mask most of GSTIN in logs
            tax_period,
        )
        return [
            {
                "invoice_no": "MOCK-S001",
                "invoice_date": "2026-07-02",
                "gstin": "29ABCDE1234F1Z5",
                "taxable_value": 45000.0,
                "gst_amount": 8100.0,
                "is_mock_data": True,
                "source": "gstr1_api",
            },
            {
                "invoice_no": "MOCK-S002",
                "invoice_date": "2026-07-10",
                "gstin": "29BCDEF2345G1Z6",
                "taxable_value": 72500.0,
                "gst_amount": 13050.0,
                "is_mock_data": True,
                "source": "gstr1_api",
            },
        ]

    def get_gstr2a(self, gstin: str, tax_period: str) -> List[Dict[str, Any]]:
        logger.info("[MockGstAdapter] Returning mock GSTR-2A data.")
        return [
            {
                "invoice_no": "MOCK-P001",
                "invoice_date": "2026-07-03",
                "gstin": "29PQRST1234A1Z1",
                "taxable_value": 85000.0,
                "gst_amount": 15300.0,
                "is_mock_data": True,
                "source": "gstr2a_api",
            },
        ]

    def get_gstr3b_summary(self, gstin: str, tax_period: str) -> Dict[str, Any]:
        logger.info("[MockGstAdapter] Returning mock GSTR-3B summary.")
        return {
            "tax_period": "2026-07",
            "output_tax": 143190.0,
            "eligible_itc": 43470.0,
            "itc_reversed": 1200.0,
            "net_itc": 42270.0,
            "is_mock_data": True,
        }

    def healthcheck(self) -> Dict[str, Any]:
        return {"status": "ok", "provider": "mock", "is_mock": True}


# ─────────────────────────────────────────────────────────────
# Factory
# ─────────────────────────────────────────────────────────────

def get_gst_adapter() -> GstApiAdapter:
    """
    Factory function — returns the appropriate adapter based on environment config.

    Currently only the mock adapter is implemented.

    To add a live adapter:
    1. Implement a subclass of GstApiAdapter for your GSP.
    2. Add a mapping here: e.g. {"nsdl": NsdlGspAdapter, "karvy": KarvyGspAdapter}
    3. Set GST_API_PROVIDER=nsdl (or your provider name) in backend/.env
    4. Ensure GST_API_BASE_URL, GST_API_CLIENT_ID, GST_API_CLIENT_SECRET are set.
    """
    provider = gst_config.provider.lower()

    if provider == "mock" or gst_config.demo_mode:
        logger.info(
            "[GstApiAdapter] Using mock adapter. "
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
# Response normalisation helpers
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
