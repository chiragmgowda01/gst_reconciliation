import re
from datetime import date as dt_date, datetime
from typing import Any, Dict, List, Optional, Tuple, Set
import pandas as pd


# Standard Indian GSTIN pattern: 2 digits state code + 10 chars PAN + 1 entity num + 1 'Z' + 1 check digit
GSTIN_REGEX = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$")


def clean_header_name(header: Any) -> str:
    """
    Clean header string by removing UTF-8 BOM, stripping leading/trailing whitespace,
    converting to lowercase, and standardizing delimiters (spaces, hyphens, dots) to underscores.
    """
    if header is None:
        return ""
    s = str(header).replace("\ufeff", "").strip().lower()
    s = re.sub(r"[\s\-\.]+", "_", s)
    s = re.sub(r"[^\w]", "", s)
    return s.strip("_")


# Exclusions: Business's own GSTIN headers must NEVER be mistaken for counterparty GSTIN
OWN_GSTIN_HEADERS: Set[str] = {
    "my_gstin", "own_gstin", "business_gstin", "company_gstin",
    "user_gstin", "our_gstin", "self_gstin", "org_gstin", "organization_gstin"
}

# Aliases for canonical invoice columns (all formatted in clean snake_case)
INVOICE_COLUMN_ALIASES: Dict[str, List[str]] = {
    "invoice_no": [
        "invoice_no", "invoice_number", "invoice", "document_number", "document_no",
        "doc_number", "doc_no", "inv_no", "inv_number", "bill_no", "bill_number",
        "invoiceno", "invoicenumber", "docno", "invno", "billno"
    ],
    "gstin": [
        # Counterparty GSTIN (prioritized by source type in normalize function)
        "counterparty_gstin", "counterpartygstin", "customer_gstin", "supplier_gstin",
        "vendor_gstin", "recipient_gstin", "party_gstin", "buyer_gstin", "gstin", "ctin"
    ],
    "invoice_date": [
        "invoice_date", "date", "inv_date", "bill_date", "doc_date", "document_date",
        "invoicedate", "invdate", "billdate", "docdate"
    ],
    "taxable_value": [
        "taxable_value", "taxable_amount", "taxable_val", "taxable_amt", "taxable",
        "tax_val", "taxablevalue", "taxableamount"
    ],
    "gst_amount": [
        "gst_amount", "tax_amount", "total_gst", "total_tax", "gst", "tax",
        "gst_amt", "tax_amt", "gstamount", "taxamount", "totaltax", "totalgst"
    ],
}

# Aliases for GSTR-3B summary-level columns
GSTR3B_COLUMN_ALIASES: Dict[str, List[str]] = {
    "tax_period": ["tax_period", "taxperiod", "period", "return_period", "month"],
    "output_tax": ["output_tax", "outputtax", "tax_payable", "liability", "outward_tax", "total_output_tax", "output_tax_amount"],
    "eligible_itc": ["eligible_itc", "eligibleitc", "itc_available", "itc_eligible", "total_itc", "itc"],
    "itc_reversed": ["itc_reversed", "itcreversed", "reversed_itc", "reversal", "itc_reversal"],
    "net_itc": ["net_itc", "netitc", "itc_net", "net_eligible_itc"],
}


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
    if date_str is None or pd.isna(date_str) or str(date_str).strip() == "" or str(date_str).lower() == "nan":
        return False, "Invoice date is missing"

    if isinstance(date_str, (dt_date, datetime)):
        return True, None

    date_str_clean = str(date_str).strip()
    for fmt in (
        "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d",
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
        "%d-%m-%Y %H:%M:%S", "%d/%m/%Y %H:%M:%S"
    ):
        try:
            datetime.strptime(date_str_clean, fmt)
            return True, None
        except ValueError:
            continue
    return False, f"Invalid date format '{date_str}', expected YYYY-MM-DD"


def parse_date_safely(date_val: Any) -> Optional[dt_date]:
    """Parse date value into a standard Python date object."""
    if date_val is None or pd.isna(date_val):
        return None
    if isinstance(date_val, datetime):
        return date_val.date()
    if isinstance(date_val, dt_date):
        return date_val

    clean_str = str(date_val).strip()
    for fmt in (
        "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d",
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
        "%d-%m-%Y %H:%M:%S", "%d/%m/%Y %H:%M:%S"
    ):
        try:
            return datetime.strptime(clean_str, fmt).date()
        except ValueError:
            continue
    return None


def validate_numeric(value: Any, field_name: str) -> Tuple[bool, Optional[str]]:
    """Validate that value is a valid non-negative float."""
    if value is None or pd.isna(value) or str(value).strip() == "" or str(value).lower() == "nan":
        return False, f"Missing numeric value for {field_name}"
    try:
        val = float(value)
        if val < 0:
            return False, f"{field_name} cannot be negative ({val})"
        return True, None
    except (ValueError, TypeError):
        return False, f"Invalid numeric value '{value}' for {field_name}"


