"""
Tests for Pre-Deployment Hardening:
- Database-backed /health endpoint (200 on healthy DB, 503 on broken DB)
- GSTR-3B database persistence, idempotency, updates, and multi-tenant isolation
- Secure seeding credentials and repeated seeding safety
"""

import io
from datetime import date
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from database import get_db
from import_data import ensure_user, get_seed_credentials, import_gstr3b_file
from main import app
from models.base import Base
from models.models import Business, GSTR3BReturn, Invoice, User
from services.auth import create_access_token, hash_password, verify_password


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
def multi_tenant_setup(client):
    session = TestingSessionLocal()
    user1 = User(name="User One", email="user1@test.local", password="hashed_user1")
    user2 = User(name="User Two", email="user2@test.local", password="hashed_user2")
    session.add_all([user1, user2])
    session.flush()

    biz1 = Business(name="Enterprise Alpha", gstin="29AAAAA1111A1Z5", user_id=user1.id)
    biz2 = Business(name="Enterprise Beta", gstin="27BBBBB2222B2Z6", user_id=user2.id)
    session.add_all([biz1, biz2])
    session.commit()

    token1 = create_access_token(user_id=user1.id, email=user1.email)
    token2 = create_access_token(user_id=user2.id, email=user2.email)

    return {
        "biz1": biz1,
        "biz2": biz2,
        "token1": token1,
        "token2": token2,
        "session": session,
    }


# ─────────────────────────────────────────────────────────────
# 1. Real Database Health Check Tests
# ─────────────────────────────────────────────────────────────

def test_health_check_success(client):
    """When database connectivity is operational, /health returns HTTP 200."""
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["database"] == "connected"


def test_health_check_db_failure(client):
    """When database is inaccessible, /health returns HTTP 503 without leaking credentials or traces."""
    def broken_get_db():
        class MockBrokenSession:
            def execute(self, statement):
                raise OperationalError("Connection refused to postgres:5432 with password=SECRET", params={}, orig=Exception("Network drop"))
            def close(self):
                pass
        yield MockBrokenSession()

    app.dependency_overrides[get_db] = broken_get_db
    try:
        res = client.get("/health")
        assert res.status_code == 503
        data = res.json()
        assert data["status"] == "error"
        assert data["database"] == "disconnected"
        assert "SECRET" not in res.text
        assert "password" not in res.text.lower()
        assert "Traceback" not in res.text
    finally:
        app.dependency_overrides.pop(get_db, None)


# ─────────────────────────────────────────────────────────────
# 2. GSTR-3B Persistence and Idempotency Tests
# ─────────────────────────────────────────────────────────────

