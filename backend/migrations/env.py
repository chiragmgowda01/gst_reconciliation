"""Alembic environment; requires an explicit URL and never reads .env files."""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from models.base import Base
from models import models as _registered_models  # noqa: F401
from migration_safety import VERIFIED_LEGACY_STAMP_TOKEN, require_migration_authorization

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _configured_url() -> str:
    """Use an explicit process/config URL; do not load or log credentials."""
    configured = os.getenv("DATABASE_URL", "").strip() or config.get_main_option("sqlalchemy.url", "").strip()
    if not configured:
        raise RuntimeError("Set DATABASE_URL explicitly before running Alembic.")

    parsed = make_url(configured)
    require_migration_authorization(database_dialect=parsed.get_backend_name())
    return configured


def run_migrations_offline() -> None:
    """Generate SQL only; never opens a database connection or executes DDL."""
    url = config.attributes.get("url") or config.get_main_option("sqlalchemy.url", "").strip()
    if not url:
        url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("Set an explicit SQLAlchemy URL for offline migration generation.")
    parsed_url = make_url(url)
    # Offline mode only renders SQL. Production still requires explicit
    # authorization and the PostgreSQL dialect before migration SQL is emitted.
    require_migration_authorization(database_dialect=parsed_url.get_backend_name())
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    _require_verified_stamp()
    with context.begin_transaction():
        context.run_migrations()


def _run_migrations_with_connection(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    _require_verified_stamp()
    with context.begin_transaction():
        context.run_migrations()


def _require_verified_stamp() -> None:
    migration_fn = context.get_context().opts.get("fn")
    if getattr(migration_fn, "__name__", "") == "do_stamp" and (
        config.attributes.get("reconcilepro_verified_legacy_stamp") is not VERIFIED_LEGACY_STAMP_TOKEN
    ):
        raise RuntimeError(
            "Direct Alembic stamp is disabled. Verify the legacy schema and use "
            "schema_parity.stamp_verified_legacy_baseline(connection)."
        )


def run_migrations_online() -> None:
    provided_connection = config.attributes.get("connection")
    if provided_connection is not None:
        # Guard before using injected connections too; otherwise an application or
        # script could bypass the production flag by supplying an Engine connection.
        require_migration_authorization(connection=provided_connection)
        _run_migrations_with_connection(provided_connection)
        return

    url = _configured_url()
    connectable = create_engine(url, poolclass=NullPool)
    try:
        with connectable.connect() as connection:
            _run_migrations_with_connection(connection)
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
