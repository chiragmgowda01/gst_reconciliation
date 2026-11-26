import logging
import os
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

ISOLATED_DEMO_SEED_FLAG = "RECONCILEPRO_ISOLATED_DEMO_SEED"


def is_production_mode() -> bool:
    """Detect Render deployments and explicit production environment settings."""
    env = os.getenv("ENVIRONMENT", "").strip().lower()
    return env in ("production", "prod") or "RENDER" in os.environ


# Refuse a direct production seed invocation before importing database.py, whose
# module initialization opens the configured database connection.
if __name__ == "__main__" and is_production_mode():
    raise SystemExit("Production fixture seeding is disabled.")

from database import SessionLocal, engine
from database_migrations import assert_schema_at_head
from models.models import Business, GSTR3BReturn, Invoice, User
from services.auth import hash_password
from services.validation import (
    normalize_gstr3b_dataframe,
    normalize_invoice_dataframe,
    parse_date_safely,
    validate_gstr3b_row,
)

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def ensure_isolated_demo_seed_allowed(database_engine) -> None:
    """Allow fixture seeding only into an explicitly selected, empty SQLite DB."""
    if is_production_mode():
        raise RuntimeError("Production fixture seeding is disabled.")
    if os.getenv(ISOLATED_DEMO_SEED_FLAG, "").strip().lower() != "true":
        raise RuntimeError(
            f"Fixture seeding requires {ISOLATED_DEMO_SEED_FLAG}=true for an isolated demo database."
        )
    if database_engine.dialect.name != "sqlite":
        raise RuntimeError("Isolated demo fixture seeding is limited to SQLite databases.")
    if not os.getenv("DATABASE_URL", "").strip():
        raise RuntimeError("Set an explicit SQLite DATABASE_URL for isolated demo seeding.")

    database_path = database_engine.url.database
    default_database = (Path(__file__).resolve().parent / "gst_local.db").resolve()
    if database_path not in {None, "", ":memory:"} and Path(database_path).resolve() == default_database:
        raise RuntimeError("The shared local development database is not an isolated demo target.")

    required_tables = {"users", "businesses", "invoices", "gstr3b_returns"}
    available_tables = set(inspect(database_engine).get_table_names())
    if not required_tables.issubset(available_tables):
        raise RuntimeError("Isolated demo database must be initialized with the current schema first.")

    with database_engine.connect() as connection:
        for table_name in sorted(required_tables):
            count = connection.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one()
            if count:
                raise RuntimeError(
                    "Isolated demo fixture seeding requires an empty database; existing application records were found."
                )


def get_seed_credentials() -> tuple[str, str]:
    """
    Retrieve admin seed credentials.
    In production (ENVIRONMENT=production or RENDER is set):
      SEED_ADMIN_EMAIL and SEED_ADMIN_PASSWORD are required environment variables.
      Insecure default passwords are explicitly rejected.
    In development/testing:
      Falls back to default@gst.local / changeme if not provided in environment.
    """
    admin_email = os.getenv("SEED_ADMIN_EMAIL")
    admin_password = os.getenv("SEED_ADMIN_PASSWORD")

    if is_production_mode():
        if not admin_email or not admin_email.strip():
            raise ValueError(
                "Secure Seeding Failure: SEED_ADMIN_EMAIL environment variable is required in production mode."
            )
        if not admin_password or not admin_password.strip():
            raise ValueError(
                "Secure Seeding Failure: SEED_ADMIN_PASSWORD environment variable is required in production mode."
            )
        if admin_password.strip().lower() in ("changeme", "admin", "password", "12345678", "demo"):
            raise ValueError(
                "Secure Seeding Failure: SEED_ADMIN_PASSWORD cannot use common default/insecure passwords in production."
            )
        return admin_email.strip(), admin_password.strip()

    # Local development / automated testing fallback
    resolved_email = admin_email.strip() if admin_email else "default@gst.local"
    resolved_password = admin_password if admin_password else "changeme"
    return resolved_email, resolved_password


def ensure_user(
    session,
    email: str | None = None,
    password: str | None = None,
    name: str = "Default User",
) -> User:
    """Ensure seed user exists in the database. Never overwrites password on repeat seeding."""
    seed_email, seed_password = get_seed_credentials()
    target_email = email or seed_email
    target_pwd = password or seed_password

    user = session.scalar(select(User).where(User.email == target_email))
    if user is None:
        user = User(
            name=name,
            email=target_email,
            password=hash_password(target_pwd),
        )
        session.add(user)
        session.flush()
        logger.info("Created seed user: %s", target_email)
    else:
        logger.info("Seed user '%s' already exists; preserving existing password.", target_email)
    return user


def ensure_business(session, gstin: str, business_name: str | None = None) -> Business:
    """Ensure default enterprise business exists for the seed user."""
    business = session.scalar(select(Business).where(Business.gstin == gstin))
    if business is None:
        user = ensure_user(session)
        business = Business(name=business_name or gstin, gstin=gstin, user_id=user.id)
        session.add(business)
        session.flush()
        logger.info("Created seed business: %s (%s)", business.name, business.gstin)
    return business


