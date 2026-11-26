"""Regression coverage for runtime database selection and production fail-closed behavior."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import database
from database import get_db
from main import app


def _set_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("RENDER", raising=False)


def test_production_requires_app_database_url_even_if_admin_database_url_exists(monkeypatch):
    _set_production(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", "postgresql://admin:secret@db.invalid/app")
    monkeypatch.delenv("APP_DATABASE_URL", raising=False)

    assert database._select_runtime_database_url() == ""
    with pytest.raises(RuntimeError, match="APP_DATABASE_URL is required in production"):
        database._build_engine(None)


def test_development_keeps_database_url_compatibility(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("APP_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")

    assert database._select_runtime_database_url() == "sqlite:///:memory:"


def test_production_rejects_sqlite_app_database_url(monkeypatch):
    _set_production(monkeypatch)

    with pytest.raises(RuntimeError, match="must use PostgreSQL"):
        database._build_engine("sqlite:///:memory:")


def test_production_invalid_app_database_url_fails_without_echoing_it(monkeypatch):
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


def test_production_rejects_non_dedicated_connected_role(monkeypatch):
    _set_production(monkeypatch)

    class FakeResult:
        def one(self):
            return ("postgres", "postgres")

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, statement):
            if "current_user" in str(statement):
                return FakeResult()
            return None

    class FakeEngine:
        dialect = SimpleNamespace(name="postgresql")

        def connect(self):
            return FakeConnection()

        def dispose(self):
            self.disposed = True

    engine = FakeEngine()
    monkeypatch.setattr(database, "create_engine", lambda *_args, **_kwargs: engine)
    with pytest.raises(RuntimeError, match="dedicated reconcilepro_app role"):
        database._build_engine("postgresql+psycopg://postgres:password@db.invalid/app")
    assert engine.disposed


def test_healthy_configured_postgresql_passes_production_health_check(monkeypatch):
    _set_production(monkeypatch)

    class FakeResult:
        def one(self):
            return ("reconcilepro_app", "reconcilepro_app")

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, statement):
            return FakeResult() if "current_user" in str(statement) else None

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


def test_explicit_development_sqlite_configuration_works(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("RENDER", raising=False)

    configured_engine = database._build_engine("sqlite:///:memory:")
    try:
        assert configured_engine.dialect.name == "sqlite"
    finally:
        configured_engine.dispose()


def test_pytest_global_database_is_isolated_sqlite():
    assert database.engine.dialect.name == "sqlite"
    assert database.engine.url.database in {None, "", ":memory:"}
