import random
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import get_db
from main import app
from models.base import Base
from services.auth import hash_password, verify_password


# Isolated in-memory SQLite database for authentication tests
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


def test_hash_and_verify_password():
    pwd = "SecurePassword123!"
    hashed = hash_password(pwd)
    assert hashed.startswith("pbkdf2:sha256:100000$")
    assert hashed != pwd

    # Valid check
    is_valid, needs_rehash = verify_password(pwd, hashed)
    assert is_valid is True
    assert needs_rehash is False

    # Invalid check
    is_valid_wrong, _ = verify_password("WrongPassword!", hashed)
    assert is_valid_wrong is False


def test_legacy_password_verification():
    legacy_plain = "legacy_demo_pwd"
    is_valid, needs_rehash = verify_password(legacy_plain, legacy_plain)
    assert is_valid is True
    assert needs_rehash is True  # Signals it should be upgraded to PBKDF2


def test_unauthenticated_protected_endpoints(client):
    endpoints = [
        "/reconcile",
        "/gstr3b/summary",
        "/invoices",
        "/anomalies",
        "/reports/summary",
    ]
    for ep in endpoints:
        res = client.get(ep)
        assert res.status_code == 401, f"Expected 401 for {ep} without token, got {res.status_code}"


def test_auth_register_and_login_flow(client):
    email = "testuser_auth@gst.local"
    pwd = "TestSecretPassword123"
    gstin = "29AAAAA9999A1Z5"

    # Register
    reg_res = client.post(
        "/auth/register",
        json={
            "name": "Test Account",
            "email": email,
            "password": pwd,
            "business_name": "Test Enterprise",
            "gstin": gstin,
        },
    )
    # 201 Created or 400 if rerun
    if reg_res.status_code == 201:
        data = reg_res.json()
        assert "access_token" in data
        assert data["user"]["email"] == email
        assert len(data["businesses"]) >= 1

    # Login
    login_res = client.post(
        "/auth/login",
        json={"email": email, "password": pwd},
    )
    assert login_res.status_code == 200
    login_data = login_res.json()
    token = login_data["access_token"]
    assert token

    # Test /auth/me
    me_res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    assert me_res.json()["user"]["email"] == email


def test_multi_tenancy_cross_business_forbidden(client):
    # Register User A
    user_a_email = "tenant_a@gst.local"
    res_a = client.post(
        "/auth/register",
        json={
            "name": "Tenant A",
            "email": user_a_email,
            "password": "PasswordA123",
            "business_name": "Business A",
            "gstin": "29BBBBB8888B1Z5",
        },
    )
    if res_a.status_code != 201:
        res_a = client.post("/auth/login", json={"email": user_a_email, "password": "PasswordA123"})
    token_a = res_a.json()["access_token"]
    biz_a_id = res_a.json()["businesses"][0]["id"]

    # Register User B
    user_b_email = "tenant_b@gst.local"
    res_b = client.post(
        "/auth/register",
        json={
            "name": "Tenant B",
            "email": user_b_email,
            "password": "PasswordB123",
            "business_name": "Business B",
            "gstin": "29CCCCC7777C1Z5",
        },
    )
    if res_b.status_code != 201:
        res_b = client.post("/auth/login", json={"email": user_b_email, "password": "PasswordB123"})
    token_b = res_b.json()["access_token"]
    biz_b_id = res_b.json()["businesses"][0]["id"]

    # User A tries to request data using Business B's ID -> must be 403 Forbidden!
    hack_res = client.get(
        "/invoices",
        headers={
            "Authorization": f"Bearer {token_a}",
            "X-Business-ID": str(biz_b_id),
        },
    )
    assert hack_res.status_code == 403, f"Expected 403 Forbidden on cross-tenant access, got {hack_res.status_code}"
    assert "Forbidden" in hack_res.json()["detail"]

    # User B tries to request data using Business A's ID -> must be 403 Forbidden!
    hack_res_b = client.get(
        "/reconcile",
        headers={
            "Authorization": f"Bearer {token_b}",
            "X-Business-ID": str(biz_a_id),
        },
    )
    assert hack_res_b.status_code == 403


