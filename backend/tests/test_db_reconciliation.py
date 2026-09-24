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


# Create isolated in-memory SQLite database so tests never touch Supabase
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
def db_session():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


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
def setup_tenants(db_session):
    # Tenant A
    user_a = User(name="User A", email="test_user_a@test.local", password="hashed_pwd_a")
    db_session.add(user_a)
    db_session.flush()

    biz_a = Business(name="Enterprise A", gstin="29AAAAA0001A1Z1", user_id=user_a.id)
    db_session.add(biz_a)
    db_session.flush()

    token_a = create_access_token(user_id=user_a.id, email=user_a.email)

    # Tenant B
    user_b = User(name="User B", email="test_user_b@test.local", password="hashed_pwd_b")
    db_session.add(user_b)
    db_session.flush()

    biz_b = Business(name="Enterprise B", gstin="29BBBBB0002B1Z2", user_id=user_b.id)
    db_session.add(biz_b)
    db_session.flush()

    token_b = create_access_token(user_id=user_b.id, email=user_b.email)

    db_session.commit()

    return {
        "user_a": user_a,
        "biz_a": biz_a,
        "token_a": token_a,
        "user_b": user_b,
        "biz_b": biz_b,
        "token_b": token_b,
    }


def test_business_isolation_cannot_see_other_business_data(client, db_session, setup_tenants):
    biz_a = setup_tenants["biz_a"]
    token_a = setup_tenants["token_a"]
    biz_b = setup_tenants["biz_b"]
    token_b = setup_tenants["token_b"]

    # Insert invoice for Business A
    inv_a1 = Invoice(
        invoice_no="INV-A100",
        invoice_date=date(2026, 7, 1),
        gstin="29CPARTY0001Z5",
        taxable_value=10000.0,
        gst_amount=1800.0,
        source="sales_register",
        business_id=biz_a.id,
    )
    inv_a1_gst = Invoice(
        invoice_no="INV-A100",
        invoice_date=date(2026, 7, 1),
        gstin="29CPARTY0001Z5",
        taxable_value=10000.0,
        gst_amount=1800.0,
        source="gstr1",
        business_id=biz_a.id,
    )

    # Insert invoice for Business B
    inv_b1 = Invoice(
        invoice_no="INV-B200",
        invoice_date=date(2026, 7, 2),
        gstin="29CPARTY0002Z5",
        taxable_value=50000.0,
        gst_amount=9000.0,
        source="sales_register",
        business_id=biz_b.id,
    )
    inv_b1_gst = Invoice(
        invoice_no="INV-B200",
        invoice_date=date(2026, 7, 2),
        gstin="29CPARTY0002Z5",
        taxable_value=50000.0,
        gst_amount=9000.0,
        source="gstr1",
        business_id=biz_b.id,
    )

    db_session.add_all([inv_a1, inv_a1_gst, inv_b1, inv_b1_gst])
    db_session.commit()

    # Reconcile as Business A
    res_a = client.get(
        "/reconcile",
        headers={"Authorization": f"Bearer {token_a}", "X-Business-ID": str(biz_a.id)},
    )
    assert res_a.status_code == 200
    data_a = res_a.json()
    assert data_a["summary"]["business_id"] == biz_a.id
    sales_a_invs = [s["invoice_no"] for s in data_a["sales"]]
    assert "INV-A100" in sales_a_invs
    assert "INV-B200" not in sales_a_invs, "Business A must NOT see Business B records!"

    # Reconcile as Business B
    res_b = client.get(
        "/reconcile",
        headers={"Authorization": f"Bearer {token_b}", "X-Business-ID": str(biz_b.id)},
    )
    assert res_b.status_code == 200
    data_b = res_b.json()
    assert data_b["summary"]["business_id"] == biz_b.id
    sales_b_invs = [s["invoice_no"] for s in data_b["sales"]]
    assert "INV-B200" in sales_b_invs
    assert "INV-A100" not in sales_b_invs, "Business B must NOT see Business A records!"

    # Cross-tenant access header rejection
    cross_res = client.get(
        "/reconcile",
        headers={"Authorization": f"Bearer {token_a}", "X-Business-ID": str(biz_b.id)},
    )
    assert cross_res.status_code == 403