def _import_csv_file(file_name: str, source: str, business_id: int | None = None) -> int:
    """Import sales/purchase/GSTR invoice records into invoices table."""
    session = SessionLocal()
    try:
        file_path = DATA / file_name
        if not file_path.exists():
            return 0
        df = pd.read_csv(file_path, encoding="utf-8-sig")
        df.columns = [str(c).replace("\ufeff", "").strip() for c in df.columns]

        if df.empty:
            return 0

        # Demo MSME defaults to Business 1 or ensure default MSME business
        if business_id is None:
            demo_msme = session.scalar(select(Business).where(Business.id == 1))
            if demo_msme is None:
                demo_msme = ensure_business(session, "29AAAAA1111A1Z5", "Demo MSME Enterprise")
            target_business_id = demo_msme.id
        else:
            target_business_id = business_id

        norm_df, missing = normalize_invoice_dataframe(df, source)
        if missing:
            norm_df = df

        imported = 0
        for _, row in norm_df.iterrows():
            invoice_no = str(row.get("invoice_no") or "").strip()
            if not invoice_no or invoice_no.lower() == "nan":
                continue
            inv_date = parse_date_safely(row.get("invoice_date"))
            if not inv_date:
                continue

            gstin = str(row.get("gstin") or row.get("customer_gstin") or row.get("supplier_gstin") or "").strip()
            try:
                taxable_value = float(row["taxable_value"])
                gst_amount = float(row["gst_amount"])
            except (ValueError, KeyError, TypeError):
                continue

            existing = session.scalar(
                select(Invoice).where(
                    Invoice.invoice_no == invoice_no,
                    Invoice.business_id == target_business_id,
                    Invoice.source == source,
                )
            )
            if existing is not None:
                continue

            invoice = Invoice(
                invoice_no=invoice_no,
                invoice_date=inv_date,
                gstin=gstin,
                taxable_value=taxable_value,
                gst_amount=gst_amount,
                source=source,
                business_id=target_business_id,
            )

            session.add(invoice)
            imported += 1

        session.commit()
        return imported
    except IntegrityError:
        session.rollback()
        raise
    finally:
        session.close()


def _import_gstr3b_file(file_name: str = "gstr3b.csv", business_id: int | None = None) -> int:
    """Import monthly GSTR-3B return summary into persistent gstr3b_returns table."""
    session = SessionLocal()
    try:
        file_path = DATA / file_name
        if not file_path.exists():
            return 0
        df = pd.read_csv(file_path, encoding="utf-8-sig")
        df.columns = [str(c).replace("\ufeff", "").strip() for c in df.columns]

        if df.empty:
            return 0

        if business_id is None:
            demo_msme = session.scalar(select(Business).where(Business.id == 1))
            if demo_msme is None:
                demo_msme = ensure_business(session, "29AAAAA1111A1Z5", "Demo MSME Enterprise")
            target_business_id = demo_msme.id
        else:
            target_business_id = business_id

        norm_df, missing = normalize_gstr3b_dataframe(df)
        if missing:
            return 0

        imported = 0
        for idx, row in norm_df.iterrows():
            row_dict = row.to_dict()
            is_valid, _ = validate_gstr3b_row(row_dict, idx + 1)
            if not is_valid:
                continue

            period = str(row_dict["tax_period"]).strip()
            out_tax = float(row_dict["output_tax"])
            el_itc = float(row_dict["eligible_itc"])
            itc_rev = float(row_dict.get("itc_reversed", 0.0) or 0.0)
            net_itc = float(row_dict.get("net_itc", el_itc - itc_rev))

            existing = session.scalar(
                select(GSTR3BReturn).where(
                    GSTR3BReturn.business_id == target_business_id,
                    GSTR3BReturn.tax_period == period,
                )
            )
            if existing is not None:
                continue

            gstr3b_record = GSTR3BReturn(
                business_id=target_business_id,
                tax_period=period,
                output_tax=out_tax,
                eligible_itc=el_itc,
                itc_reversed=itc_rev,
                net_itc=net_itc,
            )
            session.add(gstr3b_record)
            imported += 1

        session.commit()
        return imported
    except IntegrityError:
        session.rollback()
        raise
    finally:
        session.close()


def import_csv_file(file_name: str, source: str, business_id: int | None = None) -> int:
    """Guarded entry point for importing a synthetic invoice fixture."""
    ensure_isolated_demo_seed_allowed(engine)
    assert_schema_at_head(engine)
    return _import_csv_file(file_name, source, business_id)


def import_gstr3b_file(file_name: str = "gstr3b.csv", business_id: int | None = None) -> int:
    """Guarded entry point for importing a synthetic GSTR-3B fixture."""
    ensure_isolated_demo_seed_allowed(engine)
    assert_schema_at_head(engine)
    return _import_gstr3b_file(file_name, business_id)


def import_all_gst_csv_data() -> dict[str, int]:
    """Seed all GST registers and GSTR returns from synthetic fixtures."""
    ensure_isolated_demo_seed_allowed(engine)
    assert_schema_at_head(engine)
    results = {
        "sales_register.csv": _import_csv_file("sales_register.csv", "sales_register"),
        "gstr1.csv": _import_csv_file("gstr1.csv", "gstr1"),
        "purchase_register.csv": _import_csv_file("purchase_register.csv", "purchase_register"),
        "gstr2a.csv": _import_csv_file("gstr2a.csv", "gstr2a"),
        "gstr2b.csv": _import_csv_file("gstr2b.csv", "gstr2b"),
        "gstr3b.csv": _import_gstr3b_file("gstr3b.csv"),
    }
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    try:
        ensure_isolated_demo_seed_allowed(engine)
        assert_schema_at_head(engine)
        admin_email, _ = get_seed_credentials()
        logger.info("Initializing database with seed admin email: %s", admin_email)
        results = import_all_gst_csv_data()
        logger.info("Database seeding completed successfully: %s", results)
    except Exception as exc:
        logger.error("Database seeding aborted: %s", str(exc))
        sys.exit(1)
