"""Isolated regression coverage for tenant-scoped import batch deletion."""

from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy import event

from database import SessionLocal
from database import get_db
from main import app
from models.models import Business, GSTR3BReturn, ImportBatch, ImportBatchItem, Invoice, User
from services.auth import create_access_token, hash_password


@pytest.fixture
def history_context():
    with SessionLocal() as db:
        user = User(name="History User", email=f"history-{uuid4().hex}@example.test", password=hash_password("Pass123!"))
        other_user = User(name="Other User", email=f"other-{uuid4().hex}@example.test", password=hash_password("Pass123!"))
        db.add_all([user, other_user])
        db.flush()
        business = Business(name="History Business", gstin=f"29{uuid4().hex[:13].upper()}", user_id=user.id)
        other_business = Business(name="Other Business", gstin=f"27{uuid4().hex[:13].upper()}", user_id=other_user.id)
        db.add_all([business, other_business])
        db.commit()
        return {
            "user_id": user.id,
            "business_id": business.id,
            "other_business_id": other_business.id,
            "headers": {
                "Authorization": f"Bearer {create_access_token(user.id, user.email)}",
                "X-Business-ID": str(business.id),
            },
        }


@pytest.fixture
def history_client():
    return TestClient(app)


def _invoice(db, business_id, batch_id=None, invoice_no="HISTORY-001", deleted_at=None):
    row = Invoice(
        invoice_no=invoice_no,
        invoice_date=date(2026, 7, 1),
        gstin="29ABCDE1234F1Z5",
        taxable_value=1000,
        gst_amount=180,
        source="sales_register",
        business_id=business_id,
        import_batch_id=batch_id,
        deleted_at=deleted_at,
    )
    db.add(row)
    db.flush()
    return row