def test_reconciliation_uses_database_records_not_csv(client, db_session, setup_tenants):
    biz_a = setup_tenants["biz_a"]
    token_a = setup_tenants["token_a"]

    # Insert a distinct database-only invoice with specific values
    custom_inv_no = "INV-DB-CUSTOM-777"
    inv_sales = Invoice(
        invoice_no=custom_inv_no,
        invoice_date=date(2026, 7, 10),
        gstin="29CUSTOM0001Z9",
        taxable_value=77777.0,
        gst_amount=13999.86,
        source="sales_register",
        business_id=biz_a.id,
    )
    inv_portal = Invoice(
        invoice_no=custom_inv_no,
        invoice_date=date(2026, 7, 10),
        gstin="29CUSTOM0001Z9",
        taxable_value=77777.0,
        gst_amount=13999.86,
        source="gstr1",
        business_id=biz_a.id,
    )
    db_session.add_all([inv_sales, inv_portal])
    db_session.commit()

    res = client.get(
        "/reconcile",
        headers={"Authorization": f"Bearer {token_a}", "X-Business-ID": str(biz_a.id)},
    )
    assert res.status_code == 200
    data = res.json()
    matched = [s for s in data["sales"] if s["invoice_no"] == custom_inv_no]
    assert len(matched) == 1
    assert matched[0]["status"] == "MATCH"
    assert matched[0]["taxable_value"] == 77777.0
    assert matched[0]["gst_amount"] == 13999.86


def test_all_four_reconciliation_statuses(client, db_session, setup_tenants):
    biz_a = setup_tenants["biz_a"]
    token_a = setup_tenants["token_a"]

    # 1. MATCH
    m_reg = Invoice(
        invoice_no="INV-STAT-MATCH",
        invoice_date=date(2026, 7, 1),
        gstin="29AAAAA1111A1Z5",
        taxable_value=10000.0,
        gst_amount=1800.0,
        source="sales_register",
        business_id=biz_a.id,
    )
    m_gst = Invoice(
        invoice_no="INV-STAT-MATCH",
        invoice_date=date(2026, 7, 1),
        gstin="29AAAAA1111A1Z5",
        taxable_value=10000.0,
        gst_amount=1800.0,
        source="gstr1",
        business_id=biz_a.id,
    )

    # 2. MISMATCH
    mm_reg = Invoice(
        invoice_no="INV-STAT-MISMATCH",
        invoice_date=date(2026, 7, 2),
        gstin="29BBBBB2222B1Z5",
        taxable_value=20000.0,
        gst_amount=3600.0,
        source="sales_register",
        business_id=biz_a.id,
    )
    mm_gst = Invoice(
        invoice_no="INV-STAT-MISMATCH",
        invoice_date=date(2026, 7, 2),
        gstin="29BBBBB2222B1Z5",
        taxable_value=18000.0,
        gst_amount=3240.0,
        source="gstr1",
        business_id=biz_a.id,
    )

    # 3. MISSING_IN_GST
    mis_reg = Invoice(
        invoice_no="INV-STAT-MISSING",
        invoice_date=date(2026, 7, 3),
        gstin="29CCCCC3333C1Z5",
        taxable_value=15000.0,
        gst_amount=2700.0,
        source="sales_register",
        business_id=biz_a.id,
    )

    # 4. EXTRA_IN_GST
    ext_gst = Invoice(
        invoice_no="INV-STAT-EXTRA",
        invoice_date=date(2026, 7, 4),
        gstin="29DDDDD4444D1Z5",
        taxable_value=12000.0,
        gst_amount=2160.0,
        source="gstr1",
        business_id=biz_a.id,
    )

    db_session.add_all([m_reg, m_gst, mm_reg, mm_gst, mis_reg, ext_gst])
    db_session.commit()

    res = client.get(
        "/reconcile",
        headers={"Authorization": f"Bearer {token_a}", "X-Business-ID": str(biz_a.id)},
    )
    assert res.status_code == 200
    data = res.json()
    sales = {s["invoice_no"]: s for s in data["sales"]}

    assert sales["INV-STAT-MATCH"]["status"] == "MATCH"
    assert sales["INV-STAT-MATCH"]["taxable_value_diff"] == 0.0

    assert sales["INV-STAT-MISMATCH"]["status"] == "MISMATCH"
    assert sales["INV-STAT-MISMATCH"]["taxable_value_diff"] == 2000.0

    assert sales["INV-STAT-MISSING"]["status"] == "MISSING_IN_GST"
    assert sales["INV-STAT-MISSING"]["expected_taxable_value"] == 15000.0
    assert sales["INV-STAT-MISSING"]["actual_taxable_value"] is None

    assert sales["INV-STAT-EXTRA"]["status"] == "EXTRA_IN_GST"
    assert sales["INV-STAT-EXTRA"]["expected_taxable_value"] is None
    assert sales["INV-STAT-EXTRA"]["actual_taxable_value"] == 12000.0

    # Verify summary counts
    summary = data["summary"]
    assert summary["matched"] >= 1
    assert summary["mismatched"] >= 1
    assert summary["missing_in_gst"] >= 1
    assert summary["extra_in_gst"] >= 1


