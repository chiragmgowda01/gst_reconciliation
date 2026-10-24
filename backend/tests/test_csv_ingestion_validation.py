import io
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, delete

from main import app
from database import SessionLocal
from models.models import Business, Invoice, User
from services.auth import create_access_token, hash_password
from services.validation import (
    clean_header_name,
    normalize_gstr3b_dataframe,
    normalize_invoice_dataframe,
    validate_invoice_row,
    validate_gstr3b_row,
)
import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_context():
    """Ensure a dedicated test user and business exist for CSV ingestion tests."""
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.email == "ingest_test@gst.local"))
        if not user:
            user = User(
                name="Ingest Test User",
                email="ingest_test@gst.local",
                password=hash_password("Pass123!"),
            )
            db.add(user)
            db.flush()

        biz = db.scalar(select(Business).where(Business.gstin == "29INGST1234F1Z5"))
        if not biz:
            biz = Business(
                name="Ingestion Test Business",
                gstin="29INGST1234F1Z5",
                user_id=user.id,
            )
            db.add(biz)
            db.flush()

        # Clean existing invoices for this business
        db.execute(delete(Invoice).where(Invoice.business_id == biz.id))
        db.commit()

        token = create_access_token(user.id, user.email)
        headers = {"Authorization": f"Bearer {token}", "X-Business-ID": str(biz.id)}

        return {
            "user": user,
            "biz": biz,
            "headers": headers,
        }
    finally:
        db.close()


# ─── 1. Header Cleaning and Alias Tests ──────────────────────────────────────────

def test_clean_header_name_bom_spaces_case():
    assert clean_header_name("\ufeffInvoice_Number") == "invoice_number"
    assert clean_header_name("  Invoice Number  ") == "invoice_number"
    assert clean_header_name("\ufeff  COUNTERPARTY GSTIN  ") == "counterparty_gstin"
    assert clean_header_name("Taxable-Value") == "taxable_value"
    assert clean_header_name("tax.amount") == "tax_amount"
    assert clean_header_name("TOTAL GST") == "total_gst"
    assert clean_header_name(None) == ""


def test_normalize_invoice_dataframe_with_v2_aliases():
    raw_csv = """\ufeffInvoice Number,Counterparty GSTIN,Invoice Date,Taxable Amount,Tax Amount
INV-001,29ABCDE1234F1Z5,2026-07-01,10000,1800
INV-002,29BCDEF2345G1Z6,2026-07-02,20000,3600
"""
    df = pd.read_csv(io.StringIO(raw_csv))
    norm_df, missing = normalize_invoice_dataframe(df, "sales_register")
    assert len(missing) == 0
    assert list(norm_df.columns) == ["invoice_no", "gstin", "invoice_date", "taxable_value", "gst_amount"]
    assert norm_df.iloc[0]["invoice_no"] == "INV-001"
    assert norm_df.iloc[0]["gstin"] == "29ABCDE1234F1Z5"


def test_normalize_invoice_dataframe_excludes_own_gstin():
    # CSV has both company_gstin (own) and customer_gstin (counterparty)
    raw_csv = """company_gstin,customer_gstin,invoice_number,date,taxable_value,gst_amount
29INGST1234F1Z5,29ABCDE1234F1Z5,INV-100,2026-07-01,5000,900
"""
    df = pd.read_csv(io.StringIO(raw_csv))
    norm_df, missing = normalize_invoice_dataframe(df, "sales_register")
    assert len(missing) == 0
    assert norm_df.iloc[0]["gstin"] == "29ABCDE1234F1Z5"


def test_normalize_invoice_dataframe_fails_if_only_own_gstin_present():
    raw_csv = """company_gstin,invoice_number,date,taxable_value,gst_amount
29INGST1234F1Z5,INV-100,2026-07-01,5000,900
"""
    df = pd.read_csv(io.StringIO(raw_csv))
    _, missing = normalize_invoice_dataframe(df, "sales_register")
    assert any("gstin" in err.lower() for err in missing)