def test_duplicate_gstin_registration_returns_409(client):
    """
    Ensure registering an account with a GSTIN already owned by another enterprise
    is rejected with HTTP 409 Conflict, never silently assigning the existing business.
    """
    random_digits = f"{random.randint(1000, 9999)}"
    # Structurally valid 15-char Indian GSTIN shared by both registration attempts
    shared_gstin = f"29DDDDD{random_digits}A1Z5"
    user1_email = f"gstin_owner_1_{uuid.uuid4().hex[:6]}@gst.local"
    user2_email = f"gstin_owner_2_{uuid.uuid4().hex[:6]}@gst.local"

    # 1. Register first enterprise
    res1 = client.post(
        "/auth/register",
        json={
            "name": "First Owner",
            "email": user1_email,
            "password": "Password123!",
            "business_name": "First Enterprise Ltd",
            "gstin": shared_gstin,
        },
    )
    assert res1.status_code == 201
    assert res1.json()["businesses"][0]["gstin"] == shared_gstin

    # 2. Attempt to register second account with same GSTIN -> must return HTTP 409 Conflict
    res2 = client.post(
        "/auth/register",
        json={
            "name": "Second Claimant",
            "email": user2_email,
            "password": "Password456!",
            "business_name": "Second Enterprise Ltd",
            "gstin": shared_gstin,
        },
    )
    assert res2.status_code == 409, f"Expected 409 Conflict for duplicate GSTIN, got {res2.status_code}"
    assert "already registered to another enterprise account" in res2.json()["detail"]

    # 3. Verify user2 was rolled back and does not exist / cannot log in
    login_res = client.post(
        "/auth/login",
        json={"email": user2_email, "password": "Password456!"},
    )
    assert login_res.status_code == 401


def test_add_business_duplicate_gstin_returns_409(client):
    """
    Ensure adding an existing business GSTIN owned by another account returns HTTP 409.
    """
    digits_a = f"{random.randint(1000, 9999)}"
    digits_b = f"{random.randint(1000, 9999)}"
    biz_gstin = f"29EEEEE{digits_a}A1Z5"
    user_a_email = f"alpha_{uuid.uuid4().hex[:6]}@gst.local"
    user_b_email = f"beta_{uuid.uuid4().hex[:6]}@gst.local"

    res_a = client.post(
        "/auth/register",
        json={
            "name": "Enterprise Alpha",
            "email": user_a_email,
            "password": "PasswordAlpha123",
            "business_name": "Alpha Corp",
            "gstin": biz_gstin,
        },
    )
    assert res_a.status_code == 201

    res_b = client.post(
        "/auth/register",
        json={
            "name": "Enterprise Beta",
            "email": user_b_email,
            "password": "PasswordBeta123",
            "business_name": "Beta Corp",
            "gstin": f"29FFFFF{digits_b}B1Z6",
        },
    )
    assert res_b.status_code == 201
    token_b = res_b.json()["access_token"]

    # Beta attempts to link Alpha's GSTIN to Beta's account
    link_res = client.post(
        "/auth/businesses",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"name": "Alpha Stolen", "gstin": biz_gstin},
    )
    assert link_res.status_code == 409
    assert "already registered to another enterprise account" in link_res.json()["detail"]


def test_no_insecure_demo_password_bypass_in_verification():
    """
    Ensure no cross-password collisions or bypasses exist.
    A hashed real password cannot be accessed with Demo@123, password123, or changeme.
    """
    real_password = "SecretEnterprisePassword2026!"
    hashed = hash_password(real_password)

    # Legitimate password matches
    is_valid, needs_rehash = verify_password(real_password, hashed)
    assert is_valid is True
    assert needs_rehash is False

    # Insecure bypass passwords must FAIL
    for bypass_attempt in ("Demo@123", "password123", "changeme", "RandomPass"):
        valid, rehash = verify_password(bypass_attempt, hashed)
        assert valid is False
        assert rehash is False
