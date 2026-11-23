"""
Tests for the GST Simulator endpoints and MockGstAdapter.

Covers all 15 required test scenarios:
 1.  GST simulator status endpoint
 2.  Valid GSTIN format
 3.  Invalid GSTIN format
 4.  GSTIN present in demo fixtures
 5.  GSTR-1 retrieval
 6.  GSTR-2A retrieval
 7.  GSTR-2B retrieval
 8.  GSTR-3B retrieval
 9.  Correct tax-period filtering
10.  Empty period response (no data for requested period)
11.  Invalid period rejection
12.  Counterparty GSTIN filtering
13.  Missing CSV file behaviour (adapter-level)
14.  Authentication (unauthenticated request returns 401)
15.  Business isolation (another user cannot access a foreign business's endpoint)

Uses in-memory SQLite with dependency override â€” does NOT modify actual CSV fixtures.
Temporary CSV fixtures are written to a tmp directory for missing-file tests.
"""

from __future__ import annotations

import os
import tempfile
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import get_db
from main import app
from models.base import Base
from models.models import Business, Invoice, User
from services.auth import create_access_token
from services.gst_api_adapter import MockGstAdapter, validate_gstin_format

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# In-memory test database setup
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
    """Create a user + business and return auth helpers."""
    session = TestingSessionLocal()
    user = User(name="GST Test User", email="gst_test@test.local", password="hashed")
    session.add(user)
    session.flush()
    biz = Business(name="GST Test Enterprise", gstin="29AAAAA1111A1Z5", user_id=user.id)
    session.add(biz)
    session.commit()
    token = create_access_token(user_id=user.id, email=user.email)
    headers = {"Authorization": f"Bearer {token}", "X-Business-ID": str(biz.id)}
    return {"user": user, "biz": biz, "token": token, "headers": headers, "session": session}


