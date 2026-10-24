import io
import pytest
from fastapi.testclient import TestClient
import pandas as pd
from sqlalchemy import select, func

from main import app
from database import SessionLocal
from models.models import Business, Invoice, User
from services.auth import create_access_token, hash_password


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_context():
    """Ensure two users and two businesses exist for strict tenant isolation testing."""
    db = SessionLocal()
    try:
        # User 1 (Default MSME)
        user1 = db.scalar(select(User).where(User.email == "export_test_user1@gst.local"))
        if not user1:
            user1 = User(
                name="Export Test User 1",
                email="export_test_user1@gst.local",
                password=hash_password("Pass123!"),
            )
            db.add(user1)
            db.flush()

        biz1 = db.scalar(select(Business).where(Business.gstin == "29EXPT1111A1Z5"))
        if not biz1:
            biz1 = Business(
                name="Export Biz 1",
                gstin="29EXPT1111A1Z5",
                user_id=user1.id,
            )
            db.add(biz1)
            db.flush()

        # User 2 (Isolated Tenant)
        user2 = db.scalar(select(User).where(User.email == "export_test_user2@gst.local"))
        if not user2:
            user2 = User(
                name="Export Test User 2",
                email="export_test_user2@gst.local",
                password=hash_password("Pass123!"),
            )
            db.add(user2)
            db.flush()

        biz2 = db.scalar(select(Business).where(Business.gstin == "29EXPT2222A1Z6"))
        if not biz2:
            biz2 = Business(
                name="Export Biz 2",
                gstin="29EXPT2222A1Z6",
                user_id=user2.id,
            )
            db.add(biz2)
            db.flush()

        demo_user = db.scalar(select(User).where(User.email == "default@gst.local")) or db.scalar(select(User).where(User.id == 1))
        demo_biz = db.scalar(select(Business).where(Business.id == 1))
        demo_token = create_access_token(demo_user.id, demo_user.email) if demo_user else None
        demo_headers = {"Authorization": f"Bearer {demo_token}", "X-Business-ID": "1"} if demo_token else {}

        db.commit()

        token1 = create_access_token(user1.id, user1.email)
        token2 = create_access_token(user2.id, user2.email)

        return {
            "demo_user": demo_user,
            "demo_biz": demo_biz,
            "demo_headers": demo_headers,
            "user1": user1,
            "biz1": biz1,
            "token1": token1,
            "headers1": {"Authorization": f"Bearer {token1}", "X-Business-ID": str(biz1.id)},
            "user2": user2,
            "biz2": biz2,
            "token2": token2,
            "headers2": {"Authorization": f"Bearer {token2}", "X-Business-ID": str(biz2.id)},
        }
    finally:
        db.close()


def test_export_unauthenticated_returns_401(client):
    """Calling /reports/export without token must return 401 Unauthorized."""
    resp = client.get("/reports/export")
    assert resp.status_code == 401
    assert "Authentication required" in resp.text


def test_export_all_12_catalogue_reports(client, auth_context):
    """Test every single report catalogue ID returns 200, text/csv, and attachment disposition."""
    catalogue_reports = [
        "sales",
        "sales_matched",
        "sales_mismatches",
        "sales_missing",
        "sales_extra",
        "sales_tax_liability",
        "purchases",
        "purchase_matched",
        "purchase_mismatches",
        "purchase_missing",
        "purchase_extra",
        "itc_eligibility_variance",
    ]

    headers = auth_context["demo_headers"] or auth_context["headers1"]
    for rep in catalogue_reports:
        resp = client.get(f"/reports/export?report_type={rep}&purchase_source=gstr2a", headers=headers)
        assert resp.status_code == 200, f"Report {rep} failed with status {resp.status_code}: {resp.text}"
        assert "text/csv" in resp.headers.get("content-type", "")
        disposition = resp.headers.get("content-disposition", "")
        assert "attachment" in disposition
        assert ".csv" in disposition

        # Parse returned CSV content to verify structure
        df = pd.read_csv(io.StringIO(resp.text))
        # Ensure standard header columns exist
        assert "invoice_no" in df.columns or "gstin" in df.columns, f"Missing standard columns in {rep}"


def test_export_backward_compatible_reports(client, auth_context):
    """Verify mismatches, missing, anomalies reports export successfully."""
    headers = auth_context["demo_headers"] or auth_context["headers1"]
    for rep in ["mismatches", "missing", "anomalies"]:
        resp = client.get(f"/reports/export?report_type={rep}", headers=headers)
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
        assert "attachment" in resp.headers.get("content-disposition", "")


def test_export_purchase_source_selection(client, auth_context):
    """Verify switching purchase_source between gstr2a and gstr2b reflects in filename and output."""
    headers = auth_context["demo_headers"] or auth_context["headers1"]

    resp_2a = client.get("/reports/export?report_type=purchases&purchase_source=gstr2a", headers=headers)
    assert resp_2a.status_code == 200
    assert "gstr2a" in resp_2a.headers.get("content-disposition", "")

    resp_2b = client.get("/reports/export?report_type=purchases&purchase_source=gstr2b", headers=headers)
    assert resp_2b.status_code == 200
    assert "gstr2b" in resp_2b.headers.get("content-disposition", "")


