"""Explicit PostgreSQL-only release checks. Run only via the disposable Docker runner."""

from __future__ import annotations

import os
import sys
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor

import pytest
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import (
    Column, Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint,
    create_engine, event, inspect, select, text,
)
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session
from sqlalchemy.pool import NullPool


# Prevent application imports from consulting local .env files. The runner sets
# these values only in child processes and verifies the URL is loopback/test-only.
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ["ENVIRONMENT"] = "integration"
if "RENDER" in os.environ:
    raise RuntimeError("PostgreSQL integration tests refuse a Render environment.")
if os.getenv("RECONCILEPRO_PG_INTEGRATION") != "1":
    raise RuntimeError("Run these tests only through the disposable PostgreSQL PowerShell runner.")

_DATABASE_URL = os.environ.get("RECONCILEPRO_TEST_DATABASE_URL", "")
_url = make_url(_DATABASE_URL) if _DATABASE_URL else None
_run_id = os.getenv("RECONCILEPRO_PG_RUN_ID", "")
if (
    _url is None
    or _url.drivername != "postgresql+psycopg"
    or _url.host not in {"127.0.0.1", "localhost"}
    or _url.port is None
    or _url.username != "reconcilepro_test"
    or not _run_id
    or (_url.database or "") != f"reconcilepro_it_{_run_id}"
    or os.getenv("DATABASE_URL") != _DATABASE_URL
):
    raise RuntimeError("PostgreSQL integration tests require the runner's loopback-only disposable database.")

os.environ.setdefault("JWT_SECRET", "local-postgres-test-only-" + uuid4().hex)
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from database import SessionLocal, engine as application_engine  # noqa: E402
from main import app  # noqa: E402
from migration_safety import PRODUCTION_MIGRATION_FLAG  # noqa: E402
from models.models import Business, GSTR3BReturn, ImportBatch, ImportBatchItem, Invoice, User  # noqa: E402
from routers import gst as gst_routes  # noqa: E402
from schema_parity import stamp_verified_legacy_baseline, verify_legacy_schema  # noqa: E402
from services.auth import create_access_token, hash_password  # noqa: E402


def _alembic_config(connection=None, *, url=None, output_buffer=None):
    config = Config(str(BACKEND_DIR / "alembic.ini"), output_buffer=output_buffer)
    if connection is not None:
        config.attributes["connection"] = connection
    if url is not None:
        config.set_main_option("sqlalchemy.url", url)
    return config


def _legacy_models():
    """Independently redeclare the pre-Alembic ORM schema for adoption coverage."""
    class LegacyBase(DeclarativeBase):
        pass

    class LegacyUser(LegacyBase):
        __tablename__ = "users"
        id = Column(Integer, primary_key=True, index=True)
        name = Column(String(100), nullable=False)
        email = Column(String(150), unique=True, index=True, nullable=False)
        password = Column(String(255), nullable=False)

    class LegacyBusiness(LegacyBase):
        __tablename__ = "businesses"
        id = Column(Integer, primary_key=True, index=True)
        name = Column(String(150), nullable=False)
        gstin = Column(String(15), unique=True, index=True, nullable=False)
        user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    class LegacyInvoice(LegacyBase):
        __tablename__ = "invoices"
        id = Column(Integer, primary_key=True, index=True)
        invoice_no = Column(String(50), index=True, nullable=False)
        invoice_date = Column(Date, nullable=False)
        gstin = Column(String(15), nullable=False)
        taxable_value = Column(Float, nullable=False)
        gst_amount = Column(Float, nullable=False)
        source = Column(String(30), nullable=False)
        created_at = Column(DateTime, nullable=False)
        business_id = Column(Integer, ForeignKey("businesses.id"), nullable=False)

    class LegacyGSTR3BReturn(LegacyBase):
        __tablename__ = "gstr3b_returns"
        __table_args__ = (UniqueConstraint("business_id", "tax_period", name="uq_gstr3b_business_tax_period"),)
        id = Column(Integer, primary_key=True, index=True)
        business_id = Column(Integer, ForeignKey("businesses.id"), index=True, nullable=False)
        tax_period = Column(String(10), index=True, nullable=False)
        output_tax = Column(Float, default=0.0, nullable=False)
        eligible_itc = Column(Float, default=0.0, nullable=False)
        itc_reversed = Column(Float, default=0.0, nullable=False)
        net_itc = Column(Float, default=0.0, nullable=False)
        created_at = Column(DateTime, nullable=False)
        updated_at = Column(DateTime, nullable=False)

    return LegacyBase, LegacyUser, LegacyBusiness, LegacyInvoice, LegacyGSTR3BReturn


