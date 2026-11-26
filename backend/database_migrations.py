"""Read-only helpers for checking that a database has an applied Alembic head."""

from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory


def assert_schema_at_head(engine) -> None:
    """Raise a generic error unless the connected schema is at the repository head."""
    config = Config(str(Path(__file__).resolve().parent / "alembic.ini"))
    expected_revisions = set(ScriptDirectory.from_config(config).get_heads())
    with engine.connect() as connection:
        current_revisions = set(MigrationContext.configure(connection).get_current_heads())

    if current_revisions != expected_revisions:
        raise RuntimeError("Database migration revision is missing or out of date.")
