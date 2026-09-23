import pytest
from fastapi.testclient import TestClient
from main import app
from services.auth import hash_password, verify_password


@pytest.fixture
def client():
    return TestClient(app)


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
