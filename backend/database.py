import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)

env_path = Path(__file__).resolve().parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
db_file = Path(__file__).resolve().parent / "gst_local.db"
sqlite_url = f"sqlite:///{db_file.as_posix()}"


def _build_engine(url: str | None):
    target_url = url or sqlite_url
    if target_url.startswith("sqlite:///./") or target_url.strip() in (
        "sqlite:///gst_local.db",
        "sqlite:///:memory:",
    ):
        if not target_url.endswith(":memory:"):
            target_url = sqlite_url

    if target_url.startswith("postgresql://"):
        target_url = target_url.replace("postgresql://", "postgresql+psycopg://", 1)

    connect_args = {}
    if target_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    try:
        eng = create_engine(
            target_url,
            connect_args=connect_args,
            pool_pre_ping=True,
            **({"pool_timeout": 3} if not target_url.startswith("sqlite") else {}),
        )
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        return eng
    except Exception as exc:
        if not target_url.startswith("sqlite"):
            logger.warning(
                "Primary database (%s) unreachable: %s. Falling back to local SQLite at %s",
                target_url.split("@")[-1] if "@" in target_url else target_url,
                exc,
                sqlite_url,
            )
            fallback_args = {"check_same_thread": False}
            fallback_eng = create_engine(sqlite_url, connect_args=fallback_args)
            return fallback_eng
        raise exc


engine = _build_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
