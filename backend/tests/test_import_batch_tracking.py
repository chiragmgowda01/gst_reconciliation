"""Import batch tracking through authenticated invoice upload and simulator APIs."""

from datetime import date, datetime, timezone
import sqlite3
from uuid import UUID, uuid4
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import SessionLocal, get_db
from main import app
from models.models import Business, GSTR3BReturn, ImportBatch, ImportBatchItem, Invoice, User
from services.auth import create_access_token, hash_password


@pytest.fixture
def import_context():
    db = SessionLocal()
    user = User(
        name="Batch Test User",
        email=f"batch-{uuid4().hex}@example.test",
        password=hash_password("Pass123!"),
    )
    db.add(user)
    db.flush()
    business = Business(
        name="Batch Test Business",
        gstin=f"29{uuid4().hex[:13].upper()}",
        user_id=user.id,
    )
    db.add(business)
    db.commit()
    result = {
        "user_id": user.id,
        "business_id": business.id,
        "headers": {
            "Authorization": f"Bearer {create_access_token(user.id, user.email)}",
            "X-Business-ID": str(business.id),
        },
    }
    db.close()
    return result


@pytest.fixture
def client():
    return TestClient(app)


def _upload(client, headers, *, filename="batch.csv", source="sales_register", content=None, extra_data=None):
    if content is None:
        content = (
            "invoice_no,gstin,invoice_date,taxable_value,gst_amount\n"
            "CSV-TRACK-001,29ABCDE1234F1Z5,2026-07-01,1000,180\n"
        )
    data = {"source_type": source, **(extra_data or {})}
    return client.post(
        "/invoices/upload",
        files={"file": (filename, content.encode("utf-8"), "text/csv")},
        data=data,
        headers=headers,
    )


def _session():
    return SessionLocal()


def _batch_uuid(value):
    return UUID(str(value))


def _gstr3b_csv(*rows):
    return "tax_period,output_tax,eligible_itc,itc_reversed,net_itc\n" + "".join(
        f"{period},{output_tax},{eligible_itc},{itc_reversed},{net_itc}\n"
        for period, output_tax, eligible_itc, itc_reversed, net_itc in rows
    )


def test_csv_upload_creates_batch_with_authenticated_owner_and_sanitized_filename(client, import_context):
    response = _upload(
        client,
        import_context["headers"],
        filename=r"C:\private\uploads\sales.csv",
    )
    assert response.status_code == 200, response.text
    batch_id = response.json()["import_batch_id"]

    with _session() as db:
        batch = db.get(ImportBatch, _batch_uuid(batch_id))
        invoice = db.scalar(select(Invoice).where(Invoice.invoice_no == "CSV-TRACK-001"))
        assert batch is not None
        assert batch.business_id == import_context["business_id"]
        assert batch.imported_by_user_id == import_context["user_id"]
        assert batch.source_category == "csv_upload"
        assert batch.source_type == "sales_register"
        assert batch.original_filename == "sales.csv"
        assert batch.fixture_identifier is None
        assert (batch.total_rows, batch.imported_rows, batch.duplicate_rows, batch.rejected_rows) == (1, 1, 0, 0)
        assert batch.completed_at is not None
        assert invoice is not None
        assert invoice.business_id == batch.business_id
        assert invoice.import_batch_id == batch.batch_id
        assert len(batch.items) == 1
        assert batch.items[0].outcome == "imported"
        assert batch.items[0].invoice_id == invoice.id


