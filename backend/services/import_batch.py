"""Small transaction-neutral helpers for recording invoice import outcomes."""

from datetime import datetime, timezone
import sqlite3
import uuid

from sqlalchemy.orm import Session

from models.models import ImportBatch, ImportBatchItem


def is_unique_constraint_violation(error: Exception) -> bool:
    """Identify uniqueness conflicts without exposing driver error details."""
    original = getattr(error, "orig", None)
    if original is None:
        return False
    sqlstate = getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)
    if sqlstate == "23505":
        return True
    if isinstance(original, sqlite3.IntegrityError):
        error_code = getattr(original, "sqlite_errorcode", None)
        unique_codes = {
            getattr(sqlite3, "SQLITE_CONSTRAINT_UNIQUE", -1),
            getattr(sqlite3, "SQLITE_CONSTRAINT_PRIMARYKEY", -1),
        }
        return error_code in unique_codes or "UNIQUE constraint failed" in str(original)
    return False


def create_import_batch(
    db: Session,
    *,
    business_id: int,
    imported_by_user_id: int,
    source_category: str,
    source_type: str,
    total_rows: int,
    original_filename: str | None = None,
    fixture_identifier: str | None = None,
    tax_period: str | None = None,
) -> ImportBatch:
    batch = ImportBatch(
        batch_id=uuid.uuid4(),
        business_id=business_id,
        imported_by_user_id=imported_by_user_id,
        source_category=source_category,
        source_type=source_type,
        original_filename=original_filename,
        fixture_identifier=fixture_identifier,
        tax_period=tax_period,
        total_rows=total_rows,
        status="in_progress",
    )
    db.add(batch)
    db.flush()
    return batch


def add_invoice_batch_item(
    db: Session,
    *,
    batch_id: uuid.UUID,
    outcome: str,
    invoice_id: int | None = None,
    rejection_reason: str | None = None,
) -> ImportBatchItem:
    item = ImportBatchItem(
        batch_id=batch_id,
        target_record_type="invoice",
        invoice_id=invoice_id,
        outcome=outcome,
        rejection_reason=(rejection_reason[:500] if rejection_reason else None),
    )
    db.add(item)
    return item


def add_gstr3b_batch_item(
    db: Session,
    *,
    batch_id: uuid.UUID,
    outcome: str,
    tax_period: str,
    gstr3b_return_id: int | None,
    previous_values: dict | None = None,
    new_values: dict | None = None,
    rejection_reason: str | None = None,
) -> ImportBatchItem:
    """Record an imported or revised monthly GSTR-3B summary in batch history."""
    item = ImportBatchItem(
        batch_id=batch_id,
        target_record_type="gstr3b_return",
        gstr3b_return_id=gstr3b_return_id,
        target_period=tax_period,
        outcome=outcome,
        previous_values=previous_values,
        new_values=new_values,
        rejection_reason=(rejection_reason[:500] if rejection_reason else None),
    )
    db.add(item)
    return item


def complete_import_batch(
    batch: ImportBatch,
    *,
    imported_rows: int,
    duplicate_rows: int,
    rejected_rows: int,
    revised_rows: int = 0,
) -> None:
    batch.imported_rows = imported_rows
    batch.duplicate_rows = duplicate_rows
    batch.revised_rows = revised_rows
    batch.rejected_rows = rejected_rows
    batch.status = (
        "failed"
        if rejected_rows and not imported_rows and not duplicate_rows and not revised_rows
        else "partial"
        if rejected_rows
        else "completed"
    )
    batch.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
