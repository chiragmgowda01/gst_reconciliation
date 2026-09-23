import pytest
from services.validation import (
    validate_date,
    validate_gstin,
    validate_invoice_row,
    validate_numeric,
)


def test_valid_gstin():
    valid_gstin = "29AAAAA1111A1Z5"
    ok, err = validate_gstin(valid_gstin)
    assert ok is True
    assert err is None


def test_invalid_gstin_length():
    short_gstin = "29AAAAA1111A1Z"
    ok, err = validate_gstin(short_gstin)
    assert ok is False
    assert "Invalid GSTIN length" in err


def test_invalid_gstin_empty():
    ok, err = validate_gstin("")
    assert ok is False
    assert "missing" in err.lower()


def test_validate_date():
    assert validate_date("2026-07-01")[0] is True
    assert validate_date("01-07-2026")[0] is True
    assert validate_date("invalid-date")[0] is False
    assert validate_date("")[0] is False


def test_validate_numeric():
    assert validate_numeric(100.50, "taxable_value")[0] is True
    assert validate_numeric("5000", "gst_amount")[0] is True
    assert validate_numeric(-10, "taxable_value")[0] is False
    assert validate_numeric("abc", "taxable_value")[0] is False
    assert validate_numeric("", "taxable_value")[0] is False


def test_validate_invoice_row_valid():
    row = {
        "invoice_no": "INV-2026-001",
        "invoice_date": "2026-07-01",
        "customer_gstin": "29AAAAA1111A1Z5",
        "taxable_value": 15000.0,
        "gst_amount": 2700.0,
    }
    is_valid, errors = validate_invoice_row(row, 1)
    assert is_valid is True
    assert len(errors) == 0


def test_validate_invoice_row_invalid():
    row = {
        "invoice_no": "",
        "invoice_date": "bad-date",
        "customer_gstin": "1234",
        "taxable_value": -50.0,
        "gst_amount": "not-a-number",
    }
    is_valid, errors = validate_invoice_row(row, 2)
    assert is_valid is False
    assert len(errors) >= 4
