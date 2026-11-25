"""Alembic tests using only throwaway SQLite files and offline PostgreSQL DDL."""

from io import StringIO
from pathlib import Path
from uuid import uuid4
from datetime import date, datetime

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
import pytest
from sqlalchemy import CheckConstraint, Column, Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session

from database_migrations import assert_schema_at_head
from schema_parity import stamp_verified_legacy_baseline, verify_legacy_schema


BACKEND_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_CONFIG = BACKEND_DIR / "alembic.ini"


def _config(connection=None, output_buffer=None):
    config = Config(str(ALEMBIC_CONFIG), output_buffer=output_buffer)
    if connection is not None:
        config.attributes["connection"] = connection
    return config


def _legacy_orm_models(
    *, invoice_gstin_type=String(15), include_invoice_no_index=True, include_gstr_unique=True,
    invoice_source_server_default=None, include_invoice_check=False,
):
    """Independent copy of the pre-Alembic ORM models used to construct legacy DBs."""
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
        if include_invoice_check:
            __table_args__ = (CheckConstraint("taxable_value >= 0", name="ck_legacy_invoice_value"),)
        id = Column(Integer, primary_key=True, index=True)
        invoice_no = Column(String(50), index=include_invoice_no_index, nullable=False)
        invoice_date = Column(Date, nullable=False)
        gstin = Column(invoice_gstin_type, nullable=False)
        taxable_value = Column(Float, nullable=False)
        gst_amount = Column(Float, nullable=False)
        source = Column(String(30), nullable=False, server_default=invoice_source_server_default)
        created_at = Column(DateTime, nullable=False)
        business_id = Column(Integer, ForeignKey("businesses.id"), nullable=False)

    class LegacyGSTR3BReturn(LegacyBase):
        __tablename__ = "gstr3b_returns"
        if include_gstr_unique:
            __table_args__ = (
                UniqueConstraint("business_id", "tax_period", name="uq_gstr3b_business_tax_period"),
            )
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


def _make_legacy_database(tmp_path, **model_options):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.sqlite'}")
    models = _legacy_orm_models(**model_options)
    models[0].metadata.create_all(engine)
    return engine, models


def test_independent_legacy_orm_adoption_preserves_existing_rows(tmp_path):
    engine, legacy = _make_legacy_database(tmp_path)
    _LegacyBase, LegacyUser, LegacyBusiness, LegacyInvoice, LegacyGSTR3BReturn = legacy
    try:
        with Session(engine) as session:
            session.add(LegacyUser(id=10, name="Legacy User", email="legacy@example.test", password="hash"))
            session.add(
                LegacyBusiness(id=20, name="Legacy Business", gstin="29ABCDE1234F1Z5", user_id=10)
            )
            session.add(
                LegacyInvoice(
                    id=30,
                    invoice_no="LEGACY-001",
                    invoice_date=date(2026, 7, 5),
                    gstin="29ABCDE1234F1Z5",
                    taxable_value=100.0,
                    gst_amount=18.0,
                    source="sales_register",
                    created_at=datetime(2026, 10, 22, 9, 58),
                    business_id=20,
                )
            )
            session.add(
                LegacyGSTR3BReturn(
                    id=40,
                    business_id=20,
                    tax_period="2026-07",
                    output_tax=100.0,
                    eligible_itc=40.0,
                    itc_reversed=2.0,
                    net_itc=38.0,
                    created_at=datetime(2026, 10, 22, 9, 58),
                    updated_at=datetime(2026, 10, 22, 9, 58),
                )
            )
            session.commit()

        with engine.connect() as connection:
            config = _config(connection)
            report = verify_legacy_schema(connection)
            assert report.matches, report.format()
            stamp_verified_legacy_baseline(connection)
            connection.commit()
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0001_core_schema"

            command.upgrade(config, "head")
            connection.commit()
            assert_schema_at_head(engine)
            inspector = inspect(connection)
            assert {"import_batches", "import_batch_items"}.issubset(set(inspector.get_table_names()))
            assert {"import_batch_id", "deleted_at"}.issubset(
                {column["name"] for column in inspector.get_columns("invoices")}
            )
            assert {"import_batch_id", "deleted_at"}.issubset(
                {column["name"] for column in inspector.get_columns("gstr3b_returns")}
            )
            invoice = connection.execute(
                text("SELECT id, invoice_no, business_id, import_batch_id, deleted_at FROM invoices WHERE id = 30")
            ).one()
            assert tuple(invoice) == (30, "LEGACY-001", 20, None, None)
            returned = connection.execute(
                text("SELECT id, tax_period, output_tax, import_batch_id, deleted_at FROM gstr3b_returns WHERE id = 40")
            ).one()
            assert tuple(returned) == (40, "2026-07", 100.0, None, None)
            assert connection.execute(text("SELECT id, name FROM users WHERE id = 10")).one() == (
                10,
                "Legacy User",
            )
            assert connection.execute(
                text("SELECT id, name, user_id FROM businesses WHERE id = 20")
            ).one() == (20, "Legacy Business", 10)

            command.downgrade(config, "0001_core_schema")
            connection.commit()
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0001_core_schema"
            try:
                assert_schema_at_head(engine)
            except RuntimeError as exc:
                assert "missing or out of date" in str(exc)
            else:
                raise AssertionError("A downgraded database must not be reported ready for application startup.")
            inspector = inspect(connection)
            assert "import_batches" not in inspector.get_table_names()
            assert "import_batch_items" not in inspector.get_table_names()
            assert "import_batch_id" not in {column["name"] for column in inspector.get_columns("invoices")}
            assert connection.execute(
                text("SELECT id, invoice_no, business_id FROM invoices WHERE id = 30")
            ).one() == (30, "LEGACY-001", 20)
            assert connection.execute(
                text("SELECT id, tax_period, output_tax FROM gstr3b_returns WHERE id = 40")
            ).one() == (40, "2026-07", 100.0)
            assert connection.execute(text("SELECT id, name FROM users WHERE id = 10")).one() == (
                10,
                "Legacy User",
            )
            assert connection.execute(
                text("SELECT id, name, user_id FROM businesses WHERE id = 20")
            ).one() == (20, "Legacy Business", 10)
    finally:
        engine.dispose()