def test_export_tax_period_scoping_and_filename(client, auth_context):
    """Verify tax_period filters records and appends period suffix to filename."""
    headers = auth_context["demo_headers"] or auth_context["headers1"]

    # July 2026 (has demo data)
    resp_jul = client.get("/reports/export?report_type=sales&tax_period=2026-07", headers=headers)
    assert resp_jul.status_code == 200
    assert "2026_07" in resp_jul.headers.get("content-disposition", "")
    df_jul = pd.read_csv(io.StringIO(resp_jul.text))
    # Should contain records for demo business
    assert len(df_jul) > 0

    # August 2026 (no records exist for this period)
    resp_aug = client.get("/reports/export?report_type=sales&tax_period=2026-08", headers=headers)
    assert resp_aug.status_code == 200
    assert "2026_08" in resp_aug.headers.get("content-disposition", "")
    df_aug = pd.read_csv(io.StringIO(resp_aug.text))
    assert len(df_aug) == 0  # Zero rows in August


def test_export_invalid_report_type_returns_400(client, auth_context):
    """Calling with unsupported report_type returns 400 Bad Request."""
    headers = auth_context["headers1"]
    resp = client.get("/reports/export?report_type=non_existent_report", headers=headers)
    assert resp.status_code == 400
    assert "Invalid report_type" in resp.json().get("detail", "")


def test_export_invalid_tax_period_returns_400(client, auth_context):
    """Calling with invalid tax_period format returns 400 Bad Request."""
    headers = auth_context["headers1"]
    resp = client.get("/reports/export?report_type=sales&tax_period=2026-13", headers=headers)
    assert resp.status_code == 400
    assert "Invalid tax_period format" in resp.json().get("detail", "")


def test_tenant_isolation_forbidden_cross_access(client, auth_context):
    """User 2 cannot access Business 1's report data (403 Forbidden)."""
    headers = {
        "Authorization": f"Bearer {auth_context['token2']}",
        "X-Business-ID": str(auth_context["biz1"].id),
    }
    resp = client.get("/reports/export?report_type=sales", headers=headers)
    assert resp.status_code == 403
    assert "Forbidden" in resp.json().get("detail", "")


def test_tenant_isolation_empty_tenant_records(client, auth_context):
    """Tenant 2 with 0 DB records receives empty CSV headers and 0 data rows, never Tenant 1 records."""
    headers = auth_context["headers2"]
    resp = client.get("/reports/export?report_type=sales", headers=headers)
    assert resp.status_code == 200
    df = pd.read_csv(io.StringIO(resp.text))
    assert len(df) == 0  # Strictly isolated, 0 rows


def test_gstr3b_summary_upload_flow(client, auth_context):
    """Verify GSTR-3B summary CSV uploads through /upload and does not pollute the invoice table."""
    headers = auth_context["headers1"]
    db = SessionLocal()
    try:
        initial_inv_count = db.scalar(
            select(func.count(Invoice.id)).where(Invoice.business_id == auth_context["biz1"].id)
        ) or 0

        gstr3b_content = "tax_period,output_tax,eligible_itc,itc_reversed,net_itc\n2026-07,143190,43470,1200,42270\n"
        resp = client.post(
            "/upload",
            data={"source_type": "gstr3b"},
            files={"file": ("gstr3b_test.csv", io.BytesIO(gstr3b_content.encode("utf-8")), "text/csv")},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["source_type"] == "gstr3b"
        assert data["total_records"] == 1
        assert data["imported"] in {0, 1}

        # Check duplicate upload of the same summary row
        resp2 = client.post(
            "/upload",
            data={"source_type": "gstr3b"},
            files={"file": ("gstr3b_test.csv", io.BytesIO(gstr3b_content.encode("utf-8")), "text/csv")},
            headers=headers,
        )
        assert resp2.status_code == 200
        assert resp2.json()["duplicates"] == 1

        # Invoices table must NOT be polluted
        final_inv_count = db.scalar(
            select(func.count(Invoice.id)).where(Invoice.business_id == auth_context["biz1"].id)
        ) or 0
        assert final_inv_count == initial_inv_count, "GSTR-3B must not be saved to invoices table"
    finally:
        db.close()


def test_csv_upload_header_aliases_support(client, auth_context):
    """Verify CSV upload succeeds when using supported header aliases."""
    headers = auth_context["headers1"]
    csv_aliased = (
        "invoice_number,date,counterparty_gstin,taxable_amount,tax_amount\n"
        "ALIAS-001,2026-07-05,29ABCDE1234F1Z5,50000,9000\n"
    )
    resp = client.post(
        "/upload",
        data={"source_type": "sales_register"},
        files={"file": ("aliased_sales.csv", io.BytesIO(csv_aliased.encode("utf-8")), "text/csv")},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_records"] == 1
    assert data["imported"] in {0, 1}


def test_csv_upload_missing_required_column_returns_400(client, auth_context):
    """Uploading CSV with missing essential column reports clear missing column error."""
    headers = auth_context["headers1"]
    bad_csv = "date,taxable_value,gst_amount\n2026-07-05,50000,9000\n"
    resp = client.post(
        "/upload",
        data={"source_type": "sales_register"},
        files={"file": ("bad_headers.csv", io.BytesIO(bad_csv.encode("utf-8")), "text/csv")},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "Missing required column" in resp.json().get("detail", "")
