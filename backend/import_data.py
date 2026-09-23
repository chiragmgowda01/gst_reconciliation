from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from database import SessionLocal
from models.base import Base
from models.models import Business, Invoice, User

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def ensure_user(session) -> User:
    user = session.scalar(select(User).where(User.email == "default@gst.local"))
    if user is None:
        user = User(name="Default User", email="default@gst.local", password="changeme")
        session.add(user)
        session.flush()
    return user


def ensure_business(session, gstin: str, business_name: str | None = None) -> Business:
    business = session.scalar(select(Business).where(Business.gstin == gstin))
    if business is None:
        user = ensure_user(session)
        business = Business(name=business_name or gstin, gstin=gstin, user_id=user.id)
        session.add(business)
        session.flush()
    return business


def import_csv_file(file_name: str, source: str) -> int:
    session = SessionLocal()
    try:
        file_path = DATA / file_name
        df = pd.read_csv(file_path)

        if df.empty:
            return 0

        imported = 0
        for _, row in df.iterrows():
            invoice_no = str(row["invoice_no"]).strip()
            invoice_date = pd.to_datetime(row["invoice_date"]).date()
            gstin = str(row.get("customer_gstin") or row.get("supplier_gstin") or "").strip()
            taxable_value = float(row["taxable_value"])
            gst_amount = float(row["gst_amount"])

            existing = session.scalar(
                select(Invoice).where(
                    Invoice.invoice_no == invoice_no,
                    Invoice.gstin == gstin,
                    Invoice.source == source,
                )
            )
            if existing is not None:
                continue

            business = ensure_business(session, gstin)

            invoice = Invoice(
                invoice_no=invoice_no,
                invoice_date=invoice_date,
                gstin=gstin,
                taxable_value=taxable_value,
                gst_amount=gst_amount,
                source=source,
                business_id=business.id,
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


def import_all_gst_csv_data() -> dict[str, int]:
    results = {
        "sales_register.csv": import_csv_file("sales_register.csv", "sales_register"),
        "gstr1.csv": import_csv_file("gstr1.csv", "gstr1"),
        "purchase_register.csv": import_csv_file("purchase_register.csv", "purchase_register"),
        "gstr2a.csv": import_csv_file("gstr2a.csv", "gstr2a"),
    }
    return results


if __name__ == "__main__":
    Base.metadata.create_all(bind=SessionLocal().bind)
    print(import_all_gst_csv_data())