def _new_legacy_schema():
    schema = "pgit_" + uuid4().hex[:20]
    with application_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))

    legacy_engine = create_engine(_DATABASE_URL, poolclass=NullPool)

    @event.listens_for(legacy_engine, "connect")
    def set_schema(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute(f'SET search_path TO "{schema}"')
        cursor.close()

    models = _legacy_models()
    models[0].metadata.create_all(legacy_engine)
    with Session(legacy_engine) as session:
        user = models[1](name="Legacy User", email=f"legacy-{uuid4().hex}@example.test", password="hash")
        session.add(user)
        session.flush()
        business = models[2](name="Legacy Business", gstin="29ABCDE1234F1Z5", user_id=user.id)
        session.add(business)
        session.flush()
        session.add(models[3](
            invoice_no="LEGACY-PG-001", invoice_date=date(2026, 7, 5), gstin="29ABCDE1234F1Z5",
            taxable_value=100.0, gst_amount=18.0, source="sales_register",
            created_at=datetime(2026, 7, 5), business_id=business.id,
        ))
        session.add(models[4](
            business_id=business.id, tax_period="2026-07", output_tax=100.0,
            eligible_itc=40.0, itc_reversed=2.0, net_itc=38.0,
            created_at=datetime(2026, 7, 5), updated_at=datetime(2026, 7, 5),
        ))
        session.commit()

    return schema, legacy_engine, models


@pytest.fixture
def legacy_schema():
    schema, scoped_engine, models = _new_legacy_schema()
    try:
        yield schema, scoped_engine, models
    finally:
        scoped_engine.dispose()
        with application_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))


def test_fresh_alembic_schema_is_at_revision_0004():
    with application_engine.connect() as connection:
        heads = set(MigrationContext.configure(connection).get_current_heads())
        assert heads == {"0004_import_batch_rev_counts"}
        names = set(inspect(connection).get_table_names())
        assert {"users", "businesses", "invoices", "gstr3b_returns", "import_batches", "import_batch_items"} <= names
        invoice_indexes = inspect(connection).get_indexes("invoices")
        index = next(i for i in invoice_indexes if i["name"] == "uq_invoices_active_business_source_invoice")
        assert index["unique"] is True
        assert index["column_names"] == ["business_id", "source", "invoice_no"]
        index_definition = connection.execute(text(
            "SELECT indexdef FROM pg_indexes WHERE schemaname = current_schema() "
            "AND indexname = 'uq_invoices_active_business_source_invoice'"
        )).scalar_one()
        assert "WHERE (deleted_at IS NULL)" in index_definition or "WHERE deleted_at IS NULL" in index_definition
        batch_columns = {c["name"]: c for c in inspect(connection).get_columns("import_batches")}
        assert batch_columns["revised_rows"]["default"] == "0"


def test_independent_legacy_schema_parity_stamp_upgrade_preserves_rows(legacy_schema):
    _schema, scoped_engine, _models = legacy_schema
    with scoped_engine.connect() as connection:
        report = verify_legacy_schema(connection)
        assert report.matches, report.format()
        stamp_verified_legacy_baseline(connection)
        connection.commit()
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0001_core_schema"
        command.upgrade(_alembic_config(connection), "head")
        connection.commit()
        assert set(MigrationContext.configure(connection).get_current_heads()) == {"0004_import_batch_rev_counts"}
        assert connection.execute(text("SELECT COUNT(*) FROM users")).scalar_one() == 1
        assert connection.execute(text("SELECT invoice_no, import_batch_id, deleted_at FROM invoices")).one() == (
            "LEGACY-PG-001", None, None
        )
        assert connection.execute(text("SELECT tax_period, output_tax, import_batch_id FROM gstr3b_returns")).one() == (
            "2026-07", 100.0, None
        )
        assert {"import_batch_id", "deleted_at"} <= {
            column["name"] for column in inspect(connection).get_columns("invoices")
        }