def test_baseline_stamp_refuses_missing_column(tmp_path):
    engine, _ = _make_legacy_database(tmp_path)
    try:
        with engine.connect() as connection:
            connection.execute(text("ALTER TABLE invoices DROP COLUMN gstin"))
            connection.commit()
            with pytest.raises(RuntimeError, match=r"(?s)Baseline stamp refused.*column invoices.gstin: missing"):
                stamp_verified_legacy_baseline(connection)
            assert "alembic_version" not in inspect(connection).get_table_names()
    finally:
        engine.dispose()


def test_direct_unverified_alembic_stamp_is_disabled(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'unverified_stamp.sqlite'}")
    try:
        with engine.connect() as connection:
            with pytest.raises(RuntimeError, match="Direct Alembic stamp is disabled"):
                command.stamp(_config(connection), "0001_core_schema")
            assert "alembic_version" not in inspect(connection).get_table_names()
    finally:
        engine.dispose()


def test_baseline_stamp_refuses_different_column_type(tmp_path):
    engine, _ = _make_legacy_database(tmp_path, invoice_gstin_type=Integer)
    try:
        with engine.connect() as connection:
            with pytest.raises(RuntimeError, match=r"(?s)Baseline stamp refused.*column invoices.gstin type"):
                stamp_verified_legacy_baseline(connection)
            assert "alembic_version" not in inspect(connection).get_table_names()
    finally:
        engine.dispose()


def test_baseline_stamp_refuses_server_default_mismatch(tmp_path):
    engine, _ = _make_legacy_database(tmp_path, invoice_source_server_default="'unexpected'")
    try:
        with engine.connect() as connection:
            with pytest.raises(RuntimeError, match=r"column invoices.source server default"):
                stamp_verified_legacy_baseline(connection)
            assert "alembic_version" not in inspect(connection).get_table_names()
    finally:
        engine.dispose()


def test_baseline_stamp_refuses_unexpected_check_constraint(tmp_path):
    engine, _ = _make_legacy_database(tmp_path, include_invoice_check=True)
    try:
        with engine.connect() as connection:
            with pytest.raises(RuntimeError, match=r"check constraint invoices: unexpected"):
                stamp_verified_legacy_baseline(connection)
            assert "alembic_version" not in inspect(connection).get_table_names()
    finally:
        engine.dispose()


