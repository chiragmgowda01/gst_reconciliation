"""Database configuration with strict production PostgreSQL requirements."""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

logger = logging.getLogger(__name__)

env_path = Path(__file__).resolve().parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()


def is_production_environment() -> bool:
    """Render deployments and explicit production environments require PostgreSQL."""
    environment = os.getenv("ENVIRONMENT", "").strip().lower()
    return environment in {"production", "prod"} or "RENDER" in os.environ


def _build_engine(url: str | None):
    production = is_production_environment()
    configured_url = (url or "").strip()

    if not configured_url:
        if production:
            raise RuntimeError(
                "DATABASE_URL is required in production and must point to PostgreSQL."
            )
        # Keep the established local-development default. Pytest overrides this
        # with its dedicated in-memory URL in backend/tests/conftest.py.
        db_file = Path(__file__).resolve().parent / "gst_local.db"
        configured_url = f"sqlite:///{db_file.as_posix()}"

    try:
        parsed_url = make_url(configured_url)
        dialect_name = parsed_url.get_backend_name()
        if production and dialect_name != "postgresql":
            raise RuntimeError(
                "Production DATABASE_URL must use PostgreSQL; SQLite and other databases are not allowed."
            )

        if dialect_name == "postgresql" and parsed_url.drivername == "postgresql":
            parsed_url = parsed_url.set(drivername="postgresql+psycopg")

        connect_args = {"check_same_thread": False} if dialect_name == "sqlite" else {}
        pool_options = (
            {"poolclass": StaticPool}
            if dialect_name == "sqlite" and parsed_url.database in {None, "", ":memory:"}
            else {}
        )
        engine = create_engine(
            parsed_url,
            connect_args=connect_args,
            pool_pre_ping=True,
            **pool_options,
            **({"pool_timeout": 3} if dialect_name == "postgresql" else {}),
        )

        # Check both the URL-selected dialect and an actual connection before
        # publishing the engine to application code.
        if production and engine.dialect.name != "postgresql":
            engine.dispose()
            raise RuntimeError(
                "Production database engine did not initialize with PostgreSQL."
            )
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return engine
    except RuntimeError:
        raise
    except Exception as exc:
        # Never include the URL or driver exception text: either may contain
        # usernames, passwords, hostnames, or query parameters.
        logger.error("Database engine initialization failed (%s).", type(exc).__name__)
        if production:
            raise RuntimeError(
                "Unable to initialize the required production PostgreSQL database. "
                "Check DATABASE_URL and database availability."
            ) from None
        raise RuntimeError(
            f"Unable to initialize the configured database ({type(exc).__name__})."
        ) from None


DATABASE_URL = os.getenv("DATABASE_URL")
engine = _build_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