def test_active_invoice_duplicates_abort_revision_0003_without_data_loss(legacy_schema):
    _schema, scoped_engine, _models = legacy_schema
    with scoped_engine.connect() as connection:
        # The independent ORM-built legacy schema has no batch uniqueness index.
        # Add a conflicting active invoice before proving its schema baseline.
        connection.execute(
            text(
                "INSERT INTO invoices "
                "(invoice_no, invoice_date, gstin, taxable_value, gst_amount, source, created_at, business_id) "
                "SELECT 'LEGACY-PG-001', DATE '2026-07-06', '29ABCDE1234F1Z5', 125.0, 22.5, "
                "'sales_register', TIMESTAMP '2026-07-06 00:00:00', id FROM businesses"
            )
        )
        before_rows = connection.execute(
            text(
                "SELECT id, invoice_no, invoice_date, gstin, taxable_value, gst_amount, source, created_at, business_id "
                "FROM invoices ORDER BY id"
            )
        ).all()
        assert len(before_rows) == 2
        assert before_rows[0].invoice_no == before_rows[1].invoice_no
        assert before_rows[0].source == before_rows[1].source
        assert before_rows[0].business_id == before_rows[1].business_id

        report = verify_legacy_schema(connection)
        assert report.matches, report.format()
        stamp_verified_legacy_baseline(connection)
        connection.commit()
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0001_core_schema"

        with pytest.raises(RuntimeError, match="Active invoice uniqueness migration aborted"):
            command.upgrade(_alembic_config(connection), "0003_active_invoice_uniqueness")

        after_rows = connection.execute(
            text(
                "SELECT id, invoice_no, invoice_date, gstin, taxable_value, gst_amount, source, created_at, business_id "
                "FROM invoices ORDER BY id"
            )
        ).all()
        assert after_rows == before_rows
        assert not any(
            index["name"] == "uq_invoices_active_business_source_invoice"
            for index in inspect(connection).get_indexes("invoices")
        )
        # The migration chain must not claim that the failed uniqueness
        # migration, or a later revision, was applied.
        current_revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert current_revision not in {"0003_active_invoice_uniqueness", "0004_import_batch_rev_counts"}


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("ALTER TABLE users ALTER COLUMN name SET DEFAULT 'mismatch'", "column users.name server default"),
        ("ALTER TABLE users ADD CONSTRAINT pgit_bad_check CHECK (id > 0)", "check constraint users: unexpected"),
        ('ALTER TABLE users ALTER COLUMN email TYPE VARCHAR(150) COLLATE "C"', "column users.email collation"),
        ("ALTER SEQUENCE users_id_seq INCREMENT BY 2", "sequence users.id configuration"),
    ],
)
def test_postgres_schema_parity_detects_definition_mismatches(legacy_schema, mutation, expected):
    _schema, scoped_engine, _models = legacy_schema
    with scoped_engine.begin() as connection:
        connection.execute(text(mutation))
    with scoped_engine.connect() as connection:
        report = verify_legacy_schema(connection)
        assert not report.matches
        assert expected in report.format()


def test_parity_refuses_missing_sequence_ownership_and_stamp(legacy_schema):
    _schema, scoped_engine, _models = legacy_schema
    with scoped_engine.begin() as connection:
        connection.execute(text("ALTER SEQUENCE users_id_seq OWNED BY NONE"))
    with scoped_engine.connect() as connection:
        report = verify_legacy_schema(connection)
        assert not report.matches
        assert "expected an owned PostgreSQL identity/serial sequence" in report.format()
        with pytest.raises(RuntimeError, match="Baseline stamp refused"):
            stamp_verified_legacy_baseline(connection)
        assert "alembic_version" not in inspect(connection).get_table_names()