def validate_invoice_row(row: Dict[str, Any], row_idx: int) -> Tuple[bool, List[str]]:
    """
    Validate a single CSV invoice record.
    Supports canonical columns and recognizes alias fallbacks to prevent false errors.
    Returns: (is_valid, list_of_errors)
    """
    errors: List[str] = []
    # Normalize row keys to allow alias lookups even if invoked with uncleaned headers
    clean_row = {clean_header_name(k): v for k, v in row.items()}

    # 1. Invoice Number (support canonical or direct aliases)
    invoice_no = ""
    for k in (
        "invoice_no", "invoice_number", "invoice", "document_number",
        "document_no", "doc_number", "doc_no", "inv_no", "inv_number",
        "bill_no", "bill_number", "invoiceno", "invoicenumber"
    ):
        if k in clean_row and clean_row[k] is not None and not pd.isna(clean_row[k]):
            val = str(clean_row[k]).strip()
            if val and val.lower() != "nan":
                invoice_no = val
                break

    if not invoice_no:
        errors.append(f"Row {row_idx}: Missing invoice number")

    # 2. Date
    date_val = None
    for k in (
        "invoice_date", "date", "inv_date", "bill_date",
        "doc_date", "document_date", "invoicedate"
    ):
        if k in clean_row and clean_row[k] is not None and not pd.isna(clean_row[k]):
            date_val = clean_row[k]
            break

    is_date_ok, date_err = validate_date(date_val)
    if not is_date_ok:
        errors.append(f"Row {row_idx}: {date_err}")

    # 3. Counterparty GSTIN (support canonical or direct aliases, ignore business own GSTIN)
    gstin = None
    for k in (
        "gstin", "counterparty_gstin", "customer_gstin", "supplier_gstin",
        "vendor_gstin", "recipient_gstin", "party_gstin", "buyer_gstin", "ctin"
    ):
        if k in clean_row and clean_row[k] is not None and not pd.isna(clean_row[k]):
            val = str(clean_row[k]).strip()
            if val and val.lower() != "nan":
                gstin = val
                break

    is_gstin_ok, gstin_err = validate_gstin(gstin)
    if not is_gstin_ok:
        errors.append(f"Row {row_idx}: {gstin_err}")

    # 4. Taxable value
    tv_val = None
    for k in (
        "taxable_value", "taxable_amount", "taxable_val",
        "taxable_amt", "taxable", "tax_val", "taxablevalue"
    ):
        if k in clean_row and clean_row[k] is not None and not pd.isna(clean_row[k]):
            tv_val = clean_row[k]
            break

    is_tv_ok, tv_err = validate_numeric(tv_val, "taxable_value")
    if not is_tv_ok:
        errors.append(f"Row {row_idx}: {tv_err}")

    # 5. GST amount
    gst_val = None
    for k in (
        "gst_amount", "tax_amount", "total_gst", "total_tax",
        "gst", "tax", "gst_amt", "tax_amt", "gstamount", "totalgst"
    ):
        if k in clean_row and clean_row[k] is not None and not pd.isna(clean_row[k]):
            gst_val = clean_row[k]
            break

    is_gst_ok, gst_err = validate_numeric(gst_val, "gst_amount")
    if not is_gst_ok:
        errors.append(f"Row {row_idx}: {gst_err}")

    return len(errors) == 0, errors


def normalize_invoice_dataframe(df: pd.DataFrame, source_type: str) -> Tuple[pd.DataFrame, List[str]]:
    """
    Inspect raw CSV DataFrame columns, clean headers (removing UTF-8 BOM, extra spaces,
    and case differences), map safe aliases to canonical names, and verify required fields exist.
    Also detects accidental GSTR-3B summary file uploads and provides friendly guidance.
    Returns: (normalized_df, missing_columns_error_messages)
    """
    if df.empty:
        return df, []

    # Map cleaned header name -> original raw header name
    cleaned_col_map: Dict[str, str] = {}
    for raw_col in df.columns:
        cleaned = clean_header_name(raw_col)
        # Avoid overriding if duplicate
        if cleaned not in cleaned_col_map:
            cleaned_col_map[cleaned] = raw_col

    # Cross-source check: Check if user uploaded a GSTR-3B summary CSV under an invoice register
    if "tax_period" in cleaned_col_map and ("output_tax" in cleaned_col_map or "eligible_itc" in cleaned_col_map):
        return df, [
            "The uploaded CSV appears to be a GSTR-3B monthly summary return (found headers: tax_period, output_tax). "
            "Please select 'Form GSTR-3B' as the target register type instead of invoice registers."
        ]

    normalized_df = pd.DataFrame(index=df.index)
    missing_errors: List[str] = []

    for canonical, aliases in INVOICE_COLUMN_ALIASES.items():
        matched_raw = None

        if canonical == "gstin":
            # Determine source-specific prioritization for counterparty GSTIN
            if source_type in {"sales_register", "gstr1"}:
                prioritized = [
                    "customer_gstin", "recipient_gstin", "buyer_gstin",
                    "counterparty_gstin", "gstin", "party_gstin", "ctin",
                    "supplier_gstin", "vendor_gstin"
                ]
            else:
                prioritized = [
                    "supplier_gstin", "vendor_gstin", "counterparty_gstin",
                    "gstin", "party_gstin", "ctin", "customer_gstin", "recipient_gstin"
                ]

            for pref in prioritized:
                if pref in cleaned_col_map and pref not in OWN_GSTIN_HEADERS:
                    matched_raw = cleaned_col_map[pref]
                    break

        if not matched_raw:
            for alias in aliases:
                if alias in cleaned_col_map:
                    # Guard against matching business's own GSTIN
                    if canonical == "gstin" and alias in OWN_GSTIN_HEADERS:
                        continue
                    matched_raw = cleaned_col_map[alias]
                    break

        if matched_raw:
            normalized_df[canonical] = df[matched_raw]
        else:
            missing_errors.append(
                f"Missing required column '{canonical}'. Accepted headers: "
                f"{', '.join(aliases[:5])}. Present in CSV: {list(df.columns)}"
            )

    return normalized_df, missing_errors