def test_schema_parity_fails_closed_when_inspection_is_unsupported(monkeypatch, tmp_path):
    import schema_parity

    engine, _ = _make_legacy_database(tmp_path)
    original_inspect = schema_parity.inspect
    try:
        with engine.connect() as connection:
            monkeypatch.setattr(
                schema_parity,
                "inspect",
                lambda _connection: (_ for _ in ()).throw(NotImplementedError("unsupported inspector")),
            )
            report = verify_legacy_schema(connection)
            assert not report.matches
            assert "schema inspection failed (NotImplementedError)" in report.format()
            with pytest.raises(RuntimeError, match=r"(?s)Baseline stamp refused.*schema inspection failed"):
                stamp_verified_legacy_baseline(connection)
            monkeypatch.setattr(schema_parity, "inspect", original_inspect)
            assert "alembic_version" not in original_inspect(connection).get_table_names()
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("model_options", "expected_message"),
    [
        ({"include_invoice_no_index": False}, "index invoices: missing"),
        ({"include_gstr_unique": False}, "unique constraint gstr3b_returns: missing"),
    ],
)
def test_baseline_stamp_refuses_missing_index_or_constraint(tmp_path, model_options, expected_message):
    engine, _ = _make_legacy_database(tmp_path, **model_options)
    try:
        with engine.connect() as connection:
            with pytest.raises(RuntimeError, match=expected_message):
                stamp_verified_legacy_baseline(connection)
            assert "alembic_version" not in inspect(connection).get_table_names()
    finally:
        engine.dispose()


def test_fresh_disposable_sqlite_database_upgrades_to_head(tmp_path):
    database_file = tmp_path / "fresh_schema.sqlite"
    engine = create_engine(f"sqlite:///{database_file}")
    try:
        with engine.connect() as connection:
            command.upgrade(_config(connection), "head")
            assert_schema_at_head(engine)
            names = set(inspect(connection).get_table_names())
            assert {
                "users",
                "businesses",
                "invoices",
                "gstr3b_returns",
                "import_batches",
                "import_batch_items",
                "alembic_version",
            }.issubset(names)
            invoice_indexes = inspect(connection).get_indexes("invoices")
            unique_index = next(
                index for index in invoice_indexes
                if index["name"] == "uq_invoices_active_business_source_invoice"
            )
            assert bool(unique_index["unique"])
            assert unique_index["column_names"] == ["business_id", "source", "invoice_no"]
            sqlite_index_sql = connection.execute(
                text(
                    "SELECT sql FROM sqlite_master WHERE type = 'index' "
                    "AND name = 'uq_invoices_active_business_source_invoice'"
                )
            ).scalar_one()
            assert "WHERE deleted_at IS NULL" in sqlite_index_sql
            assert "revised_rows" in {column["name"] for column in inspect(connection).get_columns("import_batches")}
    finally:
        engine.dispose()


def test_revision_0001_matches_independent_legacy_baseline(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'migration_baseline.sqlite'}")
    try:
        with engine.connect() as connection:
            command.upgrade(_config(connection), "0001_core_schema")
            connection.commit()
            report = verify_legacy_schema(connection, allow_alembic_version=True)
            assert report.matches, report.format()
    finally:
        engine.dispose()


def test_downgrade_refuses_to_drop_import_audit_data(tmp_path):
    database_file = tmp_path / "retain_audit.sqlite"
    engine = create_engine(f"sqlite:///{database_file}")
    try:
        with engine.connect() as connection:
            config = _config(connection)
            command.upgrade(config, "head")
            connection.execute(
                text("INSERT INTO users (id, name, email, password) VALUES (1, 'Owner', 'owner@example.test', 'hash')")
            )
            connection.execute(
                text("INSERT INTO businesses (id, name, gstin, user_id) VALUES (2, 'Business', '29ABCDE1234F1Z5', 1)")
            )
            connection.execute(
                text(
                    "INSERT INTO import_batches "
                    "(batch_id, business_id, imported_by_user_id, source_category, source_type, original_filename, "
                    "fixture_identifier, tax_period, total_rows, imported_rows, duplicate_rows, rejected_rows, "
                    "created_at, completed_at, status, deleted_at, deleted_by_user_id) "
                    "VALUES (:batch_id, 2, 1, 'csv_upload', 'sales_register', 'sales.csv', NULL, NULL, "
                    "1, 1, 0, 0, '2026-11-25 10:00:00', NULL, 'completed', NULL, NULL)"
                ),
                {"batch_id": uuid4().hex},
            )
            connection.commit()

            with pytest.raises(RuntimeError, match="downgrade blocked.*audit data exists"):
                command.downgrade(config, "0001_core_schema")

            assert connection.execute(text("SELECT COUNT(*) FROM import_batches")).scalar_one() == 1
            assert_schema_at_head(engine)
    finally:
        engine.dispose()


