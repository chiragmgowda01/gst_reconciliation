"""Model-level tests for the import audit schema on the isolated test DB."""

from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from database import SessionLocal
from models.models import Business, GSTR3BReturn, ImportBatch, ImportBatchItem, Invoice, User


def _make_business(session, suffix="one"):
    user = User(
        name=f"Import User {suffix}",
        email=f"import-{suffix}-{uuid4().hex}@example.test",
        password="test-hash",
    )
    session.add(user)
    session.flush()
    business = Business(
        name=f"Import Business {suffix}",
        gstin=f"29{uuid4().hex[:13].upper()}",
        user_id=user.id,
    )
    session.add(business)
    session.flush()
    return user, business


def _csv_batch(user, business, batch_id=None, filename=r"C:\private\upload\returns.csv"):
    return ImportBatch(
        batch_id=batch_id or uuid4(),
        business_id=business.id,
        imported_by_user_id=user.id,
        source_category="csv_upload",
        source_type="gstr1",
        original_filename=filename,
        total_rows=4,
        imported_rows=2,
        duplicate_rows=1,
        rejected_rows=1,
        status="partial",
        completed_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )


def test_import_batch_creation_records_owner_counts_and_sanitized_filename():
    with SessionLocal() as session:
        user, business = _make_business(session)
        batch = _csv_batch(user, business)
        session.add(batch)
        session.commit()

        stored = session.get(ImportBatch, batch.batch_id)
        assert stored is not None
        assert stored.business_id == business.id
        assert stored.imported_by_user_id == user.id
        assert stored.business.id == business.id
        assert stored.imported_by.id == user.id
        assert stored.original_filename == "returns.csv"
        assert stored.fixture_identifier is None
        assert (stored.total_rows, stored.imported_rows, stored.duplicate_rows, stored.rejected_rows) == (4, 2, 1, 1)
        assert stored.status == "partial"


def test_import_batch_id_is_unique_uuid_primary_key():
    with SessionLocal() as session:
        user, business = _make_business(session)
        batch_id = uuid4()
        session.add(_csv_batch(user, business, batch_id=batch_id))
        session.commit()

        session.add(_csv_batch(user, business, batch_id=batch_id))
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()


def test_import_batch_item_relationship_retains_gstr3b_revision_values():
    with SessionLocal() as session:
        user, business = _make_business(session)
        batch = ImportBatch(
            batch_id=uuid4(),
            business_id=business.id,
            imported_by_user_id=user.id,
            source_category="gst_simulator",
            source_type="gstr3b",
            fixture_identifier="gstr3b.csv",
            tax_period="2026-07",
            total_rows=1,
            imported_rows=1,
            status="completed",
        )
        returned = GSTR3BReturn(
            business_id=business.id,
            tax_period="2026-07",
            output_tax=110.0,
            eligible_itc=42.0,
            itc_reversed=2.0,
            net_itc=40.0,
        )
        session.add(returned)
        session.flush()
        batch.items.append(
            ImportBatchItem(
                target_record_type="gstr3b_return",
                gstr3b_return_id=returned.id,
                target_period="2026-07",
                outcome="revised",
                previous_values={"output_tax": 100.0, "eligible_itc": 40.0},
                new_values={"output_tax": 110.0, "eligible_itc": 42.0},
            )
        )
        session.add(batch)
        session.commit()

        stored = session.get(ImportBatch, batch.batch_id)
        assert stored is not None
        assert len(stored.items) == 1
        assert stored.items[0].batch_id == batch.batch_id
        assert stored.items[0].target_period == "2026-07"
        assert stored.items[0].gstr3b_return_id == returned.id
        assert stored.items[0].gstr3b_return.id == returned.id
        assert stored.items[0].outcome == "revised"
        assert stored.items[0].previous_values["output_tax"] == 100.0
        assert stored.items[0].new_values["output_tax"] == 110.0


def test_unassociated_existing_invoice_is_explicitly_legacy_untracked():
    with SessionLocal() as session:
        _user, business = _make_business(session)
        invoice = Invoice(
            invoice_no="OLD-001",
            invoice_date=date(2026, 7, 5),
            gstin="29ABCDE1234F1Z5",
            taxable_value=100.0,
            gst_amount=18.0,
            source="sales_register",
            business_id=business.id,
        )
        session.add(invoice)
        session.commit()

        stored = session.get(Invoice, invoice.id)
        assert stored is not None
        assert stored.import_batch_id is None
        assert stored.import_tracking_status == "legacy_untracked"


def test_gstr3b_soft_delete_reimport_reuses_one_unique_period_row():
    with SessionLocal() as session:
        _user, business = _make_business(session)
        returned = GSTR3BReturn(
            business_id=business.id,
            tax_period="2026-07",
            output_tax=100.0,
            eligible_itc=40.0,
            itc_reversed=2.0,
            net_itc=38.0,
        )
        session.add(returned)
        session.commit()
        assert returned.import_batch_id is None
        assert returned.import_tracking_status == "legacy_untracked"

        # Audited deletion archives the canonical row. A future re-import should
        # reactivate/update this row rather than insert a second row for the period.
        returned.deleted_at = datetime.now(timezone.utc).replace(tzinfo=None)
        session.commit()
        with pytest.raises(IntegrityError):
            session.add(
                GSTR3BReturn(
                    business_id=business.id,
                    tax_period="2026-07",
                    output_tax=110.0,
                    eligible_itc=42.0,
                    itc_reversed=2.0,
                    net_itc=40.0,
                )
            )
            session.flush()
        session.rollback()

        restored = session.scalar(
            select(GSTR3BReturn).where(
                GSTR3BReturn.business_id == business.id,
                GSTR3BReturn.tax_period == "2026-07",
            )
        )
        assert restored is not None
        restored.deleted_at = None
        restored.output_tax = 110.0
        session.commit()
        assert session.scalar(
            select(func.count(GSTR3BReturn.id)).where(
                GSTR3BReturn.business_id == business.id,
                GSTR3BReturn.tax_period == "2026-07",
            )
        ) == 1