def test_gstr3b_csv_tracks_new_duplicate_revision_restore_and_reactivation(client, import_context):
    first = _upload(
        client, import_context["headers"], source="gstr3b",
        content=_gstr3b_csv(("2026-07", 100, 50, 5, 45)),
    )
    assert first.status_code == 200, first.text
    first_data = first.json()
    assert first_data["status"] == "completed"
    assert (first_data["imported"], first_data["duplicates"], first_data["revised"], first_data["rejected"]) == (1, 0, 0, 0)

    with _session() as db:
        original_batch = db.get(ImportBatch, _batch_uuid(first_data["import_batch_id"]))
        record = db.scalar(select(GSTR3BReturn).where(
            GSTR3BReturn.business_id == import_context["business_id"],
            GSTR3BReturn.tax_period == "2026-07",
        ))
        assert original_batch is not None
        assert original_batch.source_category == "csv_upload"
        assert original_batch.source_type == "gstr3b"
        assert original_batch.imported_by_user_id == import_context["user_id"]
        assert original_batch.tax_period == "2026-07"
        assert original_batch.revised_rows == 0
        assert record.import_batch_id == original_batch.batch_id
        assert len(original_batch.items) == 1 and original_batch.items[0].outcome == "imported"
        record_id = record.id

    duplicate = _upload(
        client, import_context["headers"], source="gstr3b",
        content=_gstr3b_csv(("2026-07", 100, 50, 5, 45)),
    )
    assert duplicate.status_code == 200, duplicate.text
    duplicate_data = duplicate.json()
    assert (duplicate_data["imported"], duplicate_data["duplicates"], duplicate_data["revised"]) == (0, 1, 0)
    with _session() as db:
        unchanged = db.get(GSTR3BReturn, record_id)
        duplicate_batch = db.get(ImportBatch, _batch_uuid(duplicate_data["import_batch_id"]))
        assert unchanged.import_batch_id == _batch_uuid(first_data["import_batch_id"])
        assert duplicate_batch.items[0].outcome == "duplicate"
        duplicate_batch_id = str(duplicate_batch.batch_id)
    assert client.post(
        f"/imports/batches/{duplicate_batch_id}/delete",
        json={"confirm": True}, headers=import_context["headers"],
    ).status_code == 200
    with _session() as db:
        assert db.get(GSTR3BReturn, record_id).deleted_at is None

    revision = _upload(
        client, import_context["headers"], source="gstr3b",
        content=_gstr3b_csv(("2026-07", 200, 70, 10, 60)),
    )
    assert revision.status_code == 200, revision.text
    revision_data = revision.json()
    assert (revision_data["imported"], revision_data["revised"], revision_data["duplicates"]) == (0, 1, 0)
    with _session() as db:
        revision_batch = db.get(ImportBatch, _batch_uuid(revision_data["import_batch_id"]))
        revised_record = db.get(GSTR3BReturn, record_id)
        assert revision_batch.revised_rows == 1
        assert revision_batch.items[0].outcome == "revised"
        assert revision_batch.items[0].previous_values == {
            "tax_period": "2026-07", "output_tax": 100.0, "eligible_itc": 50.0,
            "itc_reversed": 5.0, "net_itc": 45.0,
        }
        assert revision_batch.items[0].new_values == {
            "tax_period": "2026-07", "output_tax": 200.0, "eligible_itc": 70.0,
            "itc_reversed": 10.0, "net_itc": 60.0,
        }
        assert revised_record.output_tax == 200
        assert revised_record.import_batch_id == _batch_uuid(first_data["import_batch_id"])
        original_batch_id = str(revised_record.import_batch_id)

    blocked = client.post(
        f"/imports/batches/{original_batch_id}/delete-preview",
        headers=import_context["headers"],
    )
    assert blocked.status_code == 200 and blocked.json()["can_delete"] is False
    restored = client.post(
        f"/imports/batches/{revision_data['import_batch_id']}/delete",
        json={"confirm": True}, headers=import_context["headers"],
    )
    assert restored.status_code == 200, restored.text
    with _session() as db:
        restored_record = db.get(GSTR3BReturn, record_id)
        assert restored_record.output_tax == 100
        assert restored_record.import_batch_id == _batch_uuid(first_data["import_batch_id"])
        assert db.get(ImportBatch, _batch_uuid(revision_data["import_batch_id"])).items[0].previous_values is not None

    deleted_original = client.post(
        f"/imports/batches/{original_batch_id}/delete",
        json={"confirm": True}, headers=import_context["headers"],
    )
    assert deleted_original.status_code == 200, deleted_original.text
    reimport = _upload(
        client, import_context["headers"], source="gstr3b",
        content=_gstr3b_csv(("2026-07", 300, 90, 15, 75)),
    )
    assert reimport.status_code == 200, reimport.text
    reimport_data = reimport.json()
    assert reimport_data["imported"] == 1
    with _session() as db:
        period_records = db.scalars(select(GSTR3BReturn).where(
            GSTR3BReturn.business_id == import_context["business_id"],
            GSTR3BReturn.tax_period == "2026-07",
        )).all()
        assert len(period_records) == 1
        assert period_records[0].deleted_at is None
        assert period_records[0].output_tax == 300
        assert period_records[0].import_batch_id == _batch_uuid(reimport_data["import_batch_id"])
        assert db.scalar(select(Invoice.id)) is None


def test_gstr3b_csv_conflicting_duplicate_period_rolls_back_batch_and_rows(client, import_context):
    response = _upload(
        client, import_context["headers"], source="gstr3b",
        content=_gstr3b_csv(
            ("2026-07", 100, 50, 5, 45),
            ("2026-07", 120, 50, 5, 45),
        ),
    )
    assert response.status_code == 422
    with _session() as db:
        assert db.scalar(select(ImportBatch.batch_id).where(
            ImportBatch.business_id == import_context["business_id"],
        )) is None
        assert db.scalar(select(GSTR3BReturn.id).where(
            GSTR3BReturn.business_id == import_context["business_id"],
        )) is None