def test_tax_period_filtering(client, db_session, setup_tenants):
    biz_a = setup_tenants["biz_a"]
    token_a = setup_tenants["token_a"]

    # July 2026 invoice
    inv_july = Invoice(
        invoice_no="INV-PERIOD-JULY",
        invoice_date=date(2026, 7, 15),
        gstin="29PERIOD0001Z1",
        taxable_value=30000.0,
        gst_amount=5400.0,
        source="sales_register",
        business_id=biz_a.id,
    )
    # August 2026 invoice
    inv_aug = Invoice(
        invoice_no="INV-PERIOD-AUG",
        invoice_date=date(2026, 8, 20),
        gstin="29PERIOD0002Z2",
        taxable_value=40000.0,
        gst_amount=7200.0,
        source="sales_register",
        business_id=biz_a.id,
    )
    db_session.add_all([inv_july, inv_aug])
    db_session.commit()

    # Query 2026-07
    res_jul = client.get(
        "/reconcile?tax_period=2026-07",
        headers={"Authorization": f"Bearer {token_a}", "X-Business-ID": str(biz_a.id)},
    )
    assert res_jul.status_code == 200
    jul_sales = [s["invoice_no"] for s in res_jul.json()["sales"]]
    assert "INV-PERIOD-JULY" in jul_sales
    assert "INV-PERIOD-AUG" not in jul_sales

    # Query 2026-08
    res_aug = client.get(
        "/reconcile?tax_period=2026-08",
        headers={"Authorization": f"Bearer {token_a}", "X-Business-ID": str(biz_a.id)},
    )
    assert res_aug.status_code == 200
    aug_sales = [s["invoice_no"] for s in res_aug.json()["sales"]]
    assert "INV-PERIOD-AUG" in aug_sales
    assert "INV-PERIOD-JULY" not in aug_sales

    # Query 2026-09 (Period with no records -> empty data, no invented data)
    res_sep = client.get(
        "/reconcile?tax_period=2026-09",
        headers={"Authorization": f"Bearer {token_a}", "X-Business-ID": str(biz_a.id)},
    )
    assert res_sep.status_code == 200
    sep_data = res_sep.json()
    assert sep_data["sales"] == []
    assert sep_data["purchases"] == []
    assert sep_data["summary"]["total_records"] == 0

    # Query invalid tax_period format
    res_bad = client.get(
        "/reconcile?tax_period=invalid-period",
        headers={"Authorization": f"Bearer {token_a}", "X-Business-ID": str(biz_a.id)},
    )
    assert res_bad.status_code == 400

    # Query invalid month (13)
    res_bad_month = client.get(
        "/reconcile?tax_period=2026-13",
        headers={"Authorization": f"Bearer {token_a}", "X-Business-ID": str(biz_a.id)},
    )
    assert res_bad_month.status_code == 400