def test_revision_count_migration_defaults_existing_batches_and_protects_revision_history(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'revision_counts.sqlite'}")
    try:
        with engine.connect() as connection:
            config = _config(connection)
            command.upgrade(config, "0003_active_invoice_uniqueness")
            connection.execute(
                text("INSERT INTO users (id, name, email, password) VALUES (1, 'Owner', 'owner@example.test', 'hash')")
            )
            connection.execute(
                text("INSERT INTO businesses (id, name, gstin, user_id) VALUES (2, 'Business', '29ABCDE1234F1Z5', 1)")
            )
            connection.execute(
                text(
                    "INSERT INTO import_batches (batch_id, business_id, imported_by_user_id, source_category, source_type, "
                    "original_filename, total_rows, imported_rows, duplicate_rows, rejected_rows, created_at, status) "
                    "VALUES (:batch_id, 2, 1, 'csv_upload', 'gstr3b', 'returns.csv', 1, 1, 0, 0, "
                    "'2026-11-25 10:00:00', 'completed')"
                ),
                {"batch_id": uuid4().hex},
            )
            connection.commit()
            command.upgrade(config, "head")
            assert connection.execute(text("SELECT revised_rows FROM import_batches")).scalar_one() == 0
            connection.execute(text("UPDATE import_batches SET revised_rows = 1"))
            connection.commit()
            with pytest.raises(RuntimeError, match="downgrade blocked because revised import history exists"):
                command.downgrade(config, "0003_active_invoice_uniqueness")
            assert connection.execute(text("SELECT revised_rows FROM import_batches")).scalar_one() == 1
            assert_schema_at_head(engine)
    finally:
        engine.dispose()


def test_postgresql_schema_can_be_generated_offline_without_a_connection():
    output = StringIO()
    config = _config(output_buffer=output)
    config.attributes["url"] = "postgresql+psycopg://migration-user:unused@example.invalid/reconcilepro"

    command.upgrade(config, "head", sql=True)
    generated_sql = output.getvalue()

    assert "CREATE TABLE import_batches" in generated_sql
    assert "CREATE TABLE import_batch_items" in generated_sql
    assert "UUID" in generated_sql
    assert "import_batch_id UUID" in generated_sql
    assert "FOREIGN KEY(business_id) REFERENCES businesses (id) ON DELETE RESTRICT" in generated_sql
    assert "uq_gstr3b_business_tax_period" in generated_sql
    assert "uq_invoices_active_business_source_invoice" in generated_sql
    assert "WHERE deleted_at IS NULL" in generated_sql


def test_active_invoice_duplicates_block_new_migration_without_changing_rows(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'duplicate_active_invoices.sqlite'}")
    try:
        with engine.connect() as connection:
            config = _config(connection)
            command.upgrade(config, "0002_import_batch_management")
            connection.execute(
                text("INSERT INTO users (id, name, email, password) VALUES (1, 'Owner', 'owner@example.test', 'hash')")
            )
            connection.execute(
                text("INSERT INTO businesses (id, name, gstin, user_id) VALUES (2, 'Business', '29ABCDE1234F1Z5', 1)")
            )
            invoice_insert = text(
                "INSERT INTO invoices (id, invoice_no, invoice_date, gstin, taxable_value, gst_amount, source, "
                "created_at, business_id, import_batch_id, deleted_at) "
                "VALUES (:id, 'DUP-001', '2026-07-01', '29ABCDE1234F1Z5', 100, 18, 'sales_register', "
                "'2026-11-25 10:00:00', 2, NULL, NULL)"
            )
            connection.execute(invoice_insert, [{"id": 10}, {"id": 11}])
            connection.commit()
            before = connection.execute(
                text("SELECT id, invoice_no, business_id, source, deleted_at FROM invoices ORDER BY id")
            ).all()

            with pytest.raises(RuntimeError, match="Active invoice uniqueness migration aborted") as exc:
                command.upgrade(config, "head")

            assert "business_id=2" in str(exc.value)
            assert "invoice_no='DUP-001'" in str(exc.value)
            after = connection.execute(
                text("SELECT id, invoice_no, business_id, source, deleted_at FROM invoices ORDER BY id")
            ).all()
            assert after == before
            assert "uq_invoices_active_business_source_invoice" not in {
                index["name"] for index in inspect(connection).get_indexes("invoices")
            }
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
                "0002_import_batch_management"
            )
    finally:
        engine.dispose()


def test_alembic_revision_identifiers_fit_varchar32_and_chain_is_valid():
    script_dir = ScriptDirectory.from_config(_config())
    revisions = list(reversed(list(script_dir.walk_revisions("base", "heads"))))
    revision_ids = [rev.revision for rev in revisions]

    assert len(revision_ids) == len(set(revision_ids))
    assert all(len(rev_id) <= 32 for rev_id in revision_ids)
    assert script_dir.get_heads() == ["0004_import_batch_rev_counts"]
    assert revision_ids == [
        "0001_core_schema",
        "0002_import_batch_management",
        "0003_active_invoice_uniqueness",
        "0004_import_batch_rev_counts",
    ]