def test_identical_duplicate_periods_in_one_gstr3b_csv_create_one_return(client, import_context):
    response = _upload(
        client, import_context["headers"], source="gstr3b",
        content=_gstr3b_csv(
            ("2026-07", 100, 50, 5, 45),
            ("2026-07", 100, 50, 5, 45),
        ),
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert (data["imported"], data["duplicates"], data["revised"], data["rejected"]) == (1, 1, 0, 0)
    with _session() as db:
        rows = db.scalars(select(GSTR3BReturn).where(GSTR3BReturn.tax_period == "2026-07")).all()
        batch = db.get(ImportBatch, _batch_uuid(data["import_batch_id"]))
        items = db.scalars(
            select(ImportBatchItem)
            .where(ImportBatchItem.batch_id == batch.batch_id)
            .order_by(ImportBatchItem.id)
        ).all()
        assert len(rows) == 1
        assert batch.total_rows == 2
        assert batch.imported_rows == 1 and batch.duplicate_rows == 1
        assert [item.outcome for item in items] == ["imported", "duplicate"]


def test_gstr3b_csv_integrity_conflict_rolls_back_batch_and_period(client, import_context):
    previous_override = app.dependency_overrides.get(get_db)

    def integrity_failure_db():
        session = SessionLocal()

        def fail_commit(_session):
            raise IntegrityError(
                "insert into gstr3b_returns",
                {},
                sqlite3.IntegrityError("UNIQUE constraint failed: gstr3b_returns.business_id, gstr3b_returns.tax_period"),
            )

        event.listen(session, "before_commit", fail_commit)
        try:
            yield session
        finally:
            event.remove(session, "before_commit", fail_commit)
            session.close()

    app.dependency_overrides[get_db] = integrity_failure_db
    try:
        response = _upload(
            client, import_context["headers"], source="gstr3b",
            content=_gstr3b_csv(("2026-07", 100, 50, 5, 45)),
        )
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override

    assert response.status_code == 409
    assert "UNIQUE constraint failed" not in response.text
    with _session() as db:
        assert db.scalar(select(ImportBatch.batch_id)) is None
        assert db.scalar(select(GSTR3BReturn.id)) is None


def test_all_rejected_gstr3b_csv_has_failed_auditable_batch(client, import_context):
    response = _upload(
        client, import_context["headers"], source="gstr3b",
        content="tax_period,output_tax,eligible_itc,itc_reversed,net_itc\n2026-07,-1,50,5,45\n",
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "failed"
    assert (data["imported"], data["duplicates"], data["revised"], data["rejected"]) == (0, 0, 0, 1)
    with _session() as db:
        batch = db.get(ImportBatch, _batch_uuid(data["import_batch_id"]))
        assert batch.status == "failed"
        assert batch.rejected_rows == 1 and batch.revised_rows == 0
        assert len(batch.items) == 1 and batch.items[0].outcome == "rejected"
        assert db.scalar(select(GSTR3BReturn.id)) is None


def test_header_only_gstr3b_csv_creates_no_batch(client, import_context):
    response = _upload(
        client, import_context["headers"], source="gstr3b",
        content="tax_period,output_tax,eligible_itc,itc_reversed,net_itc\n",
    )
    assert response.status_code == 422
    with _session() as db:
        assert db.scalar(select(ImportBatch.batch_id)) is None
        assert db.scalar(select(GSTR3BReturn.id)) is None


@pytest.mark.parametrize(
    ("content", "expected_detail"),
    [
        ("", "CSV file is empty"),
        ("invoice_no,gstin,invoice_date,taxable_value,gst_amount\n", "no data rows"),
    ],
)
def test_empty_and_header_only_csv_are_rejected_without_database_writes(
    client, import_context, content, expected_detail
):
    response = _upload(client, import_context["headers"], content=content)
    assert response.status_code == 422
    assert expected_detail.lower() in response.json()["detail"].lower()
    with _session() as db:
        assert db.scalar(
            select(ImportBatch.batch_id).where(ImportBatch.business_id == import_context["business_id"])
        ) is None
        assert db.scalar(
            select(Invoice.id).where(Invoice.business_id == import_context["business_id"])
        ) is None
        assert db.scalar(select(ImportBatchItem.id)) is None


def test_simulator_confirmation_creates_fixture_batch_and_items(client, import_context):
    response = client.post(
        "/gst/import",
        json={"return_type": "gstr1", "tax_period": "2026-07"},
        headers=import_context["headers"],
    )
    assert response.status_code == 200, response.text
    data = response.json()

    with _session() as db:
        batch = db.get(ImportBatch, _batch_uuid(data["import_batch_id"]))
        invoices = db.scalars(
            select(Invoice).where(
                Invoice.business_id == import_context["business_id"],
                Invoice.source == "gstr1",
            )
        ).all()
        assert batch is not None
        assert batch.business_id == import_context["business_id"]
        assert batch.imported_by_user_id == import_context["user_id"]
        assert batch.source_category == "gst_simulator"
        assert batch.source_type == "gstr1"
        assert batch.fixture_identifier == "gstr1.csv"
        assert batch.tax_period == "2026-07"
        assert batch.total_rows == 15
        assert batch.imported_rows == 15
        assert batch.duplicate_rows == batch.rejected_rows == 0
        assert len(invoices) == 15
        assert all(invoice.import_batch_id == batch.batch_id for invoice in invoices)
        assert db.scalar(
            select(ImportBatchItem.id).where(
                ImportBatchItem.batch_id == batch.batch_id,
                ImportBatchItem.outcome == "imported",
            ).limit(1)
        ) is not None


def test_simulator_preview_creates_no_batch_or_invoice_records(client, import_context):
    response = client.post(
        "/gst/import/preview",
        json={"return_type": "gstr1", "tax_period": "2026-07"},
        headers=import_context["headers"],
    )
    assert response.status_code == 200, response.text

    with _session() as db:
        assert db.scalar(
            select(ImportBatch.batch_id).where(ImportBatch.business_id == import_context["business_id"])
        ) is None
        assert db.scalar(
            select(Invoice.id).where(Invoice.business_id == import_context["business_id"])
        ) is None


def test_simulator_empty_fixture_returns_no_data_without_database_writes(client, import_context):
    with patch("routers.gst._fetch_server_return_records", return_value=("gstr1", [])):
        response = client.post(
            "/gst/import",
            json={"return_type": "gstr1", "tax_period": "2026-07"},
            headers=import_context["headers"],
        )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "no_data"
    with _session() as db:
        assert db.scalar(
            select(ImportBatch.batch_id).where(ImportBatch.business_id == import_context["business_id"])
        ) is None
        assert db.scalar(
            select(Invoice.id).where(Invoice.business_id == import_context["business_id"])
        ) is None
        assert db.scalar(select(ImportBatchItem.id)) is None


def test_all_rejected_simulator_import_is_failed_and_audited(client, import_context):
    invalid_records = [{"invoice_no": "", "invoice_date": "not-a-date", "taxable_value": "bad", "gst_amount": "bad"}]
    with patch("routers.gst._fetch_server_return_records", return_value=("gstr1", invalid_records)):
        response = client.post(
            "/gst/import",
            json={"return_type": "gstr1", "tax_period": "2026-07"},
            headers=import_context["headers"],
        )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "failed"
    assert data["imported_count"] == 0
    assert data["rejected_count"] == 1
    with _session() as db:
        batch = db.get(ImportBatch, _batch_uuid(data["import_batch_id"]))
        assert batch is not None
        assert batch.status == "failed"
        assert batch.imported_rows == 0
        assert batch.rejected_rows == 1
        assert len(batch.items) == 1
        assert batch.items[0].outcome == "rejected"
        assert db.scalar(select(Invoice.id).where(Invoice.business_id == import_context["business_id"])) is None


def test_csv_duplicate_items_reference_existing_invoice_without_reassigning_it(client, import_context):
    content = "invoice_no,gstin,invoice_date,taxable_value,gst_amount\nCSV-DUP-001,29ABCDE1234F1Z5,2026-07-01,100,18\n"
    first = _upload(client, import_context["headers"], content=content)
    second = _upload(client, import_context["headers"], content=content)
    assert first.status_code == second.status_code == 200
    assert first.json()["import_batch_id"] != second.json()["import_batch_id"]
    assert second.json()["imported"] == 0
    assert second.json()["duplicates"] == 1

    with _session() as db:
        invoice = db.scalar(select(Invoice).where(Invoice.invoice_no == "CSV-DUP-001"))
        first_batch = db.get(ImportBatch, _batch_uuid(first.json()["import_batch_id"]))
        second_batch = db.get(ImportBatch, _batch_uuid(second.json()["import_batch_id"]))
        assert invoice is not None
        assert first_batch is not None and second_batch is not None
        assert invoice.import_batch_id == first_batch.batch_id
        assert second_batch.imported_rows == 0
        assert second_batch.duplicate_rows == 1
        duplicate_item = db.scalar(
            select(ImportBatchItem).where(
                ImportBatchItem.batch_id == second_batch.batch_id,
                ImportBatchItem.outcome == "duplicate",
            )
        )
        assert duplicate_item is not None
        assert duplicate_item.invoice_id == invoice.id


def test_batch_items_record_imported_duplicate_and_rejected_outcomes(client, import_context):
    content = (
        "invoice_no,gstin,invoice_date,taxable_value,gst_amount\n"
        "CSV-MIX-001,29ABCDE1234F1Z5,2026-07-01,100,18\n"
        "CSV-MIX-001,29ABCDE1234F1Z5,2026-07-01,100,18\n"
        ",,not-a-date,invalid,invalid\n"
    )
    response = _upload(client, import_context["headers"], content=content)
    assert response.status_code == 200, response.text
    batch_id = response.json()["import_batch_id"]

    with _session() as db:
        batch = db.get(ImportBatch, _batch_uuid(batch_id))
        items = db.scalars(
            select(ImportBatchItem).where(ImportBatchItem.batch_id == _batch_uuid(batch_id))
        ).all()
        assert batch is not None
        assert (batch.total_rows, batch.imported_rows, batch.duplicate_rows, batch.rejected_rows) == (3, 1, 1, 1)
        assert sorted(item.outcome for item in items) == ["duplicate", "imported", "rejected"]
        assert all(item.batch_id == batch.batch_id for item in items)
        rejected = next(item for item in items if item.outcome == "rejected")
        assert rejected.invoice_id is None
        assert rejected.rejection_reason


def test_separate_csv_imports_have_distinct_batch_ids(client, import_context):
    first = _upload(client, import_context["headers"], content=(
        "invoice_no,gstin,invoice_date,taxable_value,gst_amount\nCSV-SEPARATE-001,29ABCDE1234F1Z5,2026-07-01,100,18\n"
    ))
    second = _upload(client, import_context["headers"], content=(
        "invoice_no,gstin,invoice_date,taxable_value,gst_amount\nCSV-SEPARATE-002,29ABCDE1234F1Z5,2026-07-02,200,36\n"
    ))
    assert first.status_code == second.status_code == 200
    assert first.json()["import_batch_id"] != second.json()["import_batch_id"]


def test_tenant_and_importer_cannot_be_forged_by_request_payload(client, import_context):
    db = _session()
    other_user = User(
        name="Other Tenant",
        email=f"other-{uuid4().hex}@example.test",
        password=hash_password("Pass123!"),
    )
    db.add(other_user)
    db.flush()
    other_business = Business(
        name="Other Business",
        gstin=f"29{uuid4().hex[:13].upper()}",
        user_id=other_user.id,
    )
    db.add(other_business)
    db.commit()
    other_user_id = other_user.id
    other_business_id = other_business.id
    db.close()

    csv_response = _upload(
        client,
        import_context["headers"],
        content=(
            "invoice_no,gstin,invoice_date,taxable_value,gst_amount\nCSV-TENANT-001,29ABCDE1234F1Z5,2026-07-01,100,18\n"
        ),
        extra_data={"business_id": str(other_business_id)},
    )
    assert csv_response.status_code == 200, csv_response.text
    simulator_response = client.post(
        "/gst/import",
        json={
            "return_type": "gstr1",
            "tax_period": "2026-07",
            "business_id": other_business_id,
            "imported_by_user_id": other_user_id,
        },
        headers=import_context["headers"],
    )
    assert simulator_response.status_code == 200, simulator_response.text

    forged_header = dict(import_context["headers"], **{"X-Business-ID": str(other_business_id)})
    denied = client.post(
        "/gst/import",
        json={"return_type": "gstr1", "tax_period": "2026-07"},
        headers=forged_header,
    )
    assert denied.status_code == 403

    with _session() as db:
        for batch_id in (csv_response.json()["import_batch_id"], simulator_response.json()["import_batch_id"]):
            batch = db.get(ImportBatch, _batch_uuid(batch_id))
            assert batch is not None
            assert batch.business_id == import_context["business_id"]
            assert batch.imported_by_user_id == import_context["user_id"]


def test_failed_csv_and_simulator_transactions_rollback_batches_and_invoices(client, import_context):
    with patch("sqlalchemy.orm.Session.commit", side_effect=RuntimeError("simulated database failure")):
        csv_response = _upload(
            client,
            import_context["headers"],
            content=(
                "invoice_no,gstin,invoice_date,taxable_value,gst_amount\nCSV-ROLLBACK-001,29ABCDE1234F1Z5,2026-07-01,100,18\n"
            ),
        )
        simulator_response = client.post(
            "/gst/import",
            json={"return_type": "gstr1", "tax_period": "2026-07"},
            headers=import_context["headers"],
        )

    assert csv_response.status_code == 500
    assert simulator_response.status_code == 500
    with _session() as db:
        assert db.scalar(
            select(ImportBatch.batch_id).where(ImportBatch.business_id == import_context["business_id"])
        ) is None
        assert db.scalar(
            select(Invoice.id).where(Invoice.business_id == import_context["business_id"])
        ) is None


def test_concurrent_invoice_uniqueness_conflict_rolls_back_losing_batch(client, import_context):
    # This row represents the transaction that wins after the request's
    # read-before-insert duplicate check but before its INSERT reaches SQLite.
    db = _session()
    winner = Invoice(
        invoice_no="RACE-001",
        invoice_date=date(2026, 7, 1),
        gstin="29ABCDE1234F1Z5",
        taxable_value=100,
        gst_amount=18,
        source="sales_register",
        business_id=import_context["business_id"],
    )
    db.add(winner)
    db.commit()
    winner_id = winner.id
    db.close()

    original_scalar = Session.scalar

    def miss_active_invoice_once(session, statement, *args, **kwargs):
        descriptions = getattr(statement, "column_descriptions", ())
        if descriptions and descriptions[0].get("entity") is Invoice:
            return None
        return original_scalar(session, statement, *args, **kwargs)

    with patch.object(Session, "scalar", miss_active_invoice_once):
        response = _upload(
            client,
            import_context["headers"],
            content=(
                "invoice_no,gstin,invoice_date,taxable_value,gst_amount\n"
                "RACE-001,29ABCDE1234F1Z5,2026-07-01,100,18\n"
            ),
        )

    assert response.status_code == 409
    assert "concurrently" in response.json()["detail"].lower()
    with _session() as db:
        saved = db.get(Invoice, winner_id)
        assert saved is not None and saved.import_batch_id is None
        assert db.scalar(
            select(ImportBatch.batch_id).where(ImportBatch.business_id == import_context["business_id"])
        ) is None
        assert db.scalar(
            select(Invoice.id).where(
                Invoice.business_id == import_context["business_id"],
                Invoice.invoice_no == "RACE-001",
            )
        ) == winner_id


def _invoice_for_scope(invoice_no, source, business_id, *, deleted_at=None):
    return Invoice(
        invoice_no=invoice_no,
        invoice_date=date(2026, 7, 1),
        gstin="29ABCDE1234F1Z5",
        taxable_value=100,
        gst_amount=18,
        source=source,
        business_id=business_id,
        deleted_at=deleted_at,
    )


def test_active_invoice_key_allows_same_number_for_other_business_and_source(import_context):
    db = _session()
    owner = db.get(User, import_context["user_id"])
    other_business = Business(
        name="Second business",
        gstin=f"29{uuid4().hex[:13].upper()}",
        user_id=owner.id,
    )
    db.add(other_business)
    db.flush()
    db.add_all(
        [
            _invoice_for_scope("SCOPE-001", "sales_register", import_context["business_id"]),
            _invoice_for_scope("SCOPE-001", "sales_register", other_business.id),
            _invoice_for_scope("SCOPE-001", "gstr1", import_context["business_id"]),
        ]
    )
    db.commit()
    assert db.scalar(select(Invoice.id).where(Invoice.invoice_no == "SCOPE-001")) is not None
    db.close()


def test_identical_active_invoice_key_is_rejected(import_context):
    db = _session()
    db.add(_invoice_for_scope("UNIQUE-001", "sales_register", import_context["business_id"]))
    db.commit()
    db.add(_invoice_for_scope("UNIQUE-001", "sales_register", import_context["business_id"]))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    assert db.scalar(
        select(Invoice.id).where(
            Invoice.invoice_no == "UNIQUE-001",
            Invoice.business_id == import_context["business_id"],
            Invoice.source == "sales_register",
            Invoice.deleted_at.is_(None),
        )
    ) is not None
    db.close()


def test_soft_deleted_invoice_does_not_block_active_reimport(import_context):
    db = _session()
    db.add(
        _invoice_for_scope(
            "RESTORE-001",
            "sales_register",
            import_context["business_id"],
            deleted_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
    )
    db.add(_invoice_for_scope("RESTORE-001", "sales_register", import_context["business_id"]))
    db.commit()
    active = db.scalars(
        select(Invoice).where(
            Invoice.invoice_no == "RESTORE-001",
            Invoice.business_id == import_context["business_id"],
            Invoice.deleted_at.is_(None),
        )
    ).all()
    assert len(active) == 1
    db.close()


def _gstr3b_fixture_values(**overrides):
    values = {
        "tax_period": "2026-07",
        "output_tax": 100000.0,
        "eligible_itc": 30000.0,
        "itc_reversed": 500.0,
        "net_itc": 29500.0,
        "found": True,
        "data_source": "synthetic_csv",
        "provider": "mock",
    }
    return {**values, **overrides}


def _post_gstr3b(client, endpoint, headers, tax_period="2026-07"):
    return client.post(endpoint, json={"tax_period": tax_period}, headers=headers)


def test_gstr3b_preview_has_no_database_writes(client, import_context):
    preview = _post_gstr3b(
        client,
        "/gst/gstr3b/import/preview",
        import_context["headers"],
    )
    assert preview.status_code == 200, preview.text
    data = preview.json()
    assert data["status"] == "preview"
    assert data["operation"] == "new_import"
    assert data["data_source"] == "synthetic_csv"
    assert data["fixture_summary"]["tax_period"] == "2026-07"
    assert data["existing_summary"] is None
    with _session() as db:
        assert db.scalar(
            select(GSTR3BReturn.id).where(GSTR3BReturn.business_id == import_context["business_id"])
        ) is None
        assert db.scalar(
            select(ImportBatch.batch_id).where(ImportBatch.business_id == import_context["business_id"])
        ) is None
        assert db.scalar(
            select(Invoice.id).where(Invoice.business_id == import_context["business_id"])
        ) is None


def test_gstr3b_new_period_confirmation_tracks_business_user_and_no_invoice(client, import_context):
    response = _post_gstr3b(client, "/gst/gstr3b/import", import_context["headers"])
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "success"
    assert result["operation"] == "new_import"
    assert result["imported_count"] == 1

    with _session() as db:
        returned = db.scalar(
            select(GSTR3BReturn).where(
                GSTR3BReturn.business_id == import_context["business_id"],
                GSTR3BReturn.tax_period == "2026-07",
            )
        )
        batch = db.get(ImportBatch, _batch_uuid(result["import_batch_id"]))
        assert returned is not None
        assert batch is not None
        assert batch.business_id == import_context["business_id"]
        assert batch.imported_by_user_id == import_context["user_id"]
        assert batch.source_category == "gst_simulator"
        assert batch.source_type == "gstr3b"
        assert batch.fixture_identifier == "gstr3b.csv"
        assert batch.tax_period == "2026-07"
        assert batch.imported_rows == 1 and batch.status == "completed"
        assert returned.import_batch_id == batch.batch_id
        assert returned.output_tax == result["summary"]["output_tax"]
        assert len(batch.items) == 1
        item = batch.items[0]
        assert item.target_record_type == "gstr3b_return"
        assert item.gstr3b_return_id == returned.id
        assert item.target_period == "2026-07"
        assert item.outcome == "imported"
        assert item.previous_values is None
        assert item.new_values == result["summary"]
        assert db.scalar(select(Invoice.id)) is None

    summary_response = client.get(
        "/gstr3b/summary?tax_period=2026-07",
        headers=import_context["headers"],
    )
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["source"] == "database"
    assert summary["business_name"] == "Batch Test Business"
    assert summary["provenance"]["source_category"] == "gst_simulator"
    assert summary["provenance"]["fixture_identifier"] == "gstr3b.csv"


def test_gstr3b_identical_confirmation_is_duplicate_without_new_batch(client, import_context):
    first = _post_gstr3b(client, "/gst/gstr3b/import", import_context["headers"])
    assert first.status_code == 200
    second = _post_gstr3b(client, "/gst/gstr3b/import", import_context["headers"])
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "duplicate"
    assert second.json()["imported_count"] == 0

    with _session() as db:
        batches = db.scalars(
            select(ImportBatch).where(ImportBatch.business_id == import_context["business_id"])
        ).all()
        returns = db.scalars(
            select(GSTR3BReturn).where(GSTR3BReturn.business_id == import_context["business_id"])
        ).all()
        assert len(batches) == 1
        assert len(returns) == 1
        assert returns[0].import_batch_id == _batch_uuid(first.json()["import_batch_id"])
        assert len(batches[0].items) == 1


def test_gstr3b_revision_preserves_original_batch_and_records_complete_snapshots(
    client, import_context
):
    first = _post_gstr3b(client, "/gst/gstr3b/import", import_context["headers"])
    assert first.status_code == 200
    original_batch_id = first.json()["import_batch_id"]
    revised_fixture = _gstr3b_fixture_values(
        output_tax=110000.0,
        eligible_itc=32000.0,
        itc_reversed=700.0,
        net_itc=31300.0,
    )
    fake_adapter = type(
        "FakeGstAdapter",
        (),
        {"get_gstr3b_summary": lambda self, **_kwargs: revised_fixture},
    )()
    with patch("routers.gst.get_gst_adapter", return_value=fake_adapter):
        preview = _post_gstr3b(client, "/gst/gstr3b/import/preview", import_context["headers"])
        assert preview.status_code == 200
        assert preview.json()["operation"] == "revision"
        assert preview.json()["existing_summary"] == first.json()["summary"]
        assert preview.json()["differences"]["output_tax"] == (
            revised_fixture["output_tax"] - first.json()["summary"]["output_tax"]
        )
        revised = _post_gstr3b(client, "/gst/gstr3b/import", import_context["headers"])

    assert revised.status_code == 200, revised.text
    assert revised.json()["status"] == "success"
    assert revised.json()["operation"] == "revision"
    with _session() as db:
        returned = db.scalar(
            select(GSTR3BReturn).where(
                GSTR3BReturn.business_id == import_context["business_id"],
                GSTR3BReturn.tax_period == "2026-07",
            )
        )
        batches = db.scalars(
            select(ImportBatch).where(ImportBatch.business_id == import_context["business_id"])
        ).all()
        revised_item = db.scalar(
            select(ImportBatchItem).where(
                ImportBatchItem.outcome == "revised",
                ImportBatchItem.target_period == "2026-07",
            )
        )
        assert returned is not None
        assert returned.import_batch_id == _batch_uuid(original_batch_id)
        assert returned.output_tax == revised_fixture["output_tax"]
        assert len(batches) == 2
        assert revised_item is not None
        assert revised_item.batch_id == _batch_uuid(revised.json()["import_batch_id"])
        assert revised_item.gstr3b_return_id == returned.id
        assert revised_item.previous_values == first.json()["summary"]
        assert revised_item.new_values == revised.json()["summary"]


def test_gstr3b_missing_fixture_period_returns_no_data_without_writes(client, import_context):
    response = _post_gstr3b(
        client,
        "/gst/gstr3b/import",
        import_context["headers"],
        tax_period="2020-01",
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "no_data"
    with _session() as db:
        assert db.scalar(
            select(GSTR3BReturn.id).where(GSTR3BReturn.business_id == import_context["business_id"])
        ) is None
        assert db.scalar(
            select(ImportBatch.batch_id).where(ImportBatch.business_id == import_context["business_id"])
        ) is None
        assert db.scalar(select(Invoice.id)) is None


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("output_tax", -1),
        ("eligible_itc", float("nan")),
        ("itc_reversed", "not-a-number"),
        ("net_itc", float("inf")),
    ],
)
def test_gstr3b_preview_rejects_invalid_fixture_summary_values_without_writes(
    client, import_context, field, invalid_value
):
    bad_fixture = _gstr3b_fixture_values(**{field: invalid_value})
    fake_adapter = type(
        "FakeGstAdapter",
        (),
        {"get_gstr3b_summary": lambda self, **_kwargs: bad_fixture},
    )()
    with patch("routers.gst.get_gst_adapter", return_value=fake_adapter):
        response = _post_gstr3b(
            client,
            "/gst/gstr3b/import/preview",
            import_context["headers"],
        )
    assert response.status_code == 422
    assert field in response.json()["detail"]
    with _session() as db:
        assert db.scalar(select(GSTR3BReturn.id)) is None
        assert db.scalar(select(ImportBatch.batch_id)) is None
        assert db.scalar(select(Invoice.id)) is None


def test_gstr3b_cross_tenant_business_cannot_be_used_for_import(client, import_context):
    with _session() as db:
        other_user = User(
            name="Other GST-3B Tenant",
            email=f"gstr3b-other-{uuid4().hex}@example.test",
            password=hash_password("Pass123!"),
        )
        db.add(other_user)
        db.flush()
        other_business = Business(
            name="Other GST-3B Business",
            gstin=f"29{uuid4().hex[:13].upper()}",
            user_id=other_user.id,
        )
        db.add(other_business)
        db.commit()
        other_business_id = other_business.id

    forged_headers = dict(
        import_context["headers"], **{"X-Business-ID": str(other_business_id)}
    )
    response = _post_gstr3b(client, "/gst/gstr3b/import", forged_headers)
    assert response.status_code == 403
    with _session() as db:
        assert db.scalar(
            select(GSTR3BReturn.id).where(GSTR3BReturn.business_id == other_business_id)
        ) is None
        assert db.scalar(
            select(ImportBatch.batch_id).where(ImportBatch.business_id == other_business_id)
        ) is None


def test_gstr3b_transaction_failure_rolls_back_batch_and_return(client, import_context):
    with patch("sqlalchemy.orm.Session.commit", side_effect=RuntimeError("simulated transaction failure")):
        response = _post_gstr3b(client, "/gst/gstr3b/import", import_context["headers"])
    assert response.status_code == 500
    assert "rolled back" in response.json()["detail"].lower()
    with _session() as db:
        assert db.scalar(
            select(GSTR3BReturn.id).where(GSTR3BReturn.business_id == import_context["business_id"])
        ) is None
        assert db.scalar(
            select(ImportBatch.batch_id).where(ImportBatch.business_id == import_context["business_id"])
        ) is None
        assert db.scalar(select(ImportBatchItem.id)) is None
        assert db.scalar(
            select(Invoice.id).where(Invoice.business_id == import_context["business_id"])
        ) is None


def test_gstr3b_period_uniqueness_conflict_rolls_back_new_batch(client, import_context):
    db = _session()
    existing = GSTR3BReturn(
        business_id=import_context["business_id"],
        tax_period="2026-07",
        output_tax=999.0,
        eligible_itc=888.0,
        itc_reversed=7.0,
        net_itc=881.0,
    )
    db.add(existing)
    db.commit()
    existing_id = existing.id
    db.close()

    original_scalar = Session.scalar

    def miss_period_once(session, statement, *args, **kwargs):
        descriptions = getattr(statement, "column_descriptions", ())
        if descriptions and descriptions[0].get("entity") is GSTR3BReturn:
            return None
        return original_scalar(session, statement, *args, **kwargs)

    with patch.object(Session, "scalar", miss_period_once):
        response = _post_gstr3b(client, "/gst/gstr3b/import", import_context["headers"])

    assert response.status_code == 409
    assert "concurrently" in response.json()["detail"].lower()
    with _session() as db:
        saved = db.get(GSTR3BReturn, existing_id)
        assert saved is not None
        assert saved.output_tax == 999.0
        assert saved.import_batch_id is None
        assert db.scalar(
            select(ImportBatch.batch_id).where(ImportBatch.business_id == import_context["business_id"])
        ) is None
        assert db.scalar(
            select(Invoice.id).where(Invoice.business_id == import_context["business_id"])
        ) is None


def test_repeated_simulator_imports_are_idempotent_and_create_separate_batches(client, import_context):
    payload = {"return_type": "gstr1", "tax_period": "2026-07"}
    first = client.post("/gst/import", json=payload, headers=import_context["headers"])
    second = client.post("/gst/import", json=payload, headers=import_context["headers"])
    assert first.status_code == second.status_code == 200
    assert first.json()["import_batch_id"] != second.json()["import_batch_id"]
    assert first.json()["imported_count"] == 15
    assert second.json()["imported_count"] == 0
    assert second.json()["duplicate_count"] == 15

    with _session() as db:
        invoices = db.scalars(
            select(Invoice).where(
                Invoice.business_id == import_context["business_id"],
                Invoice.source == "gstr1",
            )
        ).all()
        batches = db.scalars(
            select(ImportBatch).where(ImportBatch.business_id == import_context["business_id"])
        ).all()
        assert len(batches) == 2
        assert len(invoices) == 15
        assert all(invoice.import_batch_id == _batch_uuid(first.json()["import_batch_id"]) for invoice in invoices)
        second_batch = db.get(ImportBatch, _batch_uuid(second.json()["import_batch_id"]))
        assert second_batch is not None
        assert second_batch.imported_rows == 0
        assert second_batch.duplicate_rows == 15
        duplicate_items = db.scalars(
            select(ImportBatchItem).where(
                ImportBatchItem.batch_id == second_batch.batch_id,
                ImportBatchItem.outcome == "duplicate",
            )
        ).all()
        assert {item.invoice_id for item in duplicate_items} == {invoice.id for invoice in invoices}
        assert all(batch.batch_id != second_batch.batch_id for batch in batches if batch.imported_rows == 15)