def test_duplicate_invoice_number_handling(client, db_session, setup_tenants):
    biz_a = setup_tenants["biz_a"]
    token_a = setup_tenants["token_a"]

    dup_no = "INV-DUP-SAFE-99"

    # Insert two records with the same invoice number in sales_register
    dup_1 = Invoice(
        invoice_no=dup_no,
        invoice_date=date(2026, 7, 5),
        gstin="29DUP00001Z9",
        taxable_value=10000.0,
        gst_amount=1800.0,
        source="sales_register",
        business_id=biz_a.id,
    )
    dup_2 = Invoice(
        invoice_no=dup_no,
        invoice_date=date(2026, 7, 5),
        gstin="29DUP00001Z9",
        taxable_value=10000.0,
        gst_amount=1800.0,
        source="sales_register",
        business_id=biz_a.id,
    )
    # One record in gstr1
    dup_gst = Invoice(
        invoice_no=dup_no,
        invoice_date=date(2026, 7, 5),
        gstin="29DUP00001Z9",
        taxable_value=10000.0,
        gst_amount=1800.0,
        source="gstr1",
        business_id=biz_a.id,
    )

    db_session.add_all([dup_1, dup_2, dup_gst])
    db_session.commit()

    res = client.get(
        "/reconcile",
        headers={"Authorization": f"Bearer {token_a}", "X-Business-ID": str(biz_a.id)},
    )
    assert res.status_code == 200
    data = res.json()

    # Verify that BOTH duplicate records are retained and not dropped by .iloc[0]
    dup_records = [s for s in data["sales"] if s["invoice_no"] == dup_no]
    assert len(dup_records) == 2, f"Expected 2 duplicate rows preserved, got {len(dup_records)}"
    for r in dup_records:
        assert r["status"] == "MISMATCH"
        assert "Duplicate invoice number" in r["explanation"]


