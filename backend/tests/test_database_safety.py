"""Regression coverage for production database startup and health behavior."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import database
from database import get_db
from main import app


def _set_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("RENDER", raising=False)


def test_production_without_database_url_fails_clearly(monkeypatch):
    _set_production(monkeypatch)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="DATABASE_URL is required in production"):
        database._build_engine(None)


def test_production_rejects_sqlite_database_url(monkeypatch):
    _set_production(monkeypatch)

    with pytest.raises(RuntimeError, match="must use PostgreSQL"):
        database._build_engine("sqlite:///:memory:")


def test_production_invalid_database_url_fails_without_echoing_it(monkeypatch):
    _set_production(monkeypatch)
    invalid_url = "postgresql://private-user:private-password@private-host/db with spaces"

    with pytest.raises(RuntimeError, match="Unable to initialize the required production PostgreSQL") as err:
        database._build_engine(invalid_url)

    assert "private-password" not in str(err.value)
    assert "private-host" not in str(err.value)


def test_production_postgresql_connection_failure_never_falls_back(monkeypatch, caplog):
    _set_production(monkeypatch)
    calls = []

    def fail_postgresql(url, **kwargs):
        calls.append(url.get_backend_name())
        raise OSError("connection failed at secret-user:secret-password@private-host")

    monkeypatch.setattr(database, "create_engine", fail_postgresql)
    with pytest.raises(RuntimeError, match="Unable to initialize the required production PostgreSQL") as err:
        database._build_engine("postgresql+psycopg://secret-user:secret-password@private-host/db")

    assert calls == ["postgresql"]
    assert "secret-password" not in str(err.value)
    assert "secret-password" not in caplog.text


def test_explicit_development_sqlite_configuration_works(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("RENDER", raising=False)

    configured_engine = database._build_engine("sqlite:///:memory:")
    try:
        assert configured_engine.dialect.name == "sqlite"
    finally:
        configured_engine.dispose()


def test_healthy_configured_postgresql_passes_production_health_check(monkeypatch):
    _set_production(monkeypatch)

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, _statement):
            return None

    class FakeEngine:
        dialect = SimpleNamespace(name="postgresql")

        def connect(self):
            return FakeConnection()

        def dispose(self):
            pass

    monkeypatch.setattr(database, "create_engine", lambda *_args, **_kwargs: FakeEngine())
    configured_engine = database._build_engine(
        "postgresql+psycopg://user:password@db.example.invalid/reconcile"
    )
    assert configured_engine.dialect.name == "postgresql"

    class FakeSession:
        def get_bind(self):
            return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

        def execute(self, _statement):
            return None

    previous_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = lambda: FakeSession()
    try:
        response = TestClient(app).get("/health")
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override

    assert response.status_code == 200
    assert response.json()["database_dialect"] == "postgresql"
    assert "password" not in response.text


def test_pytest_global_database_is_isolated_sqlite():
    assert database.engine.dialect.name == "sqlite"
    assert database.engine.url.database in {None, "", ":memory:"}
