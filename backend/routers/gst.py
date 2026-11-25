"""
GST Simulator Router
====================
Provides a set of read-only demonstration endpoints that expose the project's
synthetic CSV fixtures through a REST API shaped like a GST Suvidha Provider.

Prefix: /gst

Endpoints:
    GET  /gst/status           — Provider/adapter status and demo-mode declaration
    POST /gst/gstin/verify     — GSTIN format check + demo-fixture lookup
    GET  /gst/gstr1            — GSTR-1 outward supply filings (data/gstr1.csv)
    GET  /gst/gstr2a           — GSTR-2A dynamic ITC register (data/gstr2a.csv)
    GET  /gst/gstr2b           — GSTR-2B static auto-drafted ITC (data/gstr2b.csv)
    GET  /gst/gstr3b           — GSTR-3B monthly summary return (data/gstr3b.csv)

SAFETY GUARANTEES:
    * Every response is labelled is_mock_data=true and data_source="synthetic_csv".
    * No live GST portal connection is claimed or attempted.
    * GSTIN format validation does NOT confirm actual registration status.
    * GET requests are strictly read-only; no invoice records are created as a side effect.
    * Global synthetic fixtures are shared demo data and do not belong to any
      specific registered business — they are explicitly labelled as such.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from models.models import Business, GSTR3BReturn, Invoice, User
from services.auth import get_current_business, get_current_user
from services.import_batch import (
    add_gstr3b_batch_item,
    add_invoice_batch_item,
    complete_import_batch,
    create_import_batch,
    is_unique_constraint_violation,
)
from services.validation import parse_date_safely, validate_gstr3b_row, validate_invoice_row
from sqlalchemy import select
from services.gst_api_adapter import (
    MockGstAdapter,
    _DATA,
    _load_csv,
    _invoice_columns_outward,
    _invoice_columns_inward,
    gst_config,
    get_gst_adapter,
    validate_gstin_format,
)

router = APIRouter(prefix="/gst", tags=["GST Simulator"])

# ─────────────────────────────────────────────────────────────
# Period validation helper
# ─────────────────────────────────────────────────────────────

_PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _require_valid_period(tax_period: Optional[str]) -> str:
    """Validate and return a normalised YYYY-MM period string."""
    if not tax_period:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="tax_period is required. Provide it in YYYY-MM format (e.g., 2026-07).",
        )
    p = tax_period.strip()
    if not _PERIOD_RE.match(p):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Invalid tax_period '{p}'. Expected YYYY-MM with month between 01 and 12, "
                "e.g., 2026-07."
            ),
        )
    return p


# ─────────────────────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────────────────────

class GstinVerifyRequest(BaseModel):
    gstin: str = Field(..., min_length=15, max_length=15, description="15-character GSTIN to verify")


class GstImportRequest(BaseModel):
    return_type: str = Field(..., description="Target return to import: gstr1, gstr2a, or gstr2b")
    tax_period: str = Field(..., description="Tax period in YYYY-MM format, e.g. 2026-07")
    counterparty_gstin: Optional[str] = Field(None, description="Optional counterparty GSTIN filter")


class Gstr3bImportRequest(BaseModel):
    tax_period: str = Field(..., description="Tax period in YYYY-MM format, e.g. 2026-07")


# ─────────────────────────────────────────────────────────────
# /gst/status
# ─────────────────────────────────────────────────────────────

@router.get(
    "/status",
    summary="GST Adapter Status",
    response_description="Provider status, demo mode declaration and data source information",
)
def gst_status(
    business: Business = Depends(get_current_business),
) -> Dict[str, Any]:
    """
    Returns the current GST adapter's operational status.

    **Safety note**: This endpoint always reflects the mock/CSV adapter in demo mode.
    No live GST portal connection is claimed.
    """
    adapter = get_gst_adapter()
    hc = adapter.healthcheck()
    return {
        "adapter_type": type(adapter).__name__,
        "provider": gst_config.provider,
        "demo_mode": gst_config.demo_mode,
        "is_mock_data": True,
        "data_source": "synthetic_csv",
        "data_directory": str(_DATA),
        "available_fixtures": [
            "gstr1.csv",
            "gstr2a.csv",
            "gstr2b.csv",
            "gstr3b.csv",
        ],
        "healthcheck": hc,
        "live_integration_status": "not_configured",
        "note": (
            "This system is operating in DEMO MODE using synthetic CSV fixtures. "
            "No connection to the live GST Common Portal or any GSP is active. "
            "Data returned by all /gst/* endpoints is simulated and must not be "
            "used for actual tax filings or compliance decisions."
        ),
        "business_id": business.id,
        "business_name": business.name,
    }


# ─────────────────────────────────────────────────────────────
# /gst/gstin/verify
# ─────────────────────────────────────────────────────────────

@router.post(
    "/gstin/verify",
    summary="GSTIN Format Verification",
    response_description="Format validity and synthetic fixture lookup result",
)
def verify_gstin(
    payload: GstinVerifyRequest,
    business: Business = Depends(get_current_business),
) -> Dict[str, Any]:
    """
    Checks a GSTIN's structural format and optionally whether it appears
    in the synthetic CSV fixtures.

    **Critical disclaimer**: This endpoint performs a *format check only*.
    - `format_valid=true` means the string matches the documented GSTIN pattern.
    - `found_in_demo_fixtures=true` means the GSTIN appears in a synthetic CSV row.
    - `gstn_verified` is **always false** — actual GST registration status can
      only be confirmed through the official GST Common Portal API.
    - No live API call is made.
    """
    gstin = payload.gstin.strip().upper()
    fmt_valid = validate_gstin_format(gstin)

    # Search the synthetic CSV fixtures for this GSTIN
    found_in = []
    fixture_checks = [
        ("gstr1.csv", _invoice_columns_outward(), "customer_gstin"),
        ("gstr2a.csv", _invoice_columns_inward(), "supplier_gstin"),
        ("gstr2b.csv", _invoice_columns_inward(), "supplier_gstin"),
    ]
    for fname, req_cols, gcol in fixture_checks:
        try:
            df = _load_csv(fname, req_cols)
            if gstin in df[gcol].astype(str).str.strip().str.upper().values:
                found_in.append(fname)
        except (FileNotFoundError, ValueError):
            pass

    return {
        "gstin": gstin,
        "format_valid": fmt_valid,
        "found_in_demo_fixtures": bool(found_in),
        "fixture_files_containing_gstin": found_in,
        "gstn_verified": False,
        "is_mock_data": True,
        "data_source": "synthetic_csv",
        "provider": "mock",
        "disclaimer": (
            "This is a FORMAT CHECK only using synthetic demo data. "
            "A format-valid GSTIN is NOT confirmed as registered or active on the GST portal. "
            "Presence in demo fixtures does not indicate a real registered entity. "
            "Actual GST registration verification requires a connection to the official "
            "GST Common Portal API, which is not configured in this demo environment."
        ),
    }


# ─────────────────────────────────────────────────────────────
# Internal helper: build standard invoice response envelope
# ─────────────────────────────────────────────────────────────

def _build_response(
    records: List[Dict[str, Any]],
    source_file: str,
    tax_period: str,
    return_type: str,
    business: Business,
    counterparty_gstin: Optional[str],
) -> Dict[str, Any]:
    return {
        "return_type": return_type,
        "tax_period": tax_period,
        "record_count": len(records),
        "records": records,
        "source_file": source_file,
        "is_mock_data": True,
        "data_source": "synthetic_csv",
        "provider": "mock",
        "counterparty_gstin_filter": counterparty_gstin or None,
        "business_id": business.id,
        "business_name": business.name,
        "disclaimer": (
            "Data is sourced from synthetic CSV fixtures for demonstration purposes only. "
            "These are NOT live GST portal records. Do not use for compliance filings."
        ),
    }


# ─────────────────────────────────────────────────────────────
# /gst/gstr1
# ─────────────────────────────────────────────────────────────

@router.get(
    "/gstr1",
    summary="GSTR-1 Outward Supply Filings",
    response_description="Outward supply invoices from gstr1.csv for the requested period",
)
def get_gstr1(
    tax_period: str = Query(..., description="Tax period in YYYY-MM format, e.g. 2026-07"),
    counterparty_gstin: Optional[str] = Query(None, description="Filter by customer GSTIN"),
    business: Business = Depends(get_current_business),
) -> Dict[str, Any]:
    """
    Returns GSTR-1 outward supply invoice records from the synthetic fixture `data/gstr1.csv`
    for the specified tax period.

    **Note**: `data/gstr1.csv` contains simulated outward portal filings.
    It is distinct from `data/sales_register.csv` (the company's internal outward ledger).
    """
    period = _require_valid_period(tax_period)
    adapter = get_gst_adapter()
    try:
        records = adapter.get_gstr1(
            gstin=business.gstin,
            tax_period=period,
            counterparty_gstin=counterparty_gstin,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    return _build_response(records, "gstr1.csv", period, "GSTR-1", business, counterparty_gstin)


# ─────────────────────────────────────────────────────────────
# /gst/gstr2a
# ─────────────────────────────────────────────────────────────

@router.get(
    "/gstr2a",
    summary="GSTR-2A Dynamic Inward Supply Register",
    response_description="Dynamic inward supply records from gstr2a.csv for the requested period",
)
def get_gstr2a(
    tax_period: str = Query(..., description="Tax period in YYYY-MM format, e.g. 2026-07"),
    counterparty_gstin: Optional[str] = Query(None, description="Filter by supplier GSTIN"),
    business: Business = Depends(get_current_business),
) -> Dict[str, Any]:
    """
    Returns GSTR-2A dynamic auto-drafted inward supply records from `data/gstr2a.csv`
    for the specified tax period.

    **Note**: `data/gstr2a.csv` contains simulated supplier portal filings.
    It is distinct from `data/purchase_register.csv` (the company's internal inward ledger).
    """
    period = _require_valid_period(tax_period)
    adapter = get_gst_adapter()
    try:
        records = adapter.get_gstr2a(
            gstin=business.gstin,
            tax_period=period,
            counterparty_gstin=counterparty_gstin,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    return _build_response(records, "gstr2a.csv", period, "GSTR-2A", business, counterparty_gstin)


# ─────────────────────────────────────────────────────────────
# /gst/gstr2b
# ─────────────────────────────────────────────────────────────

@router.get(
    "/gstr2b",
    summary="GSTR-2B Static Auto-Drafted ITC Statement",
    response_description="Static ITC records from gstr2b.csv for the requested period",
)
def get_gstr2b(
    tax_period: str = Query(..., description="Tax period in YYYY-MM format, e.g. 2026-07"),
    counterparty_gstin: Optional[str] = Query(None, description="Filter by supplier GSTIN"),
    business: Business = Depends(get_current_business),
) -> Dict[str, Any]:
    """
    Returns GSTR-2B static auto-drafted ITC statement records from `data/gstr2b.csv`
    for the specified tax period.

    GSTR-2B is the official cut-off statement used to determine eligible ITC under Rule 36(4).
    It differs from GSTR-2A in that it is locked at the period-end and not updated dynamically.
    """
    period = _require_valid_period(tax_period)
    adapter = get_gst_adapter()
    try:
        records = adapter.get_gstr2b(
            gstin=business.gstin,
            tax_period=period,
            counterparty_gstin=counterparty_gstin,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    return _build_response(records, "gstr2b.csv", period, "GSTR-2B", business, counterparty_gstin)


# ─────────────────────────────────────────────────────────────
# /gst/gstr3b
# ─────────────────────────────────────────────────────────────

@router.get(
    "/gstr3b",
    summary="GSTR-3B Monthly Summary Return",
    response_description="Monthly tax liability and ITC summary from gstr3b.csv for the exact requested period",
)
def get_gstr3b(
    tax_period: str = Query(..., description="Tax period in YYYY-MM format, e.g. 2026-07"),
    business: Business = Depends(get_current_business),
) -> Dict[str, Any]:
    """
    Returns the GSTR-3B monthly summary return from `data/gstr3b.csv`
    for the **exact** specified tax period.

    If no data exists for the requested period, the response will clearly
    indicate `found=false` with an explanatory note.
    No data from another period will be silently substituted.
    """
    period = _require_valid_period(tax_period)
    adapter = get_gst_adapter()
    try:
        summary = adapter.get_gstr3b_summary(gstin=business.gstin, tax_period=period)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    return {
        "return_type": "GSTR-3B",
        "tax_period": period,
        "summary": summary,
        "source_file": "gstr3b.csv",
        "is_mock_data": True,
        "data_source": "synthetic_csv",
        "provider": "mock",
        "business_id": business.id,
        "business_name": business.name,
        "disclaimer": (
            "Data is sourced from synthetic CSV fixtures for demonstration purposes only. "
            "These are NOT live GST portal records."
        ),
    }


def _fetch_gstr3b_fixture_summary(period: str, business: Business) -> Optional[dict[str, Any]]:
    """Read and validate one exact-period synthetic GSTR-3B fixture summary."""
    adapter = get_gst_adapter()
    try:
        fixture = adapter.get_gstr3b_summary(gstin=business.gstin, tax_period=period)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The synthetic GSTR-3B fixture is currently unavailable.",
        ) from None
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The synthetic GSTR-3B fixture could not be validated.",
        ) from None

    if fixture.get("found") is not True:
        return None
    if fixture.get("data_source") != "synthetic_csv":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Only the configured synthetic GSTR-3B fixture can be imported here.",
        )
    if str(fixture.get("tax_period") or "").strip() != period:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The fixture returned a different tax period than requested.",
        )

    _, validation_errors = validate_gstr3b_row(
        {
            "tax_period": fixture.get("tax_period"),
            "output_tax": fixture.get("output_tax"),
            "eligible_itc": fixture.get("eligible_itc"),
            "itc_reversed": fixture.get("itc_reversed"),
        },
        1,
    )
    values: dict[str, float] = {}
    invalid_fields = set()
    for field in ("output_tax", "eligible_itc", "itc_reversed", "net_itc"):
        raw = fixture.get(field)
        try:
            numeric = float(str(raw).replace(",", ""))
        except (TypeError, ValueError):
            invalid_fields.add(field)
            continue
        if not math.isfinite(numeric) or (field != "net_itc" and numeric < 0):
            invalid_fields.add(field)
            continue
        values[field] = numeric

    if validation_errors or invalid_fields:
        invalid_fields.update(
            field
            for field in ("output_tax", "eligible_itc", "itc_reversed")
            if any(field in error for error in validation_errors)
        )
        fields = ", ".join(sorted(invalid_fields)) or "tax summary values"
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"The synthetic GSTR-3B summary contains invalid values for: {fields}.",
        )

    return {"tax_period": period, **values}


def _gstr3b_record_values(record: GSTR3BReturn) -> dict[str, Any]:
    return {
        "tax_period": record.tax_period,
        "output_tax": float(record.output_tax),
        "eligible_itc": float(record.eligible_itc),
        "itc_reversed": float(record.itc_reversed),
        "net_itc": float(record.net_itc),
    }


def _gstr3b_values_match(existing: dict[str, Any], fixture: dict[str, Any]) -> bool:
    return all(
        round(float(existing[field]), 2) == round(float(fixture[field]), 2)
        for field in ("output_tax", "eligible_itc", "itc_reversed", "net_itc")
    )


def _gstr3b_import_no_data(period: str, business: Business) -> dict[str, Any]:
    return {
        "status": "no_data",
        "operation": "no_data",
        "tax_period": period,
        "business_name": business.name,
        "data_source": "synthetic_csv",
        "fixture_summary": None,
        "imported_count": 0,
        "duplicate_count": 0,
        "rejected_count": 0,
        "message": f"No synthetic GSTR-3B fixture data is available for {period}. Nothing was saved.",
    }


@router.post("/gstr3b/import/preview", summary="Preview a synthetic GSTR-3B summary import")
def preview_gstr3b_import(
    payload: Gstr3bImportRequest,
    business: Business = Depends(get_current_business),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Validate a fixture summary and compare it with the tenant's saved period; never writes."""
    period = _require_valid_period(payload.tax_period)
    if business.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Business access is not authorized.")

    fixture_values = _fetch_gstr3b_fixture_summary(period, business)
    if fixture_values is None:
        return _gstr3b_import_no_data(period, business)

    record = db.scalar(
        select(GSTR3BReturn).where(
            GSTR3BReturn.business_id == business.id,
            GSTR3BReturn.tax_period == period,
        )
    )
    was_soft_deleted = record is not None and record.deleted_at is not None
    existing_values = (
        _gstr3b_record_values(record)
        if record is not None and not was_soft_deleted
        else None
    )
    if existing_values is None:
        operation = "new_import"
        differences = None
        message = f"A new GSTR-3B summary will be saved for {period}."
    elif _gstr3b_values_match(existing_values, fixture_values):
        operation = "duplicate"
        differences = {field: 0.0 for field in ("output_tax", "eligible_itc", "itc_reversed", "net_itc")}
        message = f"The saved GSTR-3B summary for {period} already matches this fixture. No changes are needed."
    else:
        operation = "revision"
        differences = {
            field: round(fixture_values[field] - existing_values[field], 2)
            for field in ("output_tax", "eligible_itc", "itc_reversed", "net_itc")
        }
        message = f"The saved GSTR-3B summary for {period} differs from the fixture and will be revised if confirmed."

    return {
        "status": "preview",
        "operation": operation,
        "tax_period": period,
        "business_name": business.name,
        "fixture_summary": fixture_values,
        "existing_summary": existing_values,
        "differences": differences,
        "data_source": "synthetic_csv",
        "fixture_identifier": "gstr3b.csv",
        "message": message,
        "disclaimer": "Synthetic demonstration data only. These figures do not represent an actual filed GST return.",
    }


@router.post("/gstr3b/import", summary="Confirm a synthetic GSTR-3B summary import")
def confirm_gstr3b_import(
    payload: Gstr3bImportRequest,
    business: Business = Depends(get_current_business),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Refetch, validate, and transactionally save a confirmed monthly summary."""
    period = _require_valid_period(payload.tax_period)
    if business.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Business access is not authorized.")

    fixture_values = _fetch_gstr3b_fixture_summary(period, business)
    if fixture_values is None:
        return _gstr3b_import_no_data(period, business)

    record = db.scalar(
        select(GSTR3BReturn)
        .where(
            GSTR3BReturn.business_id == business.id,
            GSTR3BReturn.tax_period == period,
        )
        .with_for_update()
    )
    was_soft_deleted = record is not None and record.deleted_at is not None
    existing_values = (
        _gstr3b_record_values(record)
        if record is not None and not was_soft_deleted
        else None
    )
    if existing_values is not None and _gstr3b_values_match(existing_values, fixture_values):
        return {
            "status": "duplicate",
            "operation": "duplicate",
            "tax_period": period,
            "business_name": business.name,
            "imported_count": 0,
            "duplicate_count": 1,
            "rejected_count": 0,
            "summary": existing_values,
            "data_source": "database",
            "provenance": "No changes were made; the existing record and its original import batch remain in place.",
            "message": f"The saved GSTR-3B summary for {period} already matches. No revision or import batch was created.",
        }

    operation = "new_import" if record is None or was_soft_deleted else "revision"
    try:
        batch = create_import_batch(
            db,
            business_id=business.id,
            imported_by_user_id=current_user.id,
            source_category="gst_simulator",
            source_type="gstr3b",
            fixture_identifier="gstr3b.csv",
            tax_period=period,
            total_rows=1,
        )

        if record is None:
            record = GSTR3BReturn(
                business_id=business.id,
                tax_period=period,
                output_tax=fixture_values["output_tax"],
                eligible_itc=fixture_values["eligible_itc"],
                itc_reversed=fixture_values["itc_reversed"],
                net_itc=fixture_values["net_itc"],
                import_batch_id=batch.batch_id,
            )
            db.add(record)
            db.flush()
            add_gstr3b_batch_item(
                db,
                batch_id=batch.batch_id,
                outcome="imported",
                tax_period=period,
                gstr3b_return_id=record.id,
                new_values=fixture_values,
            )
        elif was_soft_deleted:
            # Reuse the unique tenant-period row. The deleted batch remains in
            # audit history, while this new import becomes its active owner.
            record.output_tax = fixture_values["output_tax"]
            record.eligible_itc = fixture_values["eligible_itc"]
            record.itc_reversed = fixture_values["itc_reversed"]
            record.net_itc = fixture_values["net_itc"]
            record.deleted_at = None
            record.import_batch_id = batch.batch_id
            add_gstr3b_batch_item(
                db,
                batch_id=batch.batch_id,
                outcome="imported",
                tax_period=period,
                gstr3b_return_id=record.id,
                new_values=fixture_values,
            )
        else:
            previous_values = existing_values
            record.output_tax = fixture_values["output_tax"]
            record.eligible_itc = fixture_values["eligible_itc"]
            record.itc_reversed = fixture_values["itc_reversed"]
            record.net_itc = fixture_values["net_itc"]
            add_gstr3b_batch_item(
                db,
                batch_id=batch.batch_id,
                outcome="revised",
                tax_period=period,
                gstr3b_return_id=record.id,
                previous_values=previous_values,
                new_values=fixture_values,
            )

        complete_import_batch(
            batch,
            imported_rows=0 if operation == "revision" else 1,
            duplicate_rows=0,
            revised_rows=1 if operation == "revision" else 0,
            rejected_rows=0,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if is_unique_constraint_violation(exc):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A GSTR-3B summary for this business and period changed concurrently. Refresh the preview and retry.",
            ) from None
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The GSTR-3B import could not be saved. All changes were rolled back.",
        ) from None
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The GSTR-3B import could not be saved. All changes were rolled back.",
        ) from None

    saved_values = _gstr3b_record_values(record)
    return {
        "status": "success",
        "operation": operation,
        "tax_period": period,
        "business_name": business.name,
        "import_batch_id": str(batch.batch_id),
        "imported_count": 1,
        "duplicate_count": 0,
        "rejected_count": 0,
        "summary": saved_values,
        "data_source": "database",
        "provenance": "Saved from synthetic fixture gstr3b.csv; this is not an actual filed GST return.",
        "message": (
            f"GSTR-3B summary for {period} was "
            f"{'revised' if operation == 'revision' else 'saved'} in this business database."
        ),
    }


# ─────────────────────────────────────────────────────────────
# Helper: Fetch Source Records from Server Adapter
# ─────────────────────────────────────────────────────────────

def _fetch_server_return_records(
    return_type: str,
    period: str,
    counterparty_gstin: Optional[str],
    business: Business,
) -> tuple[str, List[Dict[str, Any]]]:
    """
    Fetch return records server-side from MockGstAdapter.
    Never relies on client-submitted invoice records.
    """
    norm = (return_type or "").strip().lower()
    if norm == "gstr3b":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Form GSTR-3B is a monthly summary return, not invoice-level transactions. "
                "It cannot be imported into the invoice reconciliation ledger."
            ),
        )

    allowed = {"gstr1", "gstr2a", "gstr2b"}
    if norm not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid return_type '{return_type}'. Must be one of {sorted(list(allowed))}.",
        )

    adapter = get_gst_adapter()
    cp = counterparty_gstin.strip().upper() if counterparty_gstin and counterparty_gstin.strip() else None

    try:
        if norm == "gstr1":
            raw_records = adapter.get_gstr1(gstin=business.gstin, tax_period=period, counterparty_gstin=cp)
        elif norm == "gstr2a":
            raw_records = adapter.get_gstr2a(gstin=business.gstin, tax_period=period, counterparty_gstin=cp)
        else:  # gstr2b
            raw_records = adapter.get_gstr2b(gstin=business.gstin, tax_period=period, counterparty_gstin=cp)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    return norm, raw_records


# ─────────────────────────────────────────────────────────────
# /gst/import/preview
# ─────────────────────────────────────────────────────────────

@router.post(
    "/import/preview",
    summary="Preview GST Return Import",
    response_description="Dry-run preview of return records eligible for reconciliation import",
)
def preview_gst_import(
    payload: GstImportRequest,
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Dry-run import preview.
    Fetches records on the server, validates them, and checks for existing duplicates
    in the database for the active business.

    **SAFETY**: This endpoint does NOT modify the database.
    """
    period = _require_valid_period(payload.tax_period)
    canonical_source, raw_records = _fetch_server_return_records(
        payload.return_type, period, payload.counterparty_gstin, business
    )

    ready_records: List[Dict[str, Any]] = []
    duplicate_records: List[Dict[str, Any]] = []
    invalid_records: List[Dict[str, Any]] = []
    invalid_errors: List[str] = []
    seen_in_batch: set = set()

    for idx, r in enumerate(raw_records):
        row_dict = dict(r)
        is_valid, errs = validate_invoice_row(row_dict, idx + 1)
        if not is_valid:
            invalid_records.append(row_dict)
            invalid_errors.extend(errs)
            continue

        inv_no = str(row_dict.get("invoice_no") or "").strip()
        inv_date = parse_date_safely(row_dict.get("invoice_date"))
        if not inv_no or not inv_date:
            invalid_records.append(row_dict)
            invalid_errors.append(f"Row {idx + 1}: Missing invoice_no or invalid invoice_date")
            continue

        # Check intra-batch duplicate
        batch_key = (inv_no, canonical_source)
        if batch_key in seen_in_batch:
            duplicate_records.append(row_dict)
            continue
        seen_in_batch.add(batch_key)

        # Check existing database record for active business
        existing = db.scalar(
            select(Invoice).where(
                Invoice.invoice_no == inv_no,
                Invoice.business_id == business.id,
                Invoice.source == canonical_source,
                Invoice.deleted_at.is_(None),
            ).with_for_update()
        )
        if existing is not None:
            duplicate_records.append(row_dict)
        else:
            ready_records.append(row_dict)

    preview_sample = [
        {
            "invoice_no": r.get("invoice_no"),
            "invoice_date": str(r.get("invoice_date")),
            "gstin": r.get("gstin"),
            "taxable_value": r.get("taxable_value"),
            "gst_amount": r.get("gst_amount"),
            "status": "duplicate" if r in duplicate_records else "ready",
        }
        for r in raw_records[:30]
    ]

    return {
        "return_type": canonical_source.upper(),
        "source": canonical_source,
        "tax_period": period,
        "target_business_id": business.id,
        "target_business_name": business.name,
        "target_business_gstin": business.gstin,
        "total_records": len(raw_records),
        "ready_to_import": len(ready_records),
        "duplicate_count": len(duplicate_records),
        "rejected_count": len(invalid_records),
        "preview_records": preview_sample,
        "duplicates_sample": [d.get("invoice_no") for d in duplicate_records[:10]],
        "invalid_errors": invalid_errors[:20],
        "is_mock_data": True,
        "data_source": "synthetic_csv",
        "note": (
            "Dry-run preview completed. No database changes were made. "
            "Confirm to commit these records into your business reconciliation ledger."
        ),
    }


# ─────────────────────────────────────────────────────────────
# /gst/import
# ─────────────────────────────────────────────────────────────

@router.post(
    "/import",
    summary="Execute GST Return Import",
    response_description="Imports validated synthetic return records into the business invoice ledger",
)
def execute_gst_import(
    payload: GstImportRequest,
    business: Business = Depends(get_current_business),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Executes confirmed import of return records into the reconciliation ledger.

    **SAFETY & CONCURRENCY GUARANTEES**:
    - Re-fetches all records fresh on the server from MockGstAdapter.
    - Never trusts invoice records passed from the browser.
    - Re-validates every record and parses dates/amounts safely.
    - Idempotently skips duplicates via (invoice_no, business_id, source) check.
    - Runs inside an atomic database transaction. Any failure rolls back completely.
    - Assigns business_id strictly from current_business.id (zero cross-tenant leakage).

    A partial unique index on active invoice rows enforces the same business/source/
    invoice-number key in the database, so concurrent imports cannot create duplicates.
    """
    period = _require_valid_period(payload.tax_period)
    if business.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Business access is not authorized.")
    canonical_source, raw_records = _fetch_server_return_records(
        payload.return_type, period, payload.counterparty_gstin, business
    )

    if not raw_records:
        return {
            "status": "no_data",
            "return_type": canonical_source.upper(),
            "source": canonical_source,
            "tax_period": period,
            "business_id": business.id,
            "total_records": 0,
            "imported_count": 0,
            "duplicate_count": 0,
            "rejected_count": 0,
            "message": "No eligible fixture records were found for this return and period. Nothing was saved.",
            "is_mock_data": True,
            "data_source": "synthetic_csv",
        }

    imported_count = 0
    duplicate_count = 0
    rejected_count = 0
    seen_in_batch: dict[tuple[str, str], Invoice] = {}

    try:
        batch = create_import_batch(
            db,
            business_id=business.id,
            imported_by_user_id=current_user.id,
            source_category="gst_simulator",
            source_type=canonical_source,
            fixture_identifier=f"{canonical_source}.csv",
            tax_period=period,
            total_rows=len(raw_records),
        )

        for idx, r in enumerate(raw_records):
            row_dict = dict(r)
            is_valid, validation_errors = validate_invoice_row(row_dict, idx + 1)
            if not is_valid:
                rejected_count += 1
                add_invoice_batch_item(
                    db,
                    batch_id=batch.batch_id,
                    outcome="rejected",
                    rejection_reason="; ".join(validation_errors) or "Row failed invoice validation.",
                )
                continue

            inv_no = str(row_dict.get("invoice_no") or "").strip()
            inv_date = parse_date_safely(row_dict.get("invoice_date"))
            if not inv_no or not inv_date:
                rejected_count += 1
                add_invoice_batch_item(
                    db,
                    batch_id=batch.batch_id,
                    outcome="rejected",
                    rejection_reason=f"Row {idx + 1}: Missing invoice number or invalid invoice date.",
                )
                continue

            try:
                taxable_val = float(row_dict["taxable_value"])
                gst_amt = float(row_dict["gst_amount"])
            except (ValueError, KeyError, TypeError):
                rejected_count += 1
                add_invoice_batch_item(
                    db,
                    batch_id=batch.batch_id,
                    outcome="rejected",
                    rejection_reason=f"Row {idx + 1}: Invalid taxable value or GST amount.",
                )
                continue

            gstin = str(row_dict.get("gstin") or "").strip().upper()

            # Intra-batch duplicate check
            batch_key = (inv_no, canonical_source)
            earlier_record = seen_in_batch.get(batch_key)
            if earlier_record is not None:
                duplicate_count += 1
                add_invoice_batch_item(
                    db,
                    batch_id=batch.batch_id,
                    outcome="duplicate",
                    invoice_id=earlier_record.id,
                )
                continue

            # Database duplicate check for active business
            existing = db.scalar(
                select(Invoice).where(
                    Invoice.invoice_no == inv_no,
                    Invoice.business_id == business.id,
                    Invoice.source == canonical_source,
                    Invoice.deleted_at.is_(None),
                )
            )
            if existing is not None:
                duplicate_count += 1
                seen_in_batch[batch_key] = existing
                add_invoice_batch_item(
                    db, batch_id=batch.batch_id, outcome="duplicate", invoice_id=existing.id
                )
                continue

            invoice = Invoice(
                invoice_no=inv_no,
                invoice_date=inv_date,
                gstin=gstin,
                taxable_value=taxable_val,
                gst_amount=gst_amt,
                source=canonical_source,
                business_id=business.id,
                import_batch_id=batch.batch_id,
            )
            db.add(invoice)
            db.flush()
            seen_in_batch[batch_key] = invoice
            imported_count += 1
            add_invoice_batch_item(
                db, batch_id=batch.batch_id, outcome="imported", invoice_id=invoice.id
            )

        complete_import_batch(
            batch,
            imported_rows=imported_count,
            duplicate_rows=duplicate_count,
            rejected_rows=rejected_count,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if is_unique_constraint_violation(exc):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A conflicting invoice was concurrently imported. Please refresh and retry.",
            ) from None
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database transaction failed during GST return import. The batch and invoice changes were rolled back.",
        ) from None
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Database transaction failed during GST return import. "
                "The batch and invoice changes were rolled back."
            ),
        )

    if imported_count == 0 and duplicate_count == 0 and rejected_count > 0:
        result_status = "failed"
        result_message = (
            f"No {canonical_source.upper()} records were imported for period {period}; "
            f"all {rejected_count} record(s) were rejected. Rejection details are recorded in the import batch."
        )
    elif rejected_count:
        result_status = "partial"
        result_message = (
            f"Imported {imported_count} {canonical_source.upper()} record(s) for period {period}; "
            f"skipped {duplicate_count} duplicate(s) and rejected {rejected_count} record(s)."
        )
    else:
        result_status = "success"
        result_message = (
            f"Imported {imported_count} {canonical_source.upper()} record(s) for period {period}; "
            f"skipped {duplicate_count} duplicate(s)."
        )

    return {
        "status": result_status,
        "return_type": canonical_source.upper(),
        "source": canonical_source,
        "tax_period": period,
        "import_batch_id": str(batch.batch_id),
        "business_id": business.id,
        "business_name": business.name,
        "total_records": len(raw_records),
        "imported_count": imported_count,
        "duplicate_count": duplicate_count,
        "rejected_count": rejected_count,
        "message": result_message,
        "is_mock_data": True,
        "data_source": "synthetic_csv",
    }
