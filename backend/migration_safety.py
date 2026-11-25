"""Shared safeguards for Alembic migration and baseline-stamp operations."""

import os


PRODUCTION_MIGRATION_FLAG = "RECONCILEPRO_ALLOW_PRODUCTION_MIGRATION"
VERIFIED_LEGACY_STAMP_TOKEN = object()


def is_production_environment() -> bool:
    environment = os.getenv("ENVIRONMENT", "").strip().lower()
    return environment in {"production", "prod"} or "RENDER" in os.environ


def require_migration_authorization(*, connection=None, database_dialect: str | None = None) -> None:
    """Require explicit authorization and PostgreSQL for production migration SQL or DDL."""
    if not is_production_environment():
        return

    if os.getenv(PRODUCTION_MIGRATION_FLAG, "").strip().lower() != "true":
        raise RuntimeError(
            "Production migration operations require explicit "
            f"{PRODUCTION_MIGRATION_FLAG}=true."
        )

    dialect = database_dialect
    if connection is not None:
        dialect = connection.dialect.name
    if dialect != "postgresql":
        raise RuntimeError("Production migrations require a PostgreSQL connection.")