def test_sequence_safety_detects_collision_without_advancing_sequence(legacy_schema):
    schema, scoped_engine, _models = legacy_schema
    with scoped_engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO users (id, name, email, password) VALUES (100, 'High ID', 'high-id@example.test', 'hash')"
        ))
        connection.execute(text("SELECT setval('users_id_seq', 1, true)"))
        before = connection.execute(text("SELECT last_value, is_called FROM users_id_seq")).one()
    with scoped_engine.connect() as connection:
        report = verify_legacy_schema(connection)
        assert not report.matches
        assert "sequence users.id state: next value 2 could collide" in report.format()
        after = connection.execute(text("SELECT last_value, is_called FROM users_id_seq")).one()
        assert after == before
        assert connection.execute(text("SELECT current_schema()")).scalar_one() == schema


def test_production_online_authorization_is_enforced(monkeypatch):
    with application_engine.connect() as connection:
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("RENDER", raising=False)
        monkeypatch.delenv(PRODUCTION_MIGRATION_FLAG, raising=False)
        with pytest.raises(RuntimeError, match="explicit RECONCILEPRO_ALLOW_PRODUCTION_MIGRATION=true"):
            command.upgrade(_alembic_config(connection), "head")
        assert set(MigrationContext.configure(connection).get_current_heads()) == {"0004_import_batch_rev_counts"}

        monkeypatch.setenv(PRODUCTION_MIGRATION_FLAG, "true")
        command.upgrade(_alembic_config(connection), "head")
        assert set(MigrationContext.configure(connection).get_current_heads()) == {"0004_import_batch_rev_counts"}


def test_production_offline_authorization_and_development_generation(monkeypatch):
    offline_url = "postgresql+psycopg://offline.invalid/reconcilepro"
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv(PRODUCTION_MIGRATION_FLAG, raising=False)
    with pytest.raises(RuntimeError, match="explicit RECONCILEPRO_ALLOW_PRODUCTION_MIGRATION=true"):
        command.upgrade(_alembic_config(url=offline_url), "head", sql=True)

    monkeypatch.setenv(PRODUCTION_MIGRATION_FLAG, "true")
    command.upgrade(_alembic_config(url=offline_url), "head", sql=True)

    monkeypatch.setenv("ENVIRONMENT", "integration")
    monkeypatch.delenv(PRODUCTION_MIGRATION_FLAG, raising=False)
    command.upgrade(_alembic_config(url=offline_url), "head", sql=True)


def _new_actor():
    with SessionLocal() as db:
        user = User(name="Postgres Integration", email=f"pg-{uuid4().hex}@example.test", password=hash_password("Integration-Only-Password-123!"))
        db.add(user)
        db.flush()
        business = Business(name="Disposable Business", gstin="29" + uuid4().hex[:13].upper(), user_id=user.id)
        db.add(business)
        db.commit()
        return {
            "user_id": user.id,
            "business_id": business.id,
            "headers": {
                "Authorization": f"Bearer {create_access_token(user.id, user.email)}",
                "X-Business-ID": str(business.id),
            },
        }


def _upload_invoice(context, invoice_no, filename):
    csv_data = f"invoice_no,gstin,invoice_date,taxable_value,gst_amount\n{invoice_no},29ABCDE1234F1Z5,2026-07-01,1000,180\n"
    with TestClient(app) as client:
        return client.post(
            "/invoices/upload",
            files={"file": (filename, csv_data.encode(), "text/csv")},
            data={"source_type": "sales_register"},
            headers=context["headers"],
        )


def test_concurrent_identical_invoice_imports_are_unique_and_audited():
    context = _new_actor()
    marker = uuid4().hex
    invoice_no = f"PG-RACE-{marker[:20]}"
    filename = f"race-{marker}.csv"
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: _upload_invoice(context, invoice_no, filename), range(2)))

    assert all(response.status_code in {200, 409} for response in responses), [r.status_code for r in responses]
    assert any(response.status_code == 200 for response in responses)
    with SessionLocal() as db:
        invoices = db.scalars(select(Invoice).where(
            Invoice.business_id == context["business_id"],
            Invoice.source == "sales_register",
            Invoice.invoice_no == invoice_no,
            Invoice.deleted_at.is_(None),
        )).all()
        assert len(invoices) == 1
        batches = db.scalars(select(ImportBatch).where(
            ImportBatch.business_id == context["business_id"],
            ImportBatch.original_filename == filename,
        )).all()
        assert len(batches) == sum(response.status_code == 200 for response in responses)
        assert sum(batch.imported_rows for batch in batches) == 1
        assert sum(batch.duplicate_rows for batch in batches) == len(batches) - 1
        if any(response.status_code == 409 for response in responses):
            assert len(batches) == 1