# ─── 2. Accurate Counts: Row Rejections vs Validation Findings ──────────────────

def test_upload_accurate_rejected_row_and_findings_count(client, auth_context):
    # 8 rows, all 8 missing both invoice_no and counterparty_gstin
    # Total evaluated = 8, Imported = 0, Duplicates = 0, Rejected = 8, Validation findings = 16
    lines = ["invoice_no,gstin,invoice_date,taxable_value,gst_amount"]
    for i in range(8):
        lines.append(",,2026-07-01,1000,180")
    csv_content = "\n".join(lines).encode("utf-8")

    files = {"file": ("test_empty_fields.csv", csv_content, "text/csv")}
    data = {"source_type": "sales_register"}
    response = client.post("/invoices/upload", files=files, data=data, headers=auth_context["headers"])

    assert response.status_code == 200
    res = response.json()
    assert res["total_records"] == 8
    assert res["imported"] == 0
    assert res["duplicates"] == 0
    assert res["rejected"] == 8
    assert res["invalid_records"] == 8
    assert res["validation_findings"] == 16
    assert len(res["errors"]) == 16


def test_upload_utf8_bom_and_aliases_full_success(client, auth_context):
    # UTF-8 BOM encoded CSV with alias headers and spaces
    csv_text = "\ufeffinvoice_number, counterparty_gstin , invoice date , taxable value , total gst\n"
    csv_text += "INV-BOM-001,29ABCDE1234F1Z5,2026-07-05,50000,9000\n"
    csv_text += "INV-BOM-002,29BCDEF2345G1Z6,2026-07-06,25000,4500\n"

    # Encode with UTF-8 BOM bytes (\xef\xbb\xbf)
    bom_bytes = csv_text.encode("utf-8-sig")

    files = {"file": ("sales_bom.csv", bom_bytes, "text/csv")}
    data = {"source_type": "sales_register"}
    response = client.post("/invoices/upload", files=files, data=data, headers=auth_context["headers"])

    assert response.status_code == 200
    res = response.json()
    assert res["total_records"] == 2
    assert res["imported"] == 2
    assert res["duplicates"] == 0
    assert res["rejected"] == 0
    assert res["validation_findings"] == 0

    # Verify records in database
    db = SessionLocal()
    try:
        invoices = db.scalars(
            select(Invoice).where(
                Invoice.business_id == auth_context["biz"].id,
                Invoice.source == "sales_register",
            )
        ).all()
        assert len(invoices) == 2
        inv_map = {inv.invoice_no: inv for inv in invoices}
        assert "INV-BOM-001" in inv_map
        assert inv_map["INV-BOM-001"].gstin == "29ABCDE1234F1Z5"
        assert inv_map["INV-BOM-001"].taxable_value == 50000.0
        assert inv_map["INV-BOM-001"].gst_amount == 9000.0
    finally:
        db.close()


# ─── 3. Repeat Upload / Duplicate Handling ──────────────────────────────────────

def test_upload_duplicate_detection(client, auth_context):
    csv_text = "invoice_no,customer_gstin,invoice_date,taxable_value,gst_amount\n"
    csv_text += "INV-DUP-1,29ABCDE1234F1Z5,2026-07-01,10000,1800\n"
    csv_bytes = csv_text.encode("utf-8")

    # First upload
    res1 = client.post(
        "/invoices/upload",
        files={"file": ("test.csv", csv_bytes, "text/csv")},
        data={"source_type": "sales_register"},
        headers=auth_context["headers"],
    ).json()
    assert res1["imported"] == 1
    assert res1["duplicates"] == 0

    # Second upload of identical file
    res2 = client.post(
        "/invoices/upload",
        files={"file": ("test.csv", csv_bytes, "text/csv")},
        data={"source_type": "sales_register"},
        headers=auth_context["headers"],
    ).json()
    assert res2["total_records"] == 1
    assert res2["imported"] == 0
    assert res2["duplicates"] == 1
    assert res2["rejected"] == 0

    # Intra-batch duplicate check
    batch_dup_csv = (
        "invoice_no,customer_gstin,invoice_date,taxable_value,gst_amount\n"
        "INV-BATCH-1,29ABCDE1234F1Z5,2026-07-01,10000,1800\n"
        "INV-BATCH-1,29ABCDE1234F1Z5,2026-07-01,10000,1800\n"
    ).encode("utf-8")
    res3 = client.post(
        "/invoices/upload",
        files={"file": ("batch.csv", batch_dup_csv, "text/csv")},
        data={"source_type": "gstr1"},
        headers=auth_context["headers"],
    ).json()
    assert res3["total_records"] == 2
    assert res3["imported"] == 1
    assert res3["duplicates"] == 1


