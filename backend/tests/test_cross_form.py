"""
Tests for the GSTR-3B cross-form analysis endpoint.
Uses in-memory SQLite with dependency injection to avoid Supabase.
"""

from datetime import date
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import get_db
from main import app
from models.base import Base
from models.models import Business, Invoice, User
from services.auth import create_access_token


test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)


@pytest.fixture(scope="function", autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def client():
    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def setup_user_biz(client):
    session = TestingSessionLocal()
    user = User(name="Cross Form User", email="cf@test.local", password="hashed")
    session.add(user)
    session.flush()
    biz = Business(name="CF Enterprise", gstin="29AAAAA1111A1Z5", user_id=user.id)
    session.add(biz)
    session.commit()
    token = create_access_token(user_id=user.id, email=user.email)
    return {"user": user, "biz": biz, "token": token, "session": session}


def test_gstr3b_summary_endpoint_contract(client, setup_user_biz):
    """GSTR-3B summary endpoint must return required fields."""
    biz = setup_user_biz["biz"]
    token = setup_user_biz["token"]
    res = client.get(
        "/gstr3b/summary",
        headers={"Authorization": f"Bearer {token}", "X-Business-ID": str(biz.id)},
    )
    assert res.status_code == 200
    data = res.json()
    for field in ("business_id", "tax_period", "output_tax", "eligible_itc", "itc_reversed", "net_itc"):
        assert field in data, f"Missing '{field}' in GSTR-3B summary response"


def test_gstr3b_cross_form_endpoint_returns_required_fields(client, setup_user_biz):
    """Cross-form endpoint must return the documented response structure."""
    biz = setup_user_biz["biz"]
    token = setup_user_biz["token"]
    res = client.get(
        "/gstr3b/cross-form",
        headers={"Authorization": f"Bearer {token}", "X-Business-ID": str(biz.id)},
    )
    assert res.status_code == 200
    data = res.json()
    for field in ("business_id", "tax_period", "gstr3b_data_available",
                  "register_data_available", "findings", "total_findings", "note"):
        assert field in data, f"Missing '{field}' in cross-form response"
    assert isinstance(data["findings"], list)


def test_gstr3b_cross_form_with_db_invoices(client, setup_user_biz):
    """When invoices are in the DB, register_sums should reflect them."""
    biz = setup_user_biz["biz"]
    token = setup_user_biz["token"]
    session = setup_user_biz["session"]

    # Add sales register and gstr1 invoices
    session.add(Invoice(
        invoice_no="CF-S001", invoice_date=date(2026, 7, 1),
        gstin="29ABCDE1234F1Z5", taxable_value=50000.0, gst_amount=9000.0,
        source="sales_register", business_id=biz.id
    ))
    session.add(Invoice(
        invoice_no="CF-S001", invoice_date=date(2026, 7, 1),
        gstin="29ABCDE1234F1Z5", taxable_value=50000.0, gst_amount=9000.0,
        source="gstr1", business_id=biz.id
    ))
    session.commit()

    res = client.get(
        "/gstr3b/cross-form",
        headers={"Authorization": f"Bearer {token}", "X-Business-ID": str(biz.id)},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["register_data_available"] is True
    assert data["register_sums"]["sales_register_gst"] == 9000.0
    assert data["register_sums"]["gstr1_gst"] == 9000.0


def test_gstr3b_cross_form_no_data(client, setup_user_biz):
    """With no invoices in DB, should report register_data_available=False with INFO finding."""
    biz = setup_user_biz["biz"]
    token = setup_user_biz["token"]
    res = client.get(
        "/gstr3b/cross-form",
        headers={"Authorization": f"Bearer {token}", "X-Business-ID": str(biz.id)},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["register_data_available"] is False
    # Should have at least one INFO finding explaining the gap
    info_findings = [f for f in data["findings"] if f["severity"] == "INFO"]
    assert len(info_findings) >= 1


def test_gstr3b_cross_form_requires_auth(client):
    """Cross-form endpoint must reject unauthenticated requests."""
    res = client.get("/gstr3b/cross-form")
    assert res.status_code == 401


def test_gstr3b_cross_form_note_field_present(client, setup_user_biz):
    """Response note must clearly indicate this is for investigation only."""
    biz = setup_user_biz["biz"]
    token = setup_user_biz["token"]
    res = client.get(
        "/gstr3b/cross-form",
        headers={"Authorization": f"Bearer {token}", "X-Business-ID": str(biz.id)},
    )
    data = res.json()
    note = data.get("note", "")
    assert "investigation" in note.lower() or "consult" in note.lower(), \
        "Response note must disclaim investigation-only purpose"


def test_gstr3b_invalid_tax_period_raises_400(client, setup_user_biz):
    """Invalid tax_period formats must return HTTP 400 on both summary and cross-form."""
    biz = setup_user_biz["biz"]
    token = setup_user_biz["token"]
    headers = {"Authorization": f"Bearer {token}", "X-Business-ID": str(biz.id)}

    for invalid_period in ["2026-13", "2026-00", "2026/07", "July-2026", "2026-7", "invalid"]:
        # Test summary endpoint
        res_sum = client.get(f"/gstr3b/summary?tax_period={invalid_period}", headers=headers)
        assert res_sum.status_code == 400, f"Expected 400 for summary with period '{invalid_period}'"
        assert "Invalid tax_period format" in res_sum.json()["detail"]

        # Test cross-form endpoint
        res_cf = client.get(f"/gstr3b/cross-form?tax_period={invalid_period}", headers=headers)
        assert res_cf.status_code == 400, f"Expected 400 for cross-form with period '{invalid_period}'"
        assert "Invalid tax_period format" in res_cf.json()["detail"]


def test_gstr3b_cross_form_with_gstr2b_invoices(client, setup_user_biz):
    """When GSTR-2B invoices exist in DB, cross-form should reflect GSTR-2B sums and findings."""
    biz = setup_user_biz["biz"]
    token = setup_user_biz["token"]
    session = setup_user_biz["session"]

    session.add(Invoice(
        invoice_no="CF-P001", invoice_date=date(2026, 7, 5),
        gstin="29XYZAB9012J1Z9", taxable_value=40000.0, gst_amount=7200.0,
        source="purchase_register", business_id=biz.id
    ))
    session.add(Invoice(
        invoice_no="CF-P001", invoice_date=date(2026, 7, 5),
        gstin="29XYZAB9012J1Z9", taxable_value=40000.0, gst_amount=7200.0,
        source="gstr2b", business_id=biz.id
    ))
    session.commit()

    res = client.get(
        "/gstr3b/cross-form?tax_period=2026-07",
        headers={"Authorization": f"Bearer {token}", "X-Business-ID": str(biz.id)},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["register_sums"]["gstr2b_gst"] == 7200.0
    assert "purchase_register_vs_gstr2b_gst" in data["cross_form_differences"]
    # Check for GSTR-2B integration status finding
    f_ids = [f["finding_id"] for f in data["findings"]]
    assert "cf-gstr2b-status" in f_ids


def test_gstr3b_cross_form_findings_hypotheses_tone(client, setup_user_biz):
    """Findings must provide possible causes as hypotheses and recommend investigation."""
    biz = setup_user_biz["biz"]
    token = setup_user_biz["token"]
    session = setup_user_biz["session"]

    # Introduce a mismatch between sales register and gstr1
    session.add(Invoice(
        invoice_no="CF-S010", invoice_date=date(2026, 7, 10),
        gstin="29ABCDE1234F1Z5", taxable_value=100000.0, gst_amount=18000.0,
        source="sales_register", business_id=biz.id
    ))
    session.add(Invoice(
        invoice_no="CF-S010", invoice_date=date(2026, 7, 10),
        gstin="29ABCDE1234F1Z5", taxable_value=80000.0, gst_amount=14400.0,
        source="gstr1", business_id=biz.id
    ))
    session.commit()

    res = client.get(
        "/gstr3b/cross-form?tax_period=2026-07",
        headers={"Authorization": f"Bearer {token}", "X-Business-ID": str(biz.id)},
    )
    assert res.status_code == 200
    data = res.json()
    sales_finding = next((f for f in data["findings"] if f["finding_id"] == "cf-sales-gstr1-diff"), None)
    assert sales_finding is not None
    assert "possible_causes" in sales_finding
    assert any("Hypothesis" in cause for cause in sales_finding["possible_causes"])
    assert "Investigate" in sales_finding["recommendation"] or "review" in sales_finding["recommendation"].lower()