def test_concurrent_same_key_imports_are_tenant_scoped():
    first, second = _new_actor(), _new_actor()
    marker = uuid4().hex
    invoice_no = f"PG-TENANT-{marker[:18]}"
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(_upload_invoice, first, invoice_no, f"first-{marker}.csv"),
            pool.submit(_upload_invoice, second, invoice_no, f"second-{marker}.csv"),
        ]
        responses = [future.result() for future in futures]
    assert [response.status_code for response in responses] == [200, 200]
    with SessionLocal() as db:
        rows = db.scalars(select(Invoice).where(Invoice.invoice_no == invoice_no, Invoice.deleted_at.is_(None))).all()
        assert {row.business_id for row in rows} == {first["business_id"], second["business_id"]}
        assert len(rows) == 2
        assert {row.import_batch.business_id for row in rows} == {first["business_id"], second["business_id"]}
        second_batch = db.scalar(select(Invoice.import_batch_id).where(
            Invoice.business_id == second["business_id"], Invoice.invoice_no == invoice_no
        ))
    with TestClient(app) as client:
        inaccessible = client.get(f"/imports/batches/{second_batch}", headers=first["headers"])
        accessible = client.get(f"/imports/batches/{second_batch}", headers=second["headers"])
    assert inaccessible.status_code == 404
    assert accessible.status_code == 200


def test_postgres_import_failure_rolls_back_invoice_batch_and_items():
    context = _new_actor()
    marker = uuid4().hex
    invoice_no_first = f"PG-ROLLBACK-{marker[:14]}-FIRST"
    invoice_no_second = f"PG-ROLLBACK-{marker[:14]}-SECOND"
    filename = f"rollback-{marker}.csv"
    function_name = f"pgit_fail_batch_item_{marker[:16]}"
    trigger_name = f"pgit_fail_item_{marker[:16]}"
    with application_engine.begin() as connection:
        connection.execute(text(
            f"CREATE FUNCTION public.{function_name}() RETURNS trigger LANGUAGE plpgsql AS "
            f"'BEGIN IF EXISTS (SELECT 1 FROM invoices WHERE id = NEW.invoice_id "
            f"AND invoice_no = ''{invoice_no_second}'') THEN "
            f"RAISE EXCEPTION ''intentional disposable integration failure''; "
            f"END IF; RETURN NEW; END;'"
        ))
        connection.execute(text(
            f"CREATE TRIGGER {trigger_name} BEFORE INSERT ON import_batch_items "
            f"FOR EACH ROW EXECUTE FUNCTION public.{function_name}()"
        ))
    try:
        csv_data = (
            "invoice_no,gstin,invoice_date,taxable_value,gst_amount\n"
            f"{invoice_no_first},29ABCDE1234F1Z5,2026-07-01,1000,180\n"
            f"{invoice_no_second},29ABCDE1234F1Z5,2026-07-02,2000,360\n"
        )
        with TestClient(app) as client:
            response = client.post(
                "/invoices/upload",
                files={"file": (filename, csv_data.encode(), "text/csv")},
                data={"source_type": "sales_register"},
                headers=context["headers"],
            )
        assert response.status_code == 500
        with SessionLocal() as db:
            assert db.scalar(select(Invoice.id).where(Invoice.business_id == context["business_id"], Invoice.invoice_no.in_([invoice_no_first, invoice_no_second]))) is None
            assert db.scalar(select(ImportBatch.batch_id).where(ImportBatch.business_id == context["business_id"], ImportBatch.original_filename == filename)) is None
            assert db.scalar(select(ImportBatchItem.id).join(ImportBatch).where(ImportBatch.business_id == context["business_id"], ImportBatch.original_filename == filename)) is None
    finally:
        with application_engine.begin() as connection:
            connection.execute(text(f"DROP TRIGGER IF EXISTS {trigger_name} ON import_batch_items"))
            connection.execute(text(f"DROP FUNCTION IF EXISTS public.{function_name}()"))