def test_gstr3b_upload_persists_to_db(client, multi_tenant_setup):
    """Uploading GSTR-3B CSV persists rows into the gstr3b_returns table for current business."""
    biz1 = multi_tenant_setup["biz1"]
    token1 = multi_tenant_setup["token1"]
    session = multi_tenant_setup["session"]

    csv_content = (
        "tax_period,output_tax,eligible_itc,itc_reversed,net_itc\n"
        "2026-07,143190.0,43470.0,1200.0,42270.0\n"
        "2026-08,125000.0,38000.0,1000.0,37000.0\n"
    )

    headers = {"Authorization": f"Bearer {token1}", "X-Business-ID": str(biz1.id)}
    res = client.post(
        "/invoices/upload",
        data={"source_type": "gstr3b"},
        files={"file": ("gstr3b_custom.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
        headers=headers,
    )

    assert res.status_code == 200
    data = res.json()
    assert data["source_type"] == "gstr3b"
    assert data["imported"] == 2
    assert data["duplicates"] == 0

    # Verify directly in SQLite test database
    records = session.scalars(
        select(GSTR3BReturn).where(GSTR3BReturn.business_id == biz1.id).order_by(GSTR3BReturn.tax_period)
    ).all()
    assert len(records) == 2
    assert records[0].tax_period == "2026-07"
    assert records[0].output_tax == 143190.0
    assert records[0].net_itc == 42270.0
    assert records[1].tax_period == "2026-08"
    assert records[1].output_tax == 125000.0


def test_gstr3b_upload_idempotency_and_update(client, multi_tenant_setup):
    """Uploading exact duplicates reports duplicates; uploading revised values updates the existing row."""
    biz1 = multi_tenant_setup["biz1"]
    token1 = multi_tenant_setup["token1"]
    session = multi_tenant_setup["session"]

    csv_initial = (
        "tax_period,output_tax,eligible_itc,itc_reversed,net_itc\n"
        "2026-07,100000.0,30000.0,500.0,29500.0\n"
    )

    headers = {"Authorization": f"Bearer {token1}", "X-Business-ID": str(biz1.id)}
    res1 = client.post(
        "/invoices/upload",
        data={"source_type": "gstr3b"},
        files={"file": ("gstr3b.csv", io.BytesIO(csv_initial.encode("utf-8")), "text/csv")},
        headers=headers,
    )
    assert res1.status_code == 200
    assert res1.json()["imported"] == 1

    # Repeat exact same file -> must detect duplicate
    res2 = client.post(
        "/invoices/upload",
        data={"source_type": "gstr3b"},
        files={"file": ("gstr3b.csv", io.BytesIO(csv_initial.encode("utf-8")), "text/csv")},
        headers=headers,
    )
    assert res2.status_code == 200
    assert res2.json()["duplicates"] == 1
    assert res2.json()["imported"] == 0

    # Upload revised numbers for the same tax_period -> must update the record idempotently
    csv_revised = (
        "tax_period,output_tax,eligible_itc,itc_reversed,net_itc\n"
        "2026-07,115000.0,35000.0,800.0,34200.0\n"
    )
    res3 = client.post(
        "/invoices/upload",
        data={"source_type": "gstr3b"},
        files={"file": ("gstr3b_revised.csv", io.BytesIO(csv_revised.encode("utf-8")), "text/csv")},
        headers=headers,
    )
    assert res3.status_code == 200
    assert res3.json()["imported"] == 0
    assert res3.json()["revised"] == 1
    assert res3.json()["duplicates"] == 0

    # Database must still have only 1 record, but with revised values
    records = session.scalars(
        select(GSTR3BReturn).where(GSTR3BReturn.business_id == biz1.id)
    ).all()
    assert len(records) == 1
    assert records[0].output_tax == 115000.0
    assert records[0].net_itc == 34200.0


# ─────────────────────────────────────────────────────────────
# 3. Multi-Tenant Isolation Tests for GSTR-3B
# ─────────────────────────────────────────────────────────────

def test_gstr3b_tenant_isolation(client, multi_tenant_setup):
    """Business 2 cannot see or access GSTR-3B filings uploaded by Business 1."""
    biz1 = multi_tenant_setup["biz1"]
    biz2 = multi_tenant_setup["biz2"]
    token1 = multi_tenant_setup["token1"]
    token2 = multi_tenant_setup["token2"]

    # Upload GSTR-3B for Business 1
    csv_biz1 = (
        "tax_period,output_tax,eligible_itc,itc_reversed,net_itc\n"
        "2026-07,999999.0,888888.0,0.0,888888.0\n"
    )
    client.post(
        "/invoices/upload",
        data={"source_type": "gstr3b"},
        files={"file": ("biz1_3b.csv", io.BytesIO(csv_biz1.encode("utf-8")), "text/csv")},
        headers={"Authorization": f"Bearer {token1}", "X-Business-ID": str(biz1.id)},
    )

    # Business 2 queries summary
    res_biz2 = client.get(
        "/gstr3b/summary?tax_period=2026-07",
        headers={"Authorization": f"Bearer {token2}", "X-Business-ID": str(biz2.id)},
    )
    assert res_biz2.status_code == 200
    data_biz2 = res_biz2.json()
    assert data_biz2["business_id"] == biz2.id
    assert data_biz2["data_available"] is False
    assert data_biz2["source"] == "none"
    assert data_biz2["output_tax"] == 0.0

    # Business 2 uploads its own distinct GSTR-3B
    csv_biz2 = (
        "tax_period,output_tax,eligible_itc,itc_reversed,net_itc\n"
        "2026-07,55555.0,22222.0,100.0,22122.0\n"
    )
    client.post(
        "/invoices/upload",
        data={"source_type": "gstr3b"},
        files={"file": ("biz2_3b.csv", io.BytesIO(csv_biz2.encode("utf-8")), "text/csv")},
        headers={"Authorization": f"Bearer {token2}", "X-Business-ID": str(biz2.id)},
    )

    # Check Business 2 now sees only its own data
    res_biz2_after = client.get(
        "/gstr3b/summary?tax_period=2026-07",
        headers={"Authorization": f"Bearer {token2}", "X-Business-ID": str(biz2.id)},
    )
    assert res_biz2_after.status_code == 200
    assert res_biz2_after.json()["output_tax"] == 55555.0
    assert res_biz2_after.json()["source"] == "database"

    # Check Business 1 still sees only its own data
    res_biz1_after = client.get(
        "/gstr3b/summary?tax_period=2026-07",
        headers={"Authorization": f"Bearer {token1}", "X-Business-ID": str(biz1.id)},
    )
    assert res_biz1_after.status_code == 200
    assert res_biz1_after.json()["output_tax"] == 999999.0
    assert res_biz1_after.json()["source"] == "database"


def test_gstr3b_cross_form_uses_db_persistence(client, multi_tenant_setup):
    """Cross-form comparison uses persistent GSTR-3B records from the database."""
    biz2 = multi_tenant_setup["biz2"]
    token2 = multi_tenant_setup["token2"]
    session = multi_tenant_setup["session"]

    # Seed GSTR-3B into DB for Business 2
    session.add(GSTR3BReturn(
        business_id=biz2.id,
        tax_period="2026-07",
        output_tax=50000.0,
        eligible_itc=15000.0,
        itc_reversed=0.0,
        net_itc=15000.0,
    ))
    # Add GSTR-1 outward invoice for Business 2
    session.add(Invoice(
        invoice_no="INV-B2-01",
        invoice_date=date(2026, 7, 10),
        gstin="29TEST9999A1Z1",
        taxable_value=250000.0,
        gst_amount=45000.0,
        source="gstr1",
        business_id=biz2.id,
    ))
    session.commit()

    res = client.get(
        "/gstr3b/cross-form?tax_period=2026-07",
        headers={"Authorization": f"Bearer {token2}", "X-Business-ID": str(biz2.id)},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["gstr3b_summary"]["output_tax"] == 50000.0
    assert data["gstr3b_summary"]["eligible_itc"] == 15000.0
    assert data["cross_form_differences"]["gstr1_vs_gstr3b_output_tax"] == -5000.0  # 45000 - 50000


# ─────────────────────────────────────────────────────────────
# 4. Secure Database Seeding Tests
# ─────────────────────────────────────────────────────────────

def test_secure_seeding_production_requires_credentials(monkeypatch):
    """In production mode, missing SEED_ADMIN_EMAIL or SEED_ADMIN_PASSWORD raises ValueError."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("SEED_ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("SEED_ADMIN_PASSWORD", raising=False)

    with pytest.raises(ValueError, match="SEED_ADMIN_EMAIL environment variable is required"):
        get_seed_credentials()

    monkeypatch.setenv("SEED_ADMIN_EMAIL", "admin@company.com")
    with pytest.raises(ValueError, match="SEED_ADMIN_PASSWORD environment variable is required"):
        get_seed_credentials()


def test_secure_seeding_production_rejects_weak_defaults(monkeypatch):
    """In production mode, default passwords like 'changeme' or 'admin' are explicitly rejected."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SEED_ADMIN_EMAIL", "admin@company.com")

    for weak in ["changeme", "admin", "password", "12345678"]:
        monkeypatch.setenv("SEED_ADMIN_PASSWORD", weak)
        with pytest.raises(ValueError, match="cannot use common default/insecure passwords"):
            get_seed_credentials()


def test_repeat_seeding_preserves_existing_password():
    """Repeat seeding runs must never overwrite an existing user's password."""
    session = TestingSessionLocal()
    original_pwd = "StrongCustomPassword@999"
    email = "admin-preserve@test.local"

    # First seeding run
    user1 = ensure_user(session, email=email, password=original_pwd)
    session.commit()
    stored_hash1 = user1.password

    # Second seeding run with a different password
    user2 = ensure_user(session, email=email, password="NewAttemptedPassword@123")
    session.commit()

    # The password in DB must remain the original hash
    assert user2.password == stored_hash1
    is_valid, _ = verify_password(original_pwd, user2.password)
    assert is_valid is True
    is_invalid, _ = verify_password("NewAttemptedPassword@123", user2.password)
    assert is_invalid is False
    session.close()


# ─────────────────────────────────────────────────────────────
# 5. Regression Tests for Blocker 1 & Blocker 2
# ─────────────────────────────────────────────────────────────

def test_real_business_id1_different_gstin_receives_no_demo_fallback(client):
    """A real business with ID 1 but a non-demo GSTIN must NEVER see synthetic demo figures."""
    session = TestingSessionLocal()
    user = User(name="Real Customer", email="realcustomer@corp.in", password="hashed_real")
    session.add(user)
    session.flush()

    # Create business with ID 1 and real customer GSTIN
    biz = Business(id=1, name="Real Customer Corp", gstin="29REALCUST1111A", user_id=user.id)
    session.add(biz)
    session.commit()

    token = create_access_token(user_id=user.id, email=user.email)

    res = client.get(
        "/gstr3b/summary?tax_period=2026-07",
        headers={"Authorization": f"Bearer {token}", "X-Business-ID": str(biz.id)},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["business_id"] == 1
    assert data["data_available"] is False
    assert data["output_tax"] == 0.0
    assert "No GSTR-3B filing data available" in data["note"]


def test_demo_gstin_fallback_controlled_by_environment(client, monkeypatch):
    """Business with demo GSTIN gets fallback only when permitted by environment (disabled in production by default)."""
    session = TestingSessionLocal()
    user = User(name="Demo Owner", email="demo@test.local", password="hashed_demo")
    session.add(user)
    session.flush()

    biz = Business(name="Demo MSME", gstin="29AAAAA1111A1Z5", user_id=user.id)
    session.add(biz)
    session.commit()

    token = create_access_token(user_id=user.id, email=user.email)
    headers = {"Authorization": f"Bearer {token}", "X-Business-ID": str(biz.id)}

    # 1. In production mode without explicit DEMO_MODE, fallback must be disabled
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.setenv("GST_API_DEMO_MODE", "true")

    res_prod = client.get("/gstr3b/summary?tax_period=2026-07", headers=headers)
    assert res_prod.status_code == 200
    assert res_prod.json()["data_available"] is False
    assert res_prod.json()["source"] == "none"
    assert res_prod.json()["output_tax"] == 0.0

    # 2. When DEMO_MODE=true is explicitly set in production, fallback is safely permitted
    monkeypatch.setenv("DEMO_MODE", "true")
    res_demo = client.get("/gstr3b/summary?tax_period=2026-07", headers=headers)
    assert res_demo.status_code == 200
    assert res_demo.json()["data_available"] is True
    assert res_demo.json()["output_tax"] == 143190.0
    assert res_demo.json()["source"] == "demo_fixture"

    # An unavailable requested period must not borrow another fixture period's figures.
    res_missing_period = client.get("/gstr3b/summary?tax_period=2026-06", headers=headers)
    assert res_missing_period.status_code == 200
    missing_period_data = res_missing_period.json()
    assert missing_period_data["tax_period"] == "2026-06"
    assert missing_period_data["data_available"] is False
    assert missing_period_data["source"] == "none"
    assert missing_period_data["output_tax"] == 0.0


def test_intra_batch_duplicate_identical_periods_deduplicated(client, multi_tenant_setup):
    """Identical duplicate rows for the same period in one CSV are de-duplicated without crashing."""
    biz1 = multi_tenant_setup["biz1"]
    token1 = multi_tenant_setup["token1"]
    session = multi_tenant_setup["session"]

    csv_batch = (
        "tax_period,output_tax,eligible_itc,itc_reversed,net_itc\n"
        "2026-07,143190.0,43470.0,1200.0,42270.0\n"
        "2026-07,143190.0,43470.0,1200.0,42270.0\n"
        "2026-08,125000.0,38000.0,1000.0,37000.0\n"
    )

    headers = {"Authorization": f"Bearer {token1}", "X-Business-ID": str(biz1.id)}
    res = client.post(
        "/invoices/upload",
        data={"source_type": "gstr3b"},
        files={"file": ("batch_dup.csv", io.BytesIO(csv_batch.encode("utf-8")), "text/csv")},
        headers=headers,
    )

    assert res.status_code == 200
    data = res.json()
    assert data["total_records"] == 3
    assert data["imported"] == 2
    assert data["duplicates"] == 1

    records = session.scalars(
        select(GSTR3BReturn).where(GSTR3BReturn.business_id == biz1.id).order_by(GSTR3BReturn.tax_period)
    ).all()
    assert len(records) == 2


def test_intra_batch_conflicting_periods_returns_422(client, multi_tenant_setup):
    """Conflicting rows for the same period in a single CSV must be rejected with HTTP 422."""
    biz1 = multi_tenant_setup["biz1"]
    token1 = multi_tenant_setup["token1"]
    session = multi_tenant_setup["session"]

    csv_conflict = (
        "tax_period,output_tax,eligible_itc,itc_reversed,net_itc\n"
        "2026-07,100000.0,30000.0,500.0,29500.0\n"
        "2026-07,150000.0,30000.0,500.0,29500.0\n"
    )

    headers = {"Authorization": f"Bearer {token1}", "X-Business-ID": str(biz1.id)}
    res = client.post(
        "/invoices/upload",
        data={"source_type": "gstr3b"},
        files={"file": ("conflict.csv", io.BytesIO(csv_conflict.encode("utf-8")), "text/csv")},
        headers=headers,
    )

    assert res.status_code == 422
    assert "Conflicting GSTR-3B records found in upload" in res.json()["detail"]

    # Verify transaction rollback: zero records stored
    records = session.scalars(
        select(GSTR3BReturn).where(GSTR3BReturn.business_id == biz1.id)
    ).all()
    assert len(records) == 0


def test_concurrent_upload_conflict_returns_409(client, multi_tenant_setup, monkeypatch):
    """When a concurrent insert causes an IntegrityError at commit, an HTTP 409 Conflict is returned."""
    from sqlalchemy.exc import IntegrityError as SqlIntegrityError

    biz1 = multi_tenant_setup["biz1"]
    token1 = multi_tenant_setup["token1"]

    csv_content = (
        "tax_period,output_tax,eligible_itc,itc_reversed,net_itc\n"
        "2026-07,100000.0,30000.0,500.0,29500.0\n"
    )

    headers = {"Authorization": f"Bearer {token1}", "X-Business-ID": str(biz1.id)}

    # Simulate IntegrityError at commit time
    def raise_integrity_error():
        raise SqlIntegrityError("duplicate key value violates unique constraint", params={}, orig=Exception("Conflict"))

    def override_get_db_with_mock_commit():
        session = TestingSessionLocal()
        session.commit = raise_integrity_error
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db_with_mock_commit
    try:
        res = client.post(
            "/invoices/upload",
            data={"source_type": "gstr3b"},
            files={"file": ("concurrent.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
            headers=headers,
        )
        assert res.status_code == 409
        assert "conflicting GSTR-3B return was concurrently modified" in res.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_db, None)