# ─── 4. Synthetic Pack Upload Tests ─────────────────────────────────────────────

@pytest.mark.parametrize("file_name,source_type", [
    ("sales_register.csv", "sales_register"),
    ("gstr1.csv", "gstr1"),
    ("purchase_register.csv", "purchase_register"),
    ("gstr2a.csv", "gstr2a"),
    ("gstr2b.csv", "gstr2b"),
])
def test_upload_synthetic_data_pack(client, auth_context, file_name, source_type):
    file_path = DATA_DIR / file_name
    assert file_path.exists(), f"Synthetic file {file_name} must exist"

    with open(file_path, "rb") as f:
        file_bytes = f.read()

    files = {"file": (file_name, file_bytes, "text/csv")}
    data = {"source_type": source_type}
    response = client.post(
        "/invoices/upload",
        files=files,
        data=data,
        headers=auth_context["headers"],
    )

    assert response.status_code == 200
    res = response.json()
    assert res["total_records"] > 0
    # At least some rows should be imported
    assert res["imported"] > 0 or res["duplicates"] > 0


# ─── 5. GSTR-3B Summary Schema Isolation ────────────────────────────────────────

def test_gstr3b_summary_upload_success(client, auth_context):
    # Test upload of a unique GSTR-3B tax period
    import uuid
    # Use unique values to ensure update or import
    test_out_tax = 135000.0 + (hash(str(uuid.uuid4())) % 1000)
    csv_text = f"tax_period,output_tax,eligible_itc,itc_reversed,net_itc\n2026-09,{test_out_tax},45000,2000,43000\n"
    files = {"file": ("gstr3b_sep.csv", csv_text.encode("utf-8"), "text/csv")}
    data = {"source_type": "gstr3b"}

    response = client.post(
        "/invoices/upload",
        files=files,
        data=data,
        headers=auth_context["headers"],
    )
    assert response.status_code == 200
    res = response.json()
    assert res["source_type"] == "gstr3b"
    assert res["total_records"] == 1
    assert res["imported"] == 1
    assert res["rejected"] == 0


def test_cross_source_protection_invoice_to_gstr3b(client, auth_context):
    # Uploading an invoice register under GSTR-3B must be rejected with helpful error
    csv_text = "invoice_no,invoice_date,customer_gstin,taxable_value,gst_amount\nINV-1,2026-07-01,29ABCDE1234F1Z5,100,18"
    files = {"file": ("invoices.csv", csv_text.encode("utf-8"), "text/csv")}
    data = {"source_type": "gstr3b"}

    response = client.post(
        "/invoices/upload",
        files=files,
        data=data,
        headers=auth_context["headers"],
    )
    assert response.status_code == 400
    assert "invoice-level register" in response.json()["detail"].lower()


def test_cross_source_protection_gstr3b_to_sales_register(client, auth_context):
    # Uploading GSTR-3B summary under Sales Register must be rejected with helpful error
    csv_text = "tax_period,output_tax,eligible_itc\n2026-07,100000,30000"
    files = {"file": ("summary.csv", csv_text.encode("utf-8"), "text/csv")}
    data = {"source_type": "sales_register"}

    response = client.post(
        "/invoices/upload",
        files=files,
        data=data,
        headers=auth_context["headers"],
    )
    assert response.status_code == 400
    assert "gstr-3b monthly summary" in response.json()["detail"].lower()