def test_postgres_gstr3b_import_failure_rolls_back_batch_item_and_return(monkeypatch):
    context = _new_actor()
    marker = uuid4().hex
    period = "2026-11"
    fixture_values = {
        "tax_period": period,
        "output_tax": 120.0,
        "eligible_itc": 45.0,
        "itc_reversed": 5.0,
        "net_itc": 40.0,
    }
    function_name = f"pgit_fail_gstr3b_item_{marker[:14]}"
    trigger_name = f"pgit_fail_gstr3b_{marker[:14]}"
    monkeypatch.setattr(gst_routes, "_fetch_gstr3b_fixture_summary", lambda _period, _business: fixture_values)
    with application_engine.begin() as connection:
        connection.execute(text(
            f"CREATE FUNCTION public.{function_name}() RETURNS trigger LANGUAGE plpgsql AS "
            f"'BEGIN RAISE EXCEPTION ''intentional disposable integration failure''; END;'"
        ))
        connection.execute(text(
            f"CREATE TRIGGER {trigger_name} BEFORE INSERT ON import_batch_items "
            f"FOR EACH ROW EXECUTE FUNCTION public.{function_name}()"
        ))
    try:
        with TestClient(app) as client:
            response = client.post(
                "/gst/gstr3b/import", json={"tax_period": period}, headers=context["headers"]
            )
        assert response.status_code == 500
        with SessionLocal() as db:
            assert db.scalar(select(GSTR3BReturn.id).where(
                GSTR3BReturn.business_id == context["business_id"], GSTR3BReturn.tax_period == period
            )) is None
            assert db.scalar(select(ImportBatch.batch_id).where(
                ImportBatch.business_id == context["business_id"], ImportBatch.tax_period == period,
                ImportBatch.source_type == "gstr3b",
            )) is None
            assert db.scalar(select(ImportBatchItem.id).join(ImportBatch).where(
                ImportBatch.business_id == context["business_id"], ImportBatch.tax_period == period,
                ImportBatch.source_type == "gstr3b",
            )) is None
            assert db.scalar(select(Invoice.id).where(Invoice.business_id == context["business_id"], Invoice.invoice_no == period)) is None
    finally:
        with application_engine.begin() as connection:
            connection.execute(text(f"DROP TRIGGER IF EXISTS {trigger_name} ON import_batch_items"))
            connection.execute(text(f"DROP FUNCTION IF EXISTS public.{function_name}()"))


def _seed_gstr3b_chain(context, monkeypatch):
    figures = {
        "A": {"tax_period": "2026-07", "output_tax": 110.0, "eligible_itc": 40.0, "itc_reversed": 5.0, "net_itc": 35.0},
        "B": {"tax_period": "2026-07", "output_tax": 220.0, "eligible_itc": 50.0, "itc_reversed": 6.0, "net_itc": 44.0},
        "C": {"tax_period": "2026-07", "output_tax": 330.0, "eligible_itc": 60.0, "itc_reversed": 7.0, "net_itc": 53.0},
    }
    selected = {"letter": "A"}
    monkeypatch.setattr(
        gst_routes,
        "_fetch_gstr3b_fixture_summary",
        lambda _period, _business: figures[selected["letter"]],
    )
    batch_ids = {}
    with TestClient(app) as client:
        for letter in ("A", "B", "C"):
            selected["letter"] = letter
            response = client.post(
                "/gst/gstr3b/import", json={"tax_period": "2026-07"}, headers=context["headers"]
            )
            assert response.status_code == 200, response.text
            assert response.json()["operation"] == ("new_import" if letter == "A" else "revision")
            batch_ids[letter] = response.json()["import_batch_id"]

    with SessionLocal() as db:
        record = db.scalar(select(GSTR3BReturn).where(
            GSTR3BReturn.business_id == context["business_id"], GSTR3BReturn.tax_period == "2026-07"
        ))
        assert record is not None
        return {**batch_ids, "return_id": record.id, "figures": figures}


