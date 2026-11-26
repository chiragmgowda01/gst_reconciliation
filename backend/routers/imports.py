"""Tenant-scoped import history and auditable batch soft deletion."""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from database import get_db
from models.models import Business, GSTR3BReturn, ImportBatch, ImportBatchItem, Invoice, User
from services.auth import get_current_business, get_current_user

router = APIRouter(prefix="/imports", tags=["Import history"])


class DeleteConfirmation(BaseModel):
    confirm: bool = False


_GSTR3B_FIELDS = ("tax_period", "output_tax", "eligible_itc", "itc_reversed", "net_itc")


def _batch_for_tenant(db: Session, batch_id: UUID, business_id: int, *, lock: bool = False):
    query = select(ImportBatch).where(
        ImportBatch.batch_id == batch_id,
        ImportBatch.business_id == business_id,
    )
    if lock:
        query = query.with_for_update()
    batch = db.scalar(query)
    if batch is None:
        # Use 404 for both missing and another tenant's batch to avoid disclosure.
        raise HTTPException(status_code=404, detail="Import batch not found.")
    return batch


def _serialize_batch(batch: ImportBatch, *, include_items: bool = False) -> dict[str, Any]:
    result = {
        "batch_id": str(batch.batch_id),
        "business_id": batch.business_id,
        "imported_by_user_id": batch.imported_by_user_id,
        "source_category": batch.source_category,
        "source_type": batch.source_type,
        "original_filename": batch.original_filename,
        "fixture_identifier": batch.fixture_identifier,
        "tax_period": batch.tax_period,
        "total_rows": batch.total_rows,
        "imported_rows": batch.imported_rows,
        "duplicate_rows": batch.duplicate_rows,
        "revised_rows": batch.revised_rows,
        "rejected_rows": batch.rejected_rows,
        "created_at": batch.created_at.isoformat() if batch.created_at else None,
        "completed_at": batch.completed_at.isoformat() if batch.completed_at else None,
        "status": batch.status,
        "deleted_at": batch.deleted_at.isoformat() if batch.deleted_at else None,
        "deleted_by_user_id": batch.deleted_by_user_id,
    }
    if include_items:
        result["items"] = [
            {
                "id": item.id,
                "target_record_type": item.target_record_type,
                "invoice_id": item.invoice_id,
                "gstr3b_return_id": item.gstr3b_return_id,
                "target_period": item.target_period,
                "outcome": item.outcome,
                "previous_values": item.previous_values,
                "new_values": item.new_values,
                "rejection_reason": item.rejection_reason,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in batch.items
        ]
    return result


def _item_return(db: Session, item: ImportBatchItem, business_id: int, *, lock: bool = False):
    query = select(GSTR3BReturn).where(
        GSTR3BReturn.id == item.gstr3b_return_id,
        GSTR3BReturn.business_id == business_id,
        GSTR3BReturn.tax_period == item.target_period,
    )
    if lock:
        query = query.with_for_update()
    return db.scalar(query)


def _snapshot_matches(record: GSTR3BReturn, snapshot: dict | None) -> bool:
    if not snapshot or any(field not in snapshot for field in _GSTR3B_FIELDS):
        return False
    for field in _GSTR3B_FIELDS:
        actual = getattr(record, field)
        expected = snapshot[field]
        if field == "tax_period":
            if str(actual) != str(expected):
                return False
        elif round(float(actual), 2) != round(float(expected), 2):
            return False
    return True


def _complete_snapshot(snapshot: dict | None) -> bool:
    return bool(snapshot) and all(field in snapshot for field in _GSTR3B_FIELDS)


def _deletion_plan(
    db: Session, batch: ImportBatch, business_id: int, *, lock: bool = False
) -> dict[str, Any]:
    invoice_query = select(Invoice).where(
            Invoice.business_id == business_id,
            Invoice.import_batch_id == batch.batch_id,
            Invoice.deleted_at.is_(None),
        )
    if lock:
        invoice_query = invoice_query.with_for_update()
    invoices = db.scalars(invoice_query).all()
    imported_returns: list[dict[str, Any]] = []
    revisions: list[dict[str, Any]] = []
    blocked: list[str] = []

    items = db.scalars(
        select(ImportBatchItem).where(ImportBatchItem.batch_id == batch.batch_id)
    ).all()
    for item in items:
        if item.target_record_type != "gstr3b_return" or item.outcome not in {"imported", "revised"}:
            continue
        record = _item_return(db, item, business_id, lock=lock)
        if item.outcome == "imported":
            if record is not None and record.deleted_at is None and record.import_batch_id == batch.batch_id:
                imported_returns.append({"id": record.id, "tax_period": record.tax_period})
            elif record is not None and record.deleted_at is None:
                blocked.append(
                    f"GSTR-3B {item.target_period} has a newer active import. Reverse newer revisions first."
                )
        elif item.outcome == "revised":
            if record is None or record.deleted_at is not None:
                blocked.append(f"GSTR-3B {item.target_period} is no longer active, so this revision cannot be restored safely.")
                continue
            if not _snapshot_matches(record, item.new_values):
                blocked.append(f"GSTR-3B {item.target_period} has changed since this revision; restoration was blocked.")
                continue
            newer_revision = db.scalar(
                select(ImportBatchItem.id)
                .join(ImportBatch, ImportBatch.batch_id == ImportBatchItem.batch_id)
                .where(
                    ImportBatchItem.target_record_type == "gstr3b_return",
                    ImportBatchItem.outcome == "revised",
                    ImportBatchItem.gstr3b_return_id == record.id,
                    ImportBatch.created_at > batch.created_at,
                    ImportBatch.deleted_at.is_(None),
                )
                .limit(1)
            )
            if newer_revision is not None:
                blocked.append(f"GSTR-3B {item.target_period} has a newer active revision. Reverse revisions in newest-first order.")
            elif not _complete_snapshot(item.previous_values):
                blocked.append(f"GSTR-3B {item.target_period} has no complete prior snapshot; restoration was blocked.")
            else:
                revisions.append({"item_id": item.id, "id": record.id, "tax_period": record.tax_period})

    # Deleting an original import while any active revision depends on it would
    # remove the canonical period row needed for auditable restoration.
    if imported_returns:
        for record_info in imported_returns:
            active_revision = db.scalar(
                select(ImportBatchItem.id)
                .join(ImportBatch, ImportBatch.batch_id == ImportBatchItem.batch_id)
                .where(
                    ImportBatchItem.target_record_type == "gstr3b_return",
                    ImportBatchItem.outcome == "revised",
                    ImportBatchItem.gstr3b_return_id == record_info["id"],
                    ImportBatch.deleted_at.is_(None),
                )
                .limit(1)
            )
            if active_revision is not None:
                blocked.append(f"GSTR-3B {record_info['tax_period']} has active revisions. Delete those revisions first.")

    return {
        "invoice_count": len(invoices),
        "invoice_ids": [invoice.id for invoice in invoices],
        "gstr3b_originals": imported_returns,
        "gstr3b_revisions": revisions,
        "blocked_reasons": list(dict.fromkeys(blocked)),
        "can_delete": not blocked,
    }


@router.get("/batches")
def list_import_batches(
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    source_type: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    include_deleted: bool = False,
    business: Business = Depends(get_current_business),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = select(ImportBatch).where(ImportBatch.business_id == business.id)
    if source_type:
        query = query.where(ImportBatch.source_type == source_type)
    if status_filter:
        query = query.where(ImportBatch.status == status_filter)
    if not include_deleted:
        query = query.where(ImportBatch.deleted_at.is_(None))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    batches = db.scalars(
        query.order_by(ImportBatch.created_at.desc(), ImportBatch.batch_id.desc())
        .offset(offset).limit(limit)
    ).all()
    return {"items": [_serialize_batch(batch) for batch in batches], "total": total, "limit": limit, "offset": offset}


@router.get("/batches/{batch_id}")
def get_import_batch(
    batch_id: UUID,
    business: Business = Depends(get_current_business),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    batch = db.scalar(
        select(ImportBatch).options(selectinload(ImportBatch.items)).where(
            ImportBatch.batch_id == batch_id,
            ImportBatch.business_id == business.id,
        )
    )
    if batch is None:
        raise HTTPException(status_code=404, detail="Import batch not found.")
    return _serialize_batch(batch, include_items=True)


@router.post("/batches/{batch_id}/delete-preview")
def preview_batch_deletion(
    batch_id: UUID,
    business: Business = Depends(get_current_business),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    batch = _batch_for_tenant(db, batch_id, business.id)
    if batch.deleted_at is not None:
        return {"status": "already_deleted", "can_delete": True, "message": "This batch was already deleted; its audit history remains available."}
    plan = _deletion_plan(db, batch, business.id)
    return {
        "status": "preview",
        "batch": _serialize_batch(batch),
        "can_delete": plan["can_delete"],
        "affected": {
            "invoice_count": plan["invoice_count"],
            "invoice_ids": plan["invoice_ids"],
            "gstr3b_originals": plan["gstr3b_originals"],
            "gstr3b_revisions": plan["gstr3b_revisions"],
            "audit_records_retained": True,
        },
        "blocked_reasons": plan["blocked_reasons"],
        "message": "Preview only. No records were changed.",
    }


@router.post("/batches/{batch_id}/delete")
def delete_import_batch(
    batch_id: UUID,
    confirmation: DeleteConfirmation,
    business: Business = Depends(get_current_business),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not confirmation.confirm:
        raise HTTPException(status_code=422, detail="Explicit confirmation is required.")
    try:
        batch = _batch_for_tenant(db, batch_id, business.id, lock=True)
        if batch.deleted_at is not None:
            return {"status": "already_deleted", "batch_id": str(batch.batch_id), "message": "This batch was already deleted; audit history was retained."}
        plan = _deletion_plan(db, batch, business.id, lock=True)
        if not plan["can_delete"]:
            raise HTTPException(status_code=409, detail={"message": "This batch cannot be deleted safely.", "blocked_reasons": plan["blocked_reasons"]})

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for invoice_id in plan["invoice_ids"]:
            invoice = db.scalar(
                select(Invoice).where(
                    Invoice.id == invoice_id,
                    Invoice.business_id == business.id,
                    Invoice.import_batch_id == batch.batch_id,
                    Invoice.deleted_at.is_(None),
                ).with_for_update()
            )
            if invoice is not None:
                invoice.deleted_at = now

        items = db.scalars(select(ImportBatchItem).where(ImportBatchItem.batch_id == batch.batch_id)).all()
        for item in items:
            if item.target_record_type != "gstr3b_return" or item.outcome not in {"imported", "revised"}:
                continue
            record = _item_return(db, item, business.id, lock=True)
            if record is None:
                continue
            if item.outcome == "imported":
                if record.deleted_at is None and record.import_batch_id == batch.batch_id:
                    record.deleted_at = now
            elif record.deleted_at is None and _snapshot_matches(record, item.new_values):
                for field in _GSTR3B_FIELDS:
                    setattr(record, field, item.previous_values[field])
                # Original import association intentionally remains unchanged.

        batch.deleted_at = now
        batch.deleted_by_user_id = user.id
        batch.status = "deleted"
        db.commit()
        return {
            "status": "deleted",
            "batch_id": str(batch.batch_id),
            "deleted_invoice_count": plan["invoice_count"],
            "deleted_gstr3b_count": len(plan["gstr3b_originals"]),
            "restored_gstr3b_revisions": len(plan["gstr3b_revisions"]),
            "audit_records_retained": True,
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="The import batch could not be deleted. No changes were saved.") from None