def validate_gstr3b_row(row: Dict[str, Any], row_idx: int) -> Tuple[bool, List[str]]:
    """Validate a single GSTR-3B monthly summary record."""
    errors: List[str] = []

    period_raw = str(row.get("tax_period") or "").strip()
    if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", period_raw):
        errors.append(f"Row {row_idx}: Invalid tax_period '{period_raw}', expected YYYY-MM (e.g. 2026-07)")

    for field in ("output_tax", "eligible_itc"):
        is_num, num_err = validate_numeric(row.get(field), field)
        if not is_num:
            errors.append(f"Row {row_idx}: {num_err}")

    if "itc_reversed" in row and row.get("itc_reversed") is not None and str(row.get("itc_reversed")).strip() != "":
        is_num, num_err = validate_numeric(row.get("itc_reversed"), "itc_reversed")
        if not is_num:
            errors.append(f"Row {row_idx}: {num_err}")

    return len(errors) == 0, errors


def normalize_gstr3b_dataframe(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
    """
    Inspect raw GSTR-3B summary CSV columns and map safe aliases.
    Also detects accidental invoice register uploads to GSTR-3B.
    Returns: (normalized_df, missing_columns_error_messages)
    """
    if df.empty:
        return df, []

    cleaned_col_map: Dict[str, str] = {}
    for raw_col in df.columns:
        cleaned = clean_header_name(raw_col)
        if cleaned not in cleaned_col_map:
            cleaned_col_map[cleaned] = raw_col

    # Cross-source check: Check if user uploaded an invoice register under GSTR-3B
    if any(h in cleaned_col_map for h in ("invoice_no", "invoice_number", "invoice", "document_number")):
        return df, [
            "The uploaded CSV appears to be an invoice-level register (found header: invoice_no/invoice_number). "
            "Form GSTR-3B only accepts monthly summary returns (tax_period, output_tax, eligible_itc). "
            "Please select Sales Register, GSTR-1, or Purchase Register."
        ]

    normalized_df = pd.DataFrame(index=df.index)
    missing_errors: List[str] = []

    for canonical in ["tax_period", "output_tax", "eligible_itc"]:
        aliases = GSTR3B_COLUMN_ALIASES[canonical]
        matched_raw = None
        for alias in aliases:
            if alias in cleaned_col_map:
                matched_raw = cleaned_col_map[alias]
                break
        if matched_raw:
            normalized_df[canonical] = df[matched_raw]
        else:
            missing_errors.append(
                f"Missing required GSTR-3B summary column '{canonical}'. Accepted headers: {', '.join(aliases[:4])}."
            )

    # Optional columns with defaults
    for canonical in ["itc_reversed", "net_itc"]:
        aliases = GSTR3B_COLUMN_ALIASES[canonical]
        matched_raw = None
        for alias in aliases:
            if alias in cleaned_col_map:
                matched_raw = cleaned_col_map[alias]
                break
        if matched_raw:
            normalized_df[canonical] = df[matched_raw]
        elif canonical == "itc_reversed":
            normalized_df["itc_reversed"] = 0.0

    if "net_itc" not in normalized_df.columns and "eligible_itc" in normalized_df.columns:
        try:
            el = pd.to_numeric(normalized_df["eligible_itc"], errors="coerce").fillna(0.0)
            rev = pd.to_numeric(normalized_df.get("itc_reversed", 0.0), errors="coerce").fillna(0.0)
            normalized_df["net_itc"] = el - rev
        except Exception:
            normalized_df["net_itc"] = 0.0

    return normalized_df, missing_errors