def _batch(db, context, source_type="sales_register"):
    batch = ImportBatch(
        business_id=context["business_id"],
        imported_by_user_id=context["user_id"],
        source_category="csv_upload",
        source_type=source_type,
        original_filename="history.csv",
        total_rows=1,
        imported_rows=1,
        status="completed",
        completed_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.add(batch)
    db.flush()
    return batch


def test_invoice_batch_delete_is_previewed_soft_and_auditable(history_client, history_context):
    with SessionLocal() as db:
        batch = _batch(db, history_context)
        invoice = _invoice(db, history_context["business_id"], batch.batch_id)
        item = ImportBatchItem(batch_id=batch.batch_id, target_record_type="invoice", invoice_id=invoice.id, outcome="imported")
        db.add(item)
        db.commit()
        batch_id, invoice_id = str(batch.batch_id), invoice.id

    preview = history_client.post(f"/imports/batches/{batch_id}/delete-preview", headers=history_context["headers"])
    assert preview.status_code == 200
    assert preview.json()["affected"]["invoice_count"] == 1
    assert preview.json()["message"] == "Preview only. No records were changed."
    with SessionLocal() as db:
        assert db.get(Invoice, invoice_id).deleted_at is None
        assert db.get(ImportBatch, __import__("uuid").UUID(batch_id)).deleted_at is None

    no_confirmation = history_client.post(f"/imports/batches/{batch_id}/delete", json={"confirm": False}, headers=history_context["headers"])
    assert no_confirmation.status_code == 422
    deleted = history_client.post(f"/imports/batches/{batch_id}/delete", json={"confirm": True}, headers=history_context["headers"])
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted_invoice_count"] == 1
    with SessionLocal() as db:
        invoice = db.get(Invoice, invoice_id)
        batch = db.get(ImportBatch, __import__("uuid").UUID(batch_id))
        assert invoice.deleted_at is not None
        assert batch.deleted_at is not None and batch.deleted_by_user_id == history_context["user_id"]
        assert batch.status == "deleted" and len(batch.items) == 1

    assert history_client.get("/invoices", headers=history_context["headers"]).json()["total"] == 0
    assert history_client.get("/reconcile", headers=history_context["headers"]).json()["sales"] == []
    assert history_client.post(f"/imports/batches/{batch_id}/delete", json={"confirm": True}, headers=history_context["headers"]).json()["status"] == "already_deleted"
    assert history_client.get("/imports/batches?include_deleted=true", headers=history_context["headers"]).json()["items"][0]["status"] == "deleted"


def test_batch_detail_and_delete_cannot_access_another_tenant(history_client, history_context):
    with SessionLocal() as db:
        other = ImportBatch(
            business_id=history_context["other_business_id"],
            imported_by_user_id=None,
            source_category="legacy_untracked",
            source_type="unknown",
            total_rows=0,
            status="completed",
        )
        db.add(other)
        db.commit()
        batch_id = str(other.batch_id)
    for suffix in ("", "/delete-preview", "/delete"):
        response = history_client.get(f"/imports/batches/{batch_id}", headers=history_context["headers"]) if not suffix else history_client.post(
            f"/imports/batches/{batch_id}{suffix}",
            json={"confirm": True} if suffix == "/delete" else None,
            headers=history_context["headers"],
        )
        assert response.status_code == 404


def test_duplicate_and_legacy_invoice_references_are_not_deleted(history_client, history_context):
    with SessionLocal() as db:
        owner_batch = _batch(db, history_context)
        invoice = _invoice(db, history_context["business_id"], owner_batch.batch_id, "OWNED-001")
        duplicate_batch = _batch(db, history_context)
        legacy = _invoice(db, history_context["business_id"], None, "LEGACY-001")
        db.add_all([
            ImportBatchItem(batch_id=duplicate_batch.batch_id, target_record_type="invoice", invoice_id=invoice.id, outcome="duplicate"),
            ImportBatchItem(batch_id=duplicate_batch.batch_id, target_record_type="invoice", outcome="rejected", rejection_reason="invalid row"),
        ])
        db.commit()
        batch_id, invoice_id, legacy_id = str(duplicate_batch.batch_id), invoice.id, legacy.id
    preview = history_client.post(f"/imports/batches/{batch_id}/delete-preview", headers=history_context["headers"]).json()
    assert preview["affected"]["invoice_count"] == 0
    response = history_client.post(f"/imports/batches/{batch_id}/delete", json={"confirm": True}, headers=history_context["headers"])
    assert response.status_code == 200
    with SessionLocal() as db:
        assert db.get(Invoice, invoice_id).deleted_at is None
        assert db.get(Invoice, legacy_id).deleted_at is None


@pytest.mark.parametrize(
    ("source_category", "source_type", "reference"),
    [
        ("csv_upload", "purchase_register", "purchase.csv"),
        ("gst_simulator", "gstr1", "gstr1.csv"),
    ],
)
def test_csv_and_simulator_batches_delete_only_their_owned_invoices(
    history_client, history_context, source_category, source_type, reference
):
    with SessionLocal() as db:
        if source_category == "csv_upload":
            batch = _batch(db, history_context, source_type)
        else:
            batch = ImportBatch(
                business_id=history_context["business_id"], imported_by_user_id=history_context["user_id"],
                source_category=source_category, source_type=source_type, fixture_identifier=reference,
                total_rows=1, imported_rows=1, status="completed",
            )
            db.add(batch)
            db.flush()
        invoice = _invoice(db, history_context["business_id"], batch.batch_id, f"{source_type}-owned")
        db.add(ImportBatchItem(batch_id=batch.batch_id, target_record_type="invoice", invoice_id=invoice.id, outcome="imported"))
        db.commit()
        batch_id, invoice_id = str(batch.batch_id), invoice.id
    response = history_client.post(f"/imports/batches/{batch_id}/delete", json={"confirm": True}, headers=history_context["headers"])
    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        assert db.get(Invoice, invoice_id).deleted_at is not None


def test_original_gstr3b_import_is_blocked_until_revision_is_removed(history_client, history_context):
    with SessionLocal() as db:
        original = ImportBatch(
            business_id=history_context["business_id"], imported_by_user_id=history_context["user_id"],
            source_category="gst_simulator", source_type="gstr3b", fixture_identifier="gstr3b.csv",
            tax_period="2026-07", total_rows=1, imported_rows=1, status="completed",
        )
        db.add(original)
        db.flush()
        record = GSTR3BReturn(business_id=history_context["business_id"], tax_period="2026-07", output_tax=200,
                              eligible_itc=50, itc_reversed=5, net_itc=45, import_batch_id=original.batch_id)
        db.add(record)
        db.flush()
        original_item = ImportBatchItem(batch_id=original.batch_id, target_record_type="gstr3b_return", gstr3b_return_id=record.id,
                                        target_period="2026-07", outcome="imported",
                                        new_values={"tax_period": "2026-07", "output_tax": 200, "eligible_itc": 50, "itc_reversed": 5, "net_itc": 45})
        revision = ImportBatch(business_id=history_context["business_id"], imported_by_user_id=history_context["user_id"],
                               source_category="gst_simulator", source_type="gstr3b", fixture_identifier="gstr3b.csv",
                               tax_period="2026-07", total_rows=1, imported_rows=1, status="completed")
        db.add(revision)
        db.flush()
        revision_item = ImportBatchItem(batch_id=revision.batch_id, target_record_type="gstr3b_return", gstr3b_return_id=record.id,
                                        target_period="2026-07", outcome="revised",
                                        previous_values={"tax_period": "2026-07", "output_tax": 200, "eligible_itc": 50, "itc_reversed": 5, "net_itc": 45},
                                        new_values={"tax_period": "2026-07", "output_tax": 250, "eligible_itc": 60, "itc_reversed": 10, "net_itc": 50})
        record.output_tax, record.eligible_itc, record.itc_reversed, record.net_itc = 250, 60, 10, 50
        db.add_all([original_item, revision_item])
        db.commit()
        original_id, revision_id, record_id = str(original.batch_id), str(revision.batch_id), record.id

    blocked = history_client.post(f"/imports/batches/{original_id}/delete-preview", headers=history_context["headers"]).json()
    assert blocked["can_delete"] is False
    assert any("active revisions" in reason for reason in blocked["blocked_reasons"])
    assert history_client.post(f"/imports/batches/{original_id}/delete", json={"confirm": True}, headers=history_context["headers"]).status_code == 409

    reversed_response = history_client.post(f"/imports/batches/{revision_id}/delete", json={"confirm": True}, headers=history_context["headers"])
    assert reversed_response.status_code == 200, reversed_response.text
    with SessionLocal() as db:
        record = db.get(GSTR3BReturn, record_id)
        assert (record.output_tax, record.eligible_itc, record.itc_reversed, record.net_itc) == (200, 50, 5, 45)
        assert str(record.import_batch_id) == original_id
        assert db.scalar(select(ImportBatchItem.id).where(ImportBatchItem.batch_id == __import__("uuid").UUID(revision_id))) is not None
    deleted_original = history_client.post(f"/imports/batches/{original_id}/delete", json={"confirm": True}, headers=history_context["headers"])
    assert deleted_original.status_code == 200, deleted_original.text
    with SessionLocal() as db:
        assert db.get(GSTR3BReturn, record_id).deleted_at is not None
    summary = history_client.get("/gstr3b/summary?tax_period=2026-07", headers=history_context["headers"])
    assert summary.status_code == 200
    assert summary.json()["source"] == "none"
    assert summary.json()["data_available"] is False


def test_deleted_gstr3b_period_can_be_reimported_without_duplicate_period(history_client, history_context):
    with SessionLocal() as db:
        prior_batch = ImportBatch(
            business_id=history_context["business_id"], imported_by_user_id=history_context["user_id"],
            source_category="gst_simulator", source_type="gstr3b", fixture_identifier="gstr3b.csv",
            tax_period="2026-09", total_rows=1, imported_rows=1, status="deleted",
            deleted_at=datetime.now(timezone.utc).replace(tzinfo=None), deleted_by_user_id=history_context["user_id"],
        )
        db.add(prior_batch)
        db.flush()
        record = GSTR3BReturn(
            business_id=history_context["business_id"], tax_period="2026-09", output_tax=100,
            eligible_itc=50, itc_reversed=5, net_itc=45, import_batch_id=prior_batch.batch_id,
            deleted_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db.add(record)
        db.commit()
        record_id, prior_batch_id = record.id, str(prior_batch.batch_id)

    from unittest.mock import patch
    fixture = {"tax_period": "2026-09", "output_tax": 300.0, "eligible_itc": 70.0, "itc_reversed": 10.0, "net_itc": 60.0}
    with patch("routers.gst._fetch_gstr3b_fixture_summary", return_value=fixture):
        response = history_client.post("/gst/gstr3b/import", json={"tax_period": "2026-09"}, headers=history_context["headers"])
    assert response.status_code == 200, response.text
    assert response.json()["operation"] == "new_import"
    with SessionLocal() as db:
        period_rows = db.scalars(select(GSTR3BReturn).where(
            GSTR3BReturn.business_id == history_context["business_id"],
            GSTR3BReturn.tax_period == "2026-09",
        )).all()
        assert len(period_rows) == 1
        assert period_rows[0].id == record_id
        assert period_rows[0].deleted_at is None
        assert str(period_rows[0].import_batch_id) == response.json()["import_batch_id"]
        assert str(period_rows[0].import_batch_id) != prior_batch_id


def test_delete_transaction_failure_rolls_back_records_and_batch(history_client, history_context):
    with SessionLocal() as db:
        batch = _batch(db, history_context)
        invoice = _invoice(db, history_context["business_id"], batch.batch_id, "ROLLBACK-DELETE")
        db.add(ImportBatchItem(batch_id=batch.batch_id, target_record_type="invoice", invoice_id=invoice.id, outcome="imported"))
        db.commit()
        batch_id, invoice_id = str(batch.batch_id), invoice.id

    previous_override = app.dependency_overrides.get(get_db)

    def failing_db():
        session = SessionLocal()

        def fail_commit(_session):
            raise RuntimeError("injected test failure")

        event.listen(session, "before_commit", fail_commit)
        try:
            yield session
        finally:
            event.remove(session, "before_commit", fail_commit)
            session.close()

    app.dependency_overrides[get_db] = failing_db
    try:
        response = history_client.post(
            f"/imports/batches/{batch_id}/delete",
            json={"confirm": True},
            headers=history_context["headers"],
        )
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override

    assert response.status_code == 500
    with SessionLocal() as db:
        assert db.get(Invoice, invoice_id).deleted_at is None
        assert db.get(ImportBatch, __import__("uuid").UUID(batch_id)).deleted_at is None


def test_revision_deletion_refuses_stale_current_values(history_client, history_context):
    with SessionLocal() as db:
        batch = ImportBatch(business_id=history_context["business_id"], imported_by_user_id=history_context["user_id"],
                            source_category="gst_simulator", source_type="gstr3b", fixture_identifier="gstr3b.csv",
                            tax_period="2026-08", total_rows=1, imported_rows=1, status="completed")
        db.add(batch)
        db.flush()
        record = GSTR3BReturn(business_id=history_context["business_id"], tax_period="2026-08", output_tax=999,
                              eligible_itc=60, itc_reversed=5, net_itc=55)
        db.add(record)
        db.flush()
        item = ImportBatchItem(batch_id=batch.batch_id, target_record_type="gstr3b_return", gstr3b_return_id=record.id,
                               target_period="2026-08", outcome="revised",
                               previous_values={"tax_period": "2026-08", "output_tax": 100, "eligible_itc": 60, "itc_reversed": 5, "net_itc": 55},
                               new_values={"tax_period": "2026-08", "output_tax": 200, "eligible_itc": 60, "itc_reversed": 5, "net_itc": 55})
        db.add(item)
        db.commit()
        batch_id = str(batch.batch_id)
    preview = history_client.post(f"/imports/batches/{batch_id}/delete-preview", headers=history_context["headers"]).json()
    assert not preview["can_delete"]
    assert any("changed since" in reason for reason in preview["blocked_reasons"])
    result = history_client.post(f"/imports/batches/{batch_id}/delete", json={"confirm": True}, headers=history_context["headers"])
    assert result.status_code == 409


def test_gstr3b_revisions_must_be_deleted_newest_first(history_client, history_context):
    base_time = datetime.now(timezone.utc).replace(tzinfo=None)
    figures_a = {"tax_period": "2026-07", "output_tax": 100.0, "eligible_itc": 40.0, "itc_reversed": 5.0, "net_itc": 35.0}
    figures_b = {"tax_period": "2026-07", "output_tax": 200.0, "eligible_itc": 50.0, "itc_reversed": 6.0, "net_itc": 44.0}
    figures_c = {"tax_period": "2026-07", "output_tax": 300.0, "eligible_itc": 60.0, "itc_reversed": 7.0, "net_itc": 53.0}
    with SessionLocal() as db:
        batch_a = ImportBatch(
            business_id=history_context["business_id"], imported_by_user_id=history_context["user_id"],
            source_category="gst_simulator", source_type="gstr3b", fixture_identifier="gstr3b.csv",
            tax_period="2026-07", total_rows=1, imported_rows=1, status="completed", created_at=base_time,
        )
        db.add(batch_a)
        db.flush()
        record = GSTR3BReturn(
            business_id=history_context["business_id"], tax_period="2026-07",
            output_tax=figures_a["output_tax"], eligible_itc=figures_a["eligible_itc"],
            itc_reversed=figures_a["itc_reversed"], net_itc=figures_a["net_itc"],
            import_batch_id=batch_a.batch_id,
        )
        db.add(record)
        db.flush()
        item_a = ImportBatchItem(
            batch_id=batch_a.batch_id, target_record_type="gstr3b_return", gstr3b_return_id=record.id,
            target_period="2026-07", outcome="imported", new_values=figures_a,
        )
        batch_b = ImportBatch(
            business_id=history_context["business_id"], imported_by_user_id=history_context["user_id"],
            source_category="gst_simulator", source_type="gstr3b", fixture_identifier="gstr3b.csv",
            tax_period="2026-07", total_rows=1, revised_rows=1, status="completed", created_at=base_time + __import__("datetime").timedelta(seconds=1),
        )
        db.add(batch_b)
        db.flush()
        item_b = ImportBatchItem(
            batch_id=batch_b.batch_id, target_record_type="gstr3b_return", gstr3b_return_id=record.id,
            target_period="2026-07", outcome="revised", previous_values=figures_a, new_values=figures_b,
        )
        batch_c = ImportBatch(
            business_id=history_context["business_id"], imported_by_user_id=history_context["user_id"],
            source_category="gst_simulator", source_type="gstr3b", fixture_identifier="gstr3b.csv",
            tax_period="2026-07", total_rows=1, revised_rows=1, status="completed", created_at=base_time + __import__("datetime").timedelta(seconds=2),
        )
        db.add(batch_c)
        db.flush()
        item_c = ImportBatchItem(
            batch_id=batch_c.batch_id, target_record_type="gstr3b_return", gstr3b_return_id=record.id,
            target_period="2026-07", outcome="revised", previous_values=figures_b, new_values=figures_c,
        )
        record.output_tax = figures_c["output_tax"]
        record.eligible_itc = figures_c["eligible_itc"]
        record.itc_reversed = figures_c["itc_reversed"]
        record.net_itc = figures_c["net_itc"]
        db.add_all([item_a, item_b, item_c])
        db.commit()
        a_id, b_id, c_id, record_id = map(str, (batch_a.batch_id, batch_b.batch_id, batch_c.batch_id, record.id))

    delete_b_early = history_client.post(f"/imports/batches/{b_id}/delete", json={"confirm": True}, headers=history_context["headers"])
    assert delete_b_early.status_code == 409

    delete_c = history_client.post(f"/imports/batches/{c_id}/delete", json={"confirm": True}, headers=history_context["headers"])
    assert delete_c.status_code == 200, delete_c.text
    with SessionLocal() as db:
        restored_b = db.get(GSTR3BReturn, int(record_id))
        assert _snapshot_matches_values(restored_b, figures_b)
        assert str(restored_b.import_batch_id) == a_id

    delete_b = history_client.post(f"/imports/batches/{b_id}/delete", json={"confirm": True}, headers=history_context["headers"])
    assert delete_b.status_code == 200, delete_b.text
    with SessionLocal() as db:
        restored_a = db.get(GSTR3BReturn, int(record_id))
        assert _snapshot_matches_values(restored_a, figures_a)
        assert str(restored_a.import_batch_id) == a_id
        assert all(db.get(ImportBatch, __import__("uuid").UUID(batch_id)) is not None for batch_id in (a_id, b_id, c_id))
        assert db.scalar(select(ImportBatchItem.id).where(ImportBatchItem.batch_id == __import__("uuid").UUID(a_id))) is not None
        item_b_saved = db.scalar(select(ImportBatchItem).where(ImportBatchItem.batch_id == __import__("uuid").UUID(b_id)))
        item_c_saved = db.scalar(select(ImportBatchItem).where(ImportBatchItem.batch_id == __import__("uuid").UUID(c_id)))
        assert item_b_saved.previous_values == figures_a and item_b_saved.new_values == figures_b
        assert item_c_saved.previous_values == figures_b and item_c_saved.new_values == figures_c


def _snapshot_matches_values(record, values):
    return all(
        round(float(getattr(record, field)), 2) == round(float(values[field]), 2)
        for field in ("output_tax", "eligible_itc", "itc_reversed", "net_itc")
    ) and record.tax_period == values["tax_period"]


def test_batch_filtering_and_pagination_are_tenant_scoped(history_client, history_context):
    with SessionLocal() as db:
        for source in ("sales_register", "gstr1", "gstr2a"):
            db.add(_batch(db, history_context, source))
        db.commit()
    page = history_client.get("/imports/batches?limit=2&offset=0&source_type=gstr1", headers=history_context["headers"])
    assert page.status_code == 200
    assert page.json()["total"] == 1
    assert len(page.json()["items"]) == 1
    assert page.json()["items"][0]["source_type"] == "gstr1"