def test_database_failure_returns_503_without_csv_fallback(client, setup_tenants):
    token_a = setup_tenants["token_a"]
    biz_a = setup_tenants["biz_a"]

    # Yield a broken database session whose queries fail on scalars
    real_session = TestingSessionLocal()
    class BrokenSession:
        def scalar(self, *args, **kwargs):
            return real_session.scalar(*args, **kwargs)

        def scalars(self, statement, *args, **kwargs):
            if "invoices" in str(statement).lower():
                raise RuntimeError("Simulated database connection failure")
            return real_session.scalars(statement, *args, **kwargs)

    def broken_get_db():
        yield BrokenSession()

    app.dependency_overrides[get_db] = broken_get_db

    try:
        res = client.get(
            "/reconcile",
            headers={"Authorization": f"Bearer {token_a}", "X-Business-ID": str(biz_a.id)},
        )
        assert res.status_code == 503
        assert "Reconciliation data is temporarily unavailable." in res.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_empty_database_result(client, setup_tenants):
    # Tenant with zero invoices in DB
    token_b = setup_tenants["token_b"]
    biz_b = setup_tenants["biz_b"]

    res = client.get(
        "/reconcile",
        headers={"Authorization": f"Bearer {token_b}", "X-Business-ID": str(biz_b.id)},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["sales"] == []
    assert data["purchases"] == []
    assert data["summary"]["total_records"] == 0
    assert data["summary"]["matched"] == 0
    assert data["summary"]["mismatched"] == 0
    assert data["summary"]["missing_in_gst"] == 0
    assert data["summary"]["extra_in_gst"] == 0
    # Proves no silent fallback to CSV files when DB is empty for this business
    assert len(data["sales"]) == 0
    assert len(data["purchases"]) == 0


def test_invalid_tax_periods_all_variants(client, setup_tenants):
    token_a = setup_tenants["token_a"]
    biz_a = setup_tenants["biz_a"]

    invalid_periods = ["2026-7", "2026-13", "2026-00", "abc", "2026/07", "07-2026", "2026-99"]
    for bad_period in invalid_periods:
        res = client.get(
            f"/reconcile?tax_period={bad_period}",
            headers={"Authorization": f"Bearer {token_a}", "X-Business-ID": str(biz_a.id)},
        )
        assert res.status_code == 400, f"Expected 400 for tax_period='{bad_period}', got {res.status_code}"


def test_duplicate_invoices_in_unilateral_sets_db(client, db_session, setup_tenants):
    biz_a = setup_tenants["biz_a"]
    token_a = setup_tenants["token_a"]

    # 2 duplicate records in books, 0 in GST
    inv_mis1 = Invoice(
        invoice_no="INV-UNILAT-MIS",
        invoice_date=date(2026, 7, 8),
        gstin="29MIS00001Z1",
        taxable_value=8000.0,
        gst_amount=1440.0,
        source="sales_register",
        business_id=biz_a.id,
    )
    inv_mis2 = Invoice(
        invoice_no="INV-UNILAT-MIS",
        invoice_date=date(2026, 7, 8),
        gstin="29MIS00001Z1",
        taxable_value=8000.0,
        gst_amount=1440.0,
        source="sales_register",
        business_id=biz_a.id,
    )

    # 2 duplicate records in GST portal, 0 in books
    inv_ext1 = Invoice(
        invoice_no="INV-UNILAT-EXT",
        invoice_date=date(2026, 7, 9),
        gstin="29EXT00002Z2",
        taxable_value=6000.0,
        gst_amount=1080.0,
        source="gstr1",
        business_id=biz_a.id,
    )
    inv_ext2 = Invoice(
        invoice_no="INV-UNILAT-EXT",
        invoice_date=date(2026, 7, 9),
        gstin="29EXT00002Z2",
        taxable_value=6000.0,
        gst_amount=1080.0,
        source="gstr1",
        business_id=biz_a.id,
    )

    db_session.add_all([inv_mis1, inv_mis2, inv_ext1, inv_ext2])
    db_session.commit()

    res = client.get(
        "/reconcile",
        headers={"Authorization": f"Bearer {token_a}", "X-Business-ID": str(biz_a.id)},
    )
    assert res.status_code == 200
    data = res.json()

    mis_items = [s for s in data["sales"] if s["invoice_no"] == "INV-UNILAT-MIS"]
    assert len(mis_items) == 2, "Both missing duplicate records must be preserved"
    for m in mis_items:
        assert m["status"] == "MISSING_IN_GST"

    ext_items = [s for s in data["sales"] if s["invoice_no"] == "INV-UNILAT-EXT"]
    assert len(ext_items) == 2, "Both extra duplicate records must be preserved"
    for e in ext_items:
        assert e["status"] == "EXTRA_IN_GST"


def test_gstr3b_summary_contract_preserved(client, setup_tenants):
    token_a = setup_tenants["token_a"]
    biz_a = setup_tenants["biz_a"]

    res = client.get(
        "/gstr3b/summary",
        headers={"Authorization": f"Bearer {token_a}", "X-Business-ID": str(biz_a.id)},
    )
    assert res.status_code == 200
    data = res.json()

    # Exact expected response contract
    assert "business_id" in data
    assert "tax_period" in data
    assert "output_tax" in data
    assert "eligible_itc" in data
    assert "itc_reversed" in data
    assert "net_itc" in data