@pytest.fixture
def setup_other_user_biz(client):
    """Create a *different* user + business for isolation tests."""
    session = TestingSessionLocal()
    user = User(name="Other User", email="other_gst@test.local", password="hashed2")
    session.add(user)
    session.flush()
    biz = Business(name="Other Enterprise", gstin="27BBBBB2222B2Z6", user_id=user.id)
    session.add(biz)
    session.commit()
    token = create_access_token(user_id=user.id, email=user.email)
    headers = {"Authorization": f"Bearer {token}", "X-Business-ID": str(biz.id)}
    return {"user": user, "biz": biz, "token": token, "headers": headers, "session": session}


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# 1. GST Simulator Status
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_gst_status_returns_demo_declaration(client, setup_user_biz):
    """Status endpoint must clearly declare demo/mock mode."""
    res = client.get("/gst/status", headers=setup_user_biz["headers"])
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["is_mock_data"] is True
    assert data["data_source"] == "synthetic_csv"
    assert data["provider"] == "mock"
    assert data["demo_mode"] is True
    assert "note" in data
    assert "DEMO MODE" in data["note"]
    assert data["live_integration_status"] == "not_configured"


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# 2 & 3. GSTIN Format Validation (unit-level, no HTTP)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@pytest.mark.parametrize("gstin,expected", [
    ("29AAAAA1111A1Z5", True),    # canonical demo format
    ("27BBBBB2222B2Z6", True),    # another valid structure
    ("29ABCDE1234F1Z5", True),    # fixture GSTIN
    ("29PQRST1234A1Z1", True),    # from gstr2a fixture
    ("INVALIDGSTIN123", False),   # too short / wrong format
    ("00AAAAA1111A1Z5", False),   # state code 00 is invalid
    ("29aaaaa1111a1z5", False),   # lowercase â€” pattern requires uppercase
    ("", False),
    ("123", False),
    ("29AAAAA1111A1ZZ", True),    # 15 chars: chk=Z is in [0-9A-Z] -> structurally valid
])
def test_gstin_format_validation(gstin, expected):
    assert validate_gstin_format(gstin) == expected, f"Expected {expected} for GSTIN '{gstin}'"


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# 2. Valid GSTIN format via API
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_gstin_verify_valid_format(client, setup_user_biz):
    res = client.post(
        "/gst/gstin/verify",
        json={"gstin": "29AAAAA1111A1Z5"},
        headers=setup_user_biz["headers"],
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["format_valid"] is True
    assert data["gstn_verified"] is False          # MUST always be false
    assert data["is_mock_data"] is True
    assert "disclaimer" in data


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# 3. Invalid GSTIN format via API
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_gstin_verify_invalid_format(client, setup_user_biz):
    res = client.post(
        "/gst/gstin/verify",
        json={"gstin": "BADINVALIDGSTIN"},
        headers=setup_user_biz["headers"],
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["format_valid"] is False
    assert data["gstn_verified"] is False
    assert data["is_mock_data"] is True


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# 4. GSTIN present in demo fixtures
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_gstin_found_in_demo_fixtures(client, setup_user_biz):
    """GSTINs from gstr1.csv should be reported as found in fixtures."""
    # 29ABCDE1234F1Z5 appears in data/gstr1.csv
    res = client.post(
        "/gst/gstin/verify",
        json={"gstin": "29ABCDE1234F1Z5"},
        headers=setup_user_biz["headers"],
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["format_valid"] is True
    assert data["found_in_demo_fixtures"] is True
    assert len(data["fixture_files_containing_gstin"]) > 0


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# 5. GSTR-1 Retrieval
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_gstr1_retrieval_returns_records(client, setup_user_biz):
    res = client.get(
        "/gst/gstr1?tax_period=2026-07",
        headers=setup_user_biz["headers"],
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["return_type"] == "GSTR-1"
    assert data["tax_period"] == "2026-07"
    assert data["is_mock_data"] is True
    assert data["data_source"] == "synthetic_csv"
    assert data["record_count"] >= 0
    assert isinstance(data["records"], list)
    assert "disclaimer" in data
    # All records must be labelled as mock
    for rec in data["records"]:
        assert rec["is_mock_data"] is True
        assert rec["source"] == "gstr1_csv"


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# 6. GSTR-2A Retrieval
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_gstr2a_retrieval_returns_records(client, setup_user_biz):
    res = client.get(
        "/gst/gstr2a?tax_period=2026-07",
        headers=setup_user_biz["headers"],
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["return_type"] == "GSTR-2A"
    assert data["is_mock_data"] is True
    assert isinstance(data["records"], list)
    for rec in data["records"]:
        assert rec["source"] == "gstr2a_csv"


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# 7. GSTR-2B Retrieval
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_gstr2b_retrieval_returns_records(client, setup_user_biz):
    res = client.get(
        "/gst/gstr2b?tax_period=2026-07",
        headers=setup_user_biz["headers"],
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["return_type"] == "GSTR-2B"
    assert data["is_mock_data"] is True
    assert isinstance(data["records"], list)
    for rec in data["records"]:
        assert rec["source"] == "gstr2b_csv"


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# 8. GSTR-3B Retrieval
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_gstr3b_retrieval_returns_summary(client, setup_user_biz):
    res = client.get(
        "/gst/gstr3b?tax_period=2026-07",
        headers=setup_user_biz["headers"],
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["return_type"] == "GSTR-3B"
    assert data["is_mock_data"] is True
    summary = data["summary"]
    assert summary["found"] is True
    for field in ("output_tax", "eligible_itc", "itc_reversed", "net_itc"):
        assert field in summary, f"Missing '{field}' in GSTR-3B summary"
        assert summary[field] is not None


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# 9. Correct tax-period filtering (adapter unit test)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_adapter_period_filtering_isolates_correct_month():
    """Adapter must return only records matching the requested period."""
    adapter = MockGstAdapter()
    records = adapter.get_gstr1(gstin="29AAAAA1111A1Z5", tax_period="2026-07")
    for rec in records:
        assert rec["invoice_date"].startswith("2026-07"), (
            f"Record with date {rec['invoice_date']} leaked into 2026-07 response"
        )


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# 10. Empty period response (no data for requested period)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_gstr3b_empty_response_for_missing_period(client, setup_user_biz):
    """Requesting a period with no data must return found=false, not substitute another month."""
    res = client.get(
        "/gst/gstr3b?tax_period=2020-01",
        headers=setup_user_biz["headers"],
    )
    assert res.status_code == 200, res.text
    data = res.json()
    summary = data["summary"]
    assert summary["found"] is False
    assert summary["output_tax"] is None
    assert "note" in summary


def test_gstr1_empty_for_period_with_no_records(client, setup_user_biz):
    """GSTR-1 for a period with no data should return 0 records, not error."""
    res = client.get(
        "/gst/gstr1?tax_period=2020-01",
        headers=setup_user_biz["headers"],
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["record_count"] == 0
    assert data["records"] == []


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# 11. Invalid period rejection
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@pytest.mark.parametrize("bad_period,expected_status", [
    ("072026", 422),         # MMYYYY format â€” not accepted
    ("2026-13", 422),        # month 13 is invalid
    ("2026-00", 422),        # month 00 is invalid
    ("26-07", 422),          # 2-digit year
    ("", 422),               # empty string â€” FastAPI will catch missing param
    ("not-a-period", 422),
])
def test_invalid_tax_period_rejected(client, setup_user_biz, bad_period, expected_status):
    # For empty string, omit the parameter entirely to get a 422
    if bad_period == "":
        res = client.get("/gst/gstr1", headers=setup_user_biz["headers"])
    else:
        res = client.get(f"/gst/gstr1?tax_period={bad_period}", headers=setup_user_biz["headers"])
    assert res.status_code in (400, 422), (
        f"Expected 400/422 for period '{bad_period}', got {res.status_code}: {res.text}"
    )


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# 12. Counterparty GSTIN filtering
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_counterparty_gstin_filter_returns_only_matching_records(client, setup_user_biz):
    """Filtering by counterparty_gstin must exclude non-matching records."""
    # 29ABCDE1234F1Z5 appears in gstr1.csv
    target_gstin = "29ABCDE1234F1Z5"
    res = client.get(
        f"/gst/gstr1?tax_period=2026-07&counterparty_gstin={target_gstin}",
        headers=setup_user_biz["headers"],
    )
    assert res.status_code == 200, res.text
    data = res.json()
    for rec in data["records"]:
        assert rec["gstin"].upper() == target_gstin.upper(), (
            f"Filter leaked record with GSTIN {rec['gstin']}"
        )


def test_counterparty_gstin_filter_nonexistent_gstin_returns_empty(client, setup_user_biz):
    res = client.get(
        "/gst/gstr1?tax_period=2026-07&counterparty_gstin=29ZZZZZ9999Z9Z9",
        headers=setup_user_biz["headers"],
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["record_count"] == 0
    assert data["records"] == []


def test_counterparty_gstin_filter_for_gstr2a(client, setup_user_biz):
    """GSTR-2A uses supplier_gstin column for filtering."""
    target = "29PQRST1234A1Z1"
    res = client.get(
        f"/gst/gstr2a?tax_period=2026-07&counterparty_gstin={target}",
        headers=setup_user_biz["headers"],
    )
    assert res.status_code == 200, res.text
    data = res.json()
    for rec in data["records"]:
        assert rec["gstin"].upper() == target.upper()


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# 13. Missing CSV file behaviour (adapter-level)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_missing_csv_raises_service_unavailable(client, setup_user_biz):
    """If a CSV fixture is missing the endpoint must return 503, not 500."""
    # Patch _DATA to a temp dir that doesn't have the files
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("routers.gst._DATA", Path(tmpdir)):
            with patch("services.gst_api_adapter._DATA", Path(tmpdir)):
                res = client.get(
                    "/gst/gstr1?tax_period=2026-07",
                    headers=setup_user_biz["headers"],
                )
    assert res.status_code == 503, f"Expected 503 for missing CSV, got {res.status_code}: {res.text}"


def test_adapter_raises_file_not_found_for_missing_csv():
    """MockGstAdapter.get_gstr1 must raise FileNotFoundError when CSV is absent."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("services.gst_api_adapter._DATA", Path(tmpdir)):
            adapter = MockGstAdapter()
            with pytest.raises(FileNotFoundError):
                adapter.get_gstr1(gstin="29AAAAA1111A1Z5", tax_period="2026-07")


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# 14. Authentication (unauthenticated â†’ 401)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@pytest.mark.parametrize("endpoint", [
    "/gst/status",
    "/gst/gstr1?tax_period=2026-07",
    "/gst/gstr2a?tax_period=2026-07",
    "/gst/gstr2b?tax_period=2026-07",
    "/gst/gstr3b?tax_period=2026-07",
])
def test_gst_endpoints_require_authentication(client, endpoint):
    res = client.get(endpoint)
    assert res.status_code == 401, (
        f"Expected 401 for unauthenticated {endpoint}, got {res.status_code}"
    )


def test_gstin_verify_requires_authentication(client):
    res = client.post("/gst/gstin/verify", json={"gstin": "29AAAAA1111A1Z5"})
    assert res.status_code == 401, f"Expected 401, got {res.status_code}"


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# 15. Business isolation
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_business_isolation_cross_tenant_forbidden(client, setup_user_biz, setup_other_user_biz):
    """
    User A's token with User B's business ID must be rejected with 403.
    The global synthetic CSV fixtures are not attributed to any specific business;
    but the auth layer must still prevent cross-tenant access.
    """
    user_a_token = setup_user_biz["token"]
    biz_b_id = setup_other_user_biz["biz"].id

    res = client.get(
        "/gst/status",
        headers={
            "Authorization": f"Bearer {user_a_token}",
            "X-Business-ID": str(biz_b_id),
        },
    )
    assert res.status_code == 403, (
        f"Expected 403 for cross-tenant access, got {res.status_code}: {res.text}"
    )


def test_business_isolation_own_business_succeeds(client, setup_user_biz):
    """Each user can only access their own business's resources."""
    res = client.get("/gst/status", headers=setup_user_biz["headers"])
    assert res.status_code == 200
    data = res.json()
    assert data["business_id"] == setup_user_biz["biz"].id


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Extra: response labels consistency
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_all_gst_responses_labelled_as_mock(client, setup_user_biz):
    """Every /gst/* data endpoint must include is_mock_data=true."""
    endpoints = [
        "/gst/gstr1?tax_period=2026-07",
        "/gst/gstr2a?tax_period=2026-07",
        "/gst/gstr2b?tax_period=2026-07",
        "/gst/gstr3b?tax_period=2026-07",
        "/gst/status",
    ]
    for ep in endpoints:
        res = client.get(ep, headers=setup_user_biz["headers"])
        assert res.status_code == 200, f"{ep} â†’ {res.status_code}: {res.text}"
        data = res.json()
        assert data.get("is_mock_data") is True, f"{ep} missing is_mock_data=true"
        assert data.get("data_source") == "synthetic_csv", f"{ep} wrong data_source"


def test_gstin_verify_always_returns_false_gstn_verified(client, setup_user_biz):
    """gstn_verified must ALWAYS be false — we never claim live portal verification."""
    for gstin in ("29AAAAA1111A1Z5", "29ABCDE1234F1Z5", "BADINVALIDGSTIN"):
        body = {"gstin": gstin} if len(gstin) == 15 else None
        if body is None:
            continue
        res = client.post("/gst/gstin/verify", json=body, headers=setup_user_biz["headers"])
        if res.status_code == 200:
            assert res.json()["gstn_verified"] is False, f"gstn_verified was not false for {gstin}"


# ─────────────────────────────────────────────────────────────
# PHASE 3: GST Return Import into Reconciliation Ledger Tests
# ─────────────────────────────────────────────────────────────

def test_import_preview_does_not_modify_db(client, setup_user_biz):
    """POST /gst/import/preview must report ready counts and NOT insert invoices."""
    db = TestingSessionLocal()
    initial_count = db.scalar(select(Invoice).where(Invoice.business_id == setup_user_biz["biz"].id))
    assert initial_count is None or initial_count == 0
    db.close()

    res = client.post(
        "/gst/import/preview",
        json={"return_type": "gstr1", "tax_period": "2026-07"},
        headers=setup_user_biz["headers"],
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["return_type"] == "GSTR1"
    assert data["source"] == "gstr1"
    assert data["tax_period"] == "2026-07"
    assert data["total_records"] == 15
    assert data["ready_to_import"] == 15
    assert data["duplicate_count"] == 0
    assert data["target_business_id"] == setup_user_biz["biz"].id
    assert len(data["preview_records"]) > 0

    # Verify no database side effects
    db = TestingSessionLocal()
    count_after = db.query(Invoice).filter(Invoice.business_id == setup_user_biz["biz"].id).count()
    db.close()
    assert count_after == 0, "Preview endpoint must never insert records into the database"


def test_import_gstr1_successful_insert(client, setup_user_biz):
    """POST /gst/import with gstr1 inserts invoices tagged with source='gstr1'."""
    res = client.post(
        "/gst/import",
        json={"return_type": "gstr1", "tax_period": "2026-07"},
        headers=setup_user_biz["headers"],
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["status"] == "success"
    assert data["source"] == "gstr1"
    assert data["imported_count"] == 15
    assert data["duplicate_count"] == 0
    assert data["rejected_count"] == 0
    assert data["business_id"] == setup_user_biz["biz"].id

    db = TestingSessionLocal()
    invoices = db.query(Invoice).filter(
        Invoice.business_id == setup_user_biz["biz"].id,
        Invoice.source == "gstr1",
    ).all()
    db.close()
    assert len(invoices) == 15
    assert all(inv.source == "gstr1" for inv in invoices)
    assert all(inv.business_id == setup_user_biz["biz"].id for inv in invoices)


def test_repeated_import_idempotent_duplicates_skipped(client, setup_user_biz):
    """Calling /gst/import a second time skips all previously imported invoices."""
    # First import
    res1 = client.post(
        "/gst/import",
        json={"return_type": "gstr1", "tax_period": "2026-07"},
        headers=setup_user_biz["headers"],
    )
    assert res1.status_code == 200
    first_imported = res1.json()["imported_count"]

    # Second import (same return and period)
    res2 = client.post(
        "/gst/import",
        json={"return_type": "gstr1", "tax_period": "2026-07"},
        headers=setup_user_biz["headers"],
    )
    assert res2.status_code == 200, res2.text
    data2 = res2.json()
    assert data2["imported_count"] == 0, "Subsequent import must insert 0 duplicates"
    assert data2["duplicate_count"] == first_imported, "All records must be identified as duplicates"

    # Preview also reflects duplicates
    prev = client.post(
        "/gst/import/preview",
        json={"return_type": "gstr1", "tax_period": "2026-07"},
        headers=setup_user_biz["headers"],
    )
    assert prev.status_code == 200
    assert prev.json()["ready_to_import"] == 0
    assert prev.json()["duplicate_count"] == first_imported


def test_import_gstr2a_source_mapping(client, setup_user_biz):
    """POST /gst/import with gstr2a inserts invoices tagged with source='gstr2a'."""
    res = client.post(
        "/gst/import",
        json={"return_type": "gstr2a", "tax_period": "2026-07"},
        headers=setup_user_biz["headers"],
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["source"] == "gstr2a"
    assert data["imported_count"] == 16

    db = TestingSessionLocal()
    invoices = db.query(Invoice).filter(
        Invoice.business_id == setup_user_biz["biz"].id,
        Invoice.source == "gstr2a",
    ).all()
    db.close()
    assert len(invoices) == 16


def test_import_gstr2b_source_mapping(client, setup_user_biz):
    """POST /gst/import with gstr2b inserts invoices tagged with source='gstr2b'."""
    res = client.post(
        "/gst/import",
        json={"return_type": "gstr2b", "tax_period": "2026-07"},
        headers=setup_user_biz["headers"],
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["source"] == "gstr2b"
    assert data["imported_count"] == 15

    db = TestingSessionLocal()
    invoices = db.query(Invoice).filter(
        Invoice.business_id == setup_user_biz["biz"].id,
        Invoice.source == "gstr2b",
    ).all()
    db.close()
    assert len(invoices) == 15


def test_import_gstr3b_rejected(client, setup_user_biz):
    """GSTR-3B monthly summary must be rejected for invoice table import."""
    res = client.post(
        "/gst/import",
        json={"return_type": "gstr3b", "tax_period": "2026-07"},
        headers=setup_user_biz["headers"],
    )
    assert res.status_code == 400
    assert "summary return" in res.json()["detail"].lower()


def test_preview_gstr3b_rejected(client, setup_user_biz):
    """Preview for GSTR-3B must be rejected with 400."""
    res = client.post(
        "/gst/import/preview",
        json={"return_type": "gstr3b", "tax_period": "2026-07"},
        headers=setup_user_biz["headers"],
    )
    assert res.status_code == 400
    assert "summary return" in res.json()["detail"].lower()


def test_import_cross_business_isolation(client, setup_user_biz, setup_other_user_biz):
    """Imported invoices belong strictly to current_business and never leak to others."""
    # User A imports GSTR-1
    res_a = client.post(
        "/gst/import",
        json={"return_type": "gstr1", "tax_period": "2026-07"},
        headers=setup_user_biz["headers"],
    )
    assert res_a.status_code == 200
    biz_a_id = setup_user_biz["biz"].id

    # User B imports GSTR-1
    res_b = client.post(
        "/gst/import",
        json={"return_type": "gstr1", "tax_period": "2026-07"},
        headers=setup_other_user_biz["headers"],
    )
    assert res_b.status_code == 200
    biz_b_id = setup_other_user_biz["biz"].id
    assert res_b.json()["business_id"] == biz_b_id
    assert res_b.json()["imported_count"] == 15  # Not a duplicate for User B!

    db = TestingSessionLocal()
    count_a = db.query(Invoice).filter(Invoice.business_id == biz_a_id, Invoice.source == "gstr1").count()
    count_b = db.query(Invoice).filter(Invoice.business_id == biz_b_id, Invoice.source == "gstr1").count()
    db.close()
    assert count_a == 15
    assert count_b == 15


def test_import_invalid_tax_period_rejected(client, setup_user_biz):
    """Invalid tax periods return 422 for both preview and import."""
    for bad_period in ("2026-13", "072026", "invalid-period"):
        res_prev = client.post(
            "/gst/import/preview",
            json={"return_type": "gstr1", "tax_period": bad_period},
            headers=setup_user_biz["headers"],
        )
        assert res_prev.status_code == 422

        res_imp = client.post(
            "/gst/import",
            json={"return_type": "gstr1", "tax_period": bad_period},
            headers=setup_user_biz["headers"],
        )
        assert res_imp.status_code == 422


def test_import_server_fixtures_used_ignores_client_body(client, setup_user_biz):
    """Backend re-fetches records server-side; arbitrary client rows are ignored."""
    rogue_payload = {
        "return_type": "gstr1",
        "tax_period": "2026-07",
        "records": [
            {"invoice_no": "ROGUE_999", "taxable_value": 999999, "gst_amount": 99999}
        ],
    }
    res = client.post("/gst/import", json=rogue_payload, headers=setup_user_biz["headers"])
    assert res.status_code == 200

    db = TestingSessionLocal()
    rogue_inv = db.scalar(select(Invoice).where(Invoice.invoice_no == "ROGUE_999"))
    db.close()
    assert rogue_inv is None, "Backend must ignore rogue client-supplied invoice records"


def test_import_transaction_rollback_on_error(client, setup_user_biz):
    """Database exception causes rollback so 0 partial records remain."""
    db = TestingSessionLocal()
    count_before = db.query(Invoice).filter(Invoice.business_id == setup_user_biz["biz"].id).count()
    db.close()

    with patch("sqlalchemy.orm.Session.commit", side_effect=RuntimeError("Simulated DB Crash")):
        res = client.post(
            "/gst/import",
            json={"return_type": "gstr1", "tax_period": "2026-07"},
            headers=setup_user_biz["headers"],
        )
        assert res.status_code == 500
        assert "Database transaction failed" in res.json()["detail"]

    db = TestingSessionLocal()
    count_after = db.query(Invoice).filter(Invoice.business_id == setup_user_biz["biz"].id).count()
    db.close()
    assert count_after == count_before, "Failed transaction must roll back without partial writes"

