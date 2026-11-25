"""Migration and seed safeguards exercised only with disposable local databases."""

from pathlib import Path
from types import SimpleNamespace
from io import StringIO

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, inspect

from import_data import ensure_isolated_demo_seed_allowed
from migration_safety import PRODUCTION_MIGRATION_FLAG
from models import models as _registered_models  # noqa: F401
from models.base import Base


BACKEND_DIR = Path(__file__).resolve().parents[1]


def _config(connection=None):
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    if connection is not None:
        config.attributes["connection"] = connection
    return config


def _offline_config(url):
    config = Config(str(BACKEND_DIR / "alembic.ini"), output_buffer=StringIO())
    config.set_main_option("sqlalchemy.url", url)
    return config


def test_production_migration_guard_blocks_normal_cli_before_connecting(monkeypatch, tmp_path):
    target_file = tmp_path / "must_not_be_created.sqlite"
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv(PRODUCTION_MIGRATION_FLAG, raising=False)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{target_file}")

    with pytest.raises(RuntimeError, match="explicit RECONCILEPRO_ALLOW_PRODUCTION_MIGRATION=true"):
        command.upgrade(_config(), "head")

    assert not target_file.exists()


def test_production_migration_guard_cannot_be_bypassed_with_injected_connection(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv(PRODUCTION_MIGRATION_FLAG, raising=False)
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.connect() as connection:
            with pytest.raises(RuntimeError, match="explicit RECONCILEPRO_ALLOW_PRODUCTION_MIGRATION=true"):
                command.upgrade(_config(connection), "head")
            assert "alembic_version" not in inspect(connection).get_table_names()
            assert "users" not in inspect(connection).get_table_names()
    finally:
        engine.dispose()


def test_production_migration_guard_requires_postgresql_even_with_flag(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.setenv(PRODUCTION_MIGRATION_FLAG, "true")
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.connect() as connection:
            with pytest.raises(RuntimeError, match="Production migrations require a PostgreSQL connection"):
                command.upgrade(_config(connection), "head")
            assert "alembic_version" not in inspect(connection).get_table_names()
    finally:
        engine.dispose()


def test_production_offline_sql_generation_requires_authorization(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv(PRODUCTION_MIGRATION_FLAG, raising=False)

    with pytest.raises(RuntimeError, match="explicit RECONCILEPRO_ALLOW_PRODUCTION_MIGRATION=true"):
        command.upgrade(
            _offline_config("postgresql+psycopg://offline.invalid/reconcilepro"),
            "head",
            sql=True,
        )


def test_authorized_production_offline_generation_emits_postgresql_sql_without_connecting(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.setenv(PRODUCTION_MIGRATION_FLAG, "true")
    config = _offline_config("postgresql+psycopg://offline.invalid/reconcilepro")

    # An unreachable host is intentional: --sql must render SQL and must not connect.
    command.upgrade(config, "head", sql=True)
    rendered = config.output_buffer.getvalue()
    assert "CREATE TABLE users" in rendered
    assert "uq_invoices_active_business_source_invoice" in rendered


@pytest.mark.parametrize("environment", ["development", "test"])
def test_development_and_test_offline_sql_generation_needs_no_production_flag(monkeypatch, environment):
    monkeypatch.setenv("ENVIRONMENT", environment)
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv(PRODUCTION_MIGRATION_FLAG, raising=False)
    config = _offline_config("postgresql+psycopg://offline.invalid/reconcilepro")

    command.upgrade(config, "head", sql=True)
    assert "CREATE TABLE users" in config.output_buffer.getvalue()


def test_production_seed_is_refused_even_with_isolated_demo_flag(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("RECONCILEPRO_ISOLATED_DEMO_SEED", "true")
    engine = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

    with pytest.raises(RuntimeError, match="Production fixture seeding is disabled"):
        ensure_isolated_demo_seed_allowed(engine)


def test_isolated_demo_seed_requires_explicit_mode(monkeypatch, tmp_path):
    database_file = tmp_path / "isolated_demo.sqlite"
    database_url = f"sqlite:///{database_file}"
    engine = create_engine(database_url)
    try:
        Base.metadata.create_all(engine)
        monkeypatch.setenv("ENVIRONMENT", "test")
        monkeypatch.delenv("RENDER", raising=False)
        monkeypatch.delenv("RECONCILEPRO_ISOLATED_DEMO_SEED", raising=False)
        monkeypatch.setenv("DATABASE_URL", database_url)

        with pytest.raises(RuntimeError, match="requires RECONCILEPRO_ISOLATED_DEMO_SEED=true"):
            ensure_isolated_demo_seed_allowed(engine)
    finally:
        engine.dispose()


def test_isolated_demo_seed_accepts_only_empty_dedicated_sqlite(monkeypatch, tmp_path):
    database_file = tmp_path / "isolated_demo.sqlite"
    database_url = f"sqlite:///{database_file}"
    engine = create_engine(database_url)
    try:
        Base.metadata.create_all(engine)
        monkeypatch.setenv("ENVIRONMENT", "test")
        monkeypatch.delenv("RENDER", raising=False)
        monkeypatch.setenv("RECONCILEPRO_ISOLATED_DEMO_SEED", "true")
        monkeypatch.setenv("DATABASE_URL", database_url)

        ensure_isolated_demo_seed_allowed(engine)

        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO users (id, name, email, password) VALUES (1, 'Customer', 'customer@example.test', 'hash')"
            )
        with pytest.raises(RuntimeError, match="requires an empty database"):
            ensure_isolated_demo_seed_allowed(engine)
    finally:
        engine.dispose()


def test_isolated_demo_seed_rejects_non_sqlite_database(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("RECONCILEPRO_ISOLATED_DEMO_SEED", "true")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    engine = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

    with pytest.raises(RuntimeError, match="limited to SQLite"):
        ensure_isolated_demo_seed_allowed(engine)