def _delete_batch(context, batch_id):
    with TestClient(app) as client:
        return client.post(
            f"/imports/batches/{batch_id}/delete", json={"confirm": True}, headers=context["headers"]
        )


def _assert_return_values(record, figures):
    assert record.tax_period == figures["tax_period"]
    for field in ("output_tax", "eligible_itc", "itc_reversed", "net_itc"):
        assert float(getattr(record, field)) == pytest.approx(figures[field])


def test_gstr3b_a_b_c_reverse_deletion_and_audit_history(monkeypatch):
    context = _new_actor()
    chain = _seed_gstr3b_chain(context, monkeypatch)
    assert _delete_batch(context, chain["B"]).status_code == 409
    with SessionLocal() as db:
        row = db.get(GSTR3BReturn, chain["return_id"])
        _assert_return_values(row, chain["figures"]["C"])
        assert db.get(ImportBatch, chain["B"]).deleted_at is None
        assert db.get(ImportBatch, chain["C"]).deleted_at is None
    assert _delete_batch(context, chain["C"]).status_code == 200
    with SessionLocal() as db:
        row = db.get(GSTR3BReturn, chain["return_id"])
        _assert_return_values(row, chain["figures"]["B"])
        assert str(row.import_batch_id) == chain["A"]
    assert _delete_batch(context, chain["B"]).status_code == 200
    with SessionLocal() as db:
        row = db.get(GSTR3BReturn, chain["return_id"])
        _assert_return_values(row, chain["figures"]["A"])
        assert str(row.import_batch_id) == chain["A"]
        assert db.scalar(select(ImportBatchItem.id).where(ImportBatchItem.batch_id == chain["A"])) is not None
        for key in ("B", "C"):
            batch = db.get(ImportBatch, chain[key])
            assert batch is not None and batch.deleted_at is not None
            item = db.scalar(select(ImportBatchItem).where(ImportBatchItem.batch_id == chain[key]))
            assert item.previous_values is not None and item.new_values == chain["figures"][key]


def test_stale_gstr3b_snapshot_is_blocked_and_keeps_audit(monkeypatch):
    context = _new_actor()
    chain = _seed_gstr3b_chain(context, monkeypatch)
    with SessionLocal() as db:
        row = db.get(GSTR3BReturn, chain["return_id"])
        row.output_tax = 999.0
        db.commit()
    stale = _delete_batch(context, chain["C"])
    assert stale.status_code == 409
    with SessionLocal() as db:
        row = db.get(GSTR3BReturn, chain["return_id"])
        assert row.output_tax == 999.0
        assert db.get(ImportBatch, chain["C"]).deleted_at is None
        item = db.scalar(select(ImportBatchItem).where(ImportBatchItem.batch_id == chain["C"]))
        assert item.previous_values == chain["figures"]["B"]
        assert item.new_values == chain["figures"]["C"]


def test_concurrent_gstr3b_deletion_serializes_revisions_and_preserves_audit(monkeypatch):
    context = _new_actor()
    chain = _seed_gstr3b_chain(context, monkeypatch)
    with ThreadPoolExecutor(max_workers=2) as pool:
        newer = pool.submit(_delete_batch, context, chain["C"])
        older = pool.submit(_delete_batch, context, chain["B"])
        newer_result, older_result = newer.result(), older.result()
    assert newer_result.status_code == 200
    assert older_result.status_code in {200, 409}
    if older_result.status_code == 409:
        older_result = _delete_batch(context, chain["B"])
        assert older_result.status_code == 200
    with SessionLocal() as db:
        row = db.get(GSTR3BReturn, chain["return_id"])
        _assert_return_values(row, chain["figures"]["A"])
        assert str(row.import_batch_id) == chain["A"]
        assert all(db.get(ImportBatch, chain[key]) is not None for key in ("A", "B", "C"))
        assert db.scalar(select(ImportBatchItem.id).where(ImportBatchItem.batch_id == chain["B"])) is not None
        assert db.scalar(select(ImportBatchItem.id).where(ImportBatchItem.batch_id == chain["C"])) is not None
