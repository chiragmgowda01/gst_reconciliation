"""Force the suite onto an isolated in-memory database before app imports."""

import os

import pytest
from sqlalchemy import text


_configured_database_url = os.getenv("DATABASE_URL", "").strip()
_configured_app_database_url = os.getenv("APP_DATABASE_URL", "").strip()
_is_render = "RENDER" in os.environ
_is_production = os.getenv("ENVIRONMENT", "").strip().lower() in {"production", "prod"}

# Refuse to run if the process appears configured for a hosted or PostgreSQL
# database. Do not print the URL: it may contain credentials.
if (
    _is_render
    or _is_production
    or _configured_database_url.lower().startswith(("postgres",))
    or _configured_app_database_url.lower().startswith(("postgres",))
):
    raise pytest.UsageError(
        "Backend tests refused to start: production/hosted or PostgreSQL database configuration detected."
    )

os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["APP_DATABASE_URL"] = "sqlite:///:memory:"

from database import SessionLocal, engine, get_db  # noqa: E402
from main import app  # noqa: E402
from models.base import Base  # noqa: E402
from models import models as _models  # noqa: E402,F401


@pytest.fixture(autouse=True)
def isolated_application_database():
    """Give tests using the app's global session factory a fresh SQLite schema."""
    Base.metadata.create_all(bind=engine)
    # The application lifespan now verifies that an Alembic revision is present.
    # Tests still create their isolated schema directly from the registered ORM
    # metadata, then mark that disposable schema at the current migration head.
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS alembic_version "
                "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
            )
        )
        connection.execute(text("DELETE FROM alembic_version"))
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            {"revision": "0005_runtime_role_security"},
        )

    def override_get_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    previous_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    try:
        yield
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override
        Base.metadata.drop_all(bind=engine)
