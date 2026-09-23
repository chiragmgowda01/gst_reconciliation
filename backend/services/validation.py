import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


# Standard Indian GSTIN pattern: 2 digits state code + 10 chars PAN + 1 entity num + 1 'Z' + 1 check digit
GSTIN_REGEX = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$")


def validate_gstin(gstin: Optional[str]) -> Tuple[bool, Optional[str]]:
    """Validate that GSTIN is a non-empty 15-character string matching Indian GSTIN standard format."""
    if not gstin or not isinstance(gstin, str):
        return False, "GSTIN is missing or empty"
    cleaned = gstin.strip().upper()
    if len(cleaned) != 15:
        return False, f"Invalid GSTIN length ({len(cleaned)} chars, expected 15)"
    if not GSTIN_REGEX.match(cleaned):
        return False, f"Invalid GSTIN structure '{cleaned}'"
    return True, None


def validate_date(date_str: Any) -> Tuple[bool, Optional[str]]:
    """Validate date format is YYYY-MM-DD or standard parseable ISO date."""
    if not date_str:
        return False, "Invoice date is missing"
    date_str_clean = str(date_str).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            datetime.strptime(date_str_clean, fmt)
            return True, None
        except ValueError:
            continue
    return False, f"Invalid date format '{date_str}', expected YYYY-MM-DD"


def validate_numeric(value: Any, field_name: str) -> Tuple[bool, Optional[str]]:
    """Validate that value is a valid non-negative float."""
    if value is None or str(value).strip() == "":
        return False, f"Missing numeric value for {field_name}"
    try:
        val = float(value)
        if val < 0:
            return False, f"{field_name} cannot be negative ({val})"
        return True, None
    except (ValueError, TypeError):
        return False, f"Invalid numeric value '{value}' for {field_name}"


def validate_invoice_row(row: Dict[str, Any], row_idx: int) -> Tuple[bool, List[str]]:
    """Validate a single CSV invoice record. Returns (is_valid, list_of_errors)."""
    errors: List[str] = []

    # 1. Invoice Number
    invoice_no = str(row.get("invoice_no") or "").strip()
    if not invoice_no or invoice_no.lower() == "nan":
        errors.append(f"Row {row_idx}: Missing invoice number")

    # 2. Date
    is_date_ok, date_err = validate_date(row.get("invoice_date"))
    if not is_date_ok:
        errors.append(f"Row {row_idx}: {date_err}")

    # 3. GSTIN (customer_gstin or supplier_gstin or gstin)
    gstin = row.get("customer_gstin") or row.get("supplier_gstin") or row.get("gstin")
    is_gstin_ok, gstin_err = validate_gstin(gstin)
    if not is_gstin_ok:
        errors.append(f"Row {row_idx}: {gstin_err}")

    # 4. Taxable value
    is_tv_ok, tv_err = validate_numeric(row.get("taxable_value"), "taxable_value")
    if not is_tv_ok:
        errors.append(f"Row {row_idx}: {tv_err}")

    # 5. GST amount
    is_gst_ok, gst_err = validate_numeric(row.get("gst_amount"), "gst_amount")
    if not is_gst_ok:
        errors.append(f"Row {row_idx}: {gst_err}")

    return len(errors) == 0, errors
