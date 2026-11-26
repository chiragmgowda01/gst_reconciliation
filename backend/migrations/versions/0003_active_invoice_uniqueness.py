"""Prevent duplicate active invoices per business and source.

Revision ID: 0003_active_invoice_uniqueness
Revises: 0002_import_batch_management
"""

from alembic import context, op
import sqlalchemy as sa


revision = "0003_active_invoice_uniqueness"
down_revision = "0002_import_batch_management"
branch_labels = None
depends_on = None

INDEX_NAME = "uq_invoices_active_business_source_invoice"


def upgrade() -> None:
    bind = op.get_bind()
    if context.is_offline_mode():
        # A generated PostgreSQL script must retain the same read-only duplicate
        # gate when it is later executed, rather than skipping the audit.
        op.execute(
            sa.text(
                "DO $$ BEGIN "
                "IF EXISTS (SELECT 1 FROM invoices WHERE deleted_at IS NULL "
                "GROUP BY business_id, source, invoice_no HAVING COUNT(*) > 1) THEN "
                "RAISE EXCEPTION 'Active invoice uniqueness migration aborted: duplicate active business/source/invoice keys exist; review them before retrying'; "
                "END IF; END $$;"
            )
        )
    else:
        duplicates = bind.execute(
            sa.text(
                "SELECT business_id, source, invoice_no, COUNT(*) AS duplicate_count "
                "FROM invoices WHERE deleted_at IS NULL "
                "GROUP BY business_id, source, invoice_no HAVING COUNT(*) > 1 "
                "ORDER BY business_id, source, invoice_no"
            )
        ).mappings().all()
        if duplicates:
            details = "; ".join(
                f"business_id={row['business_id']}, source={row['source']!r}, "
                f"invoice_no={row['invoice_no']!r}, count={row['duplicate_count']}"
                for row in duplicates
            )
            raise RuntimeError(
                "Active invoice uniqueness migration aborted. Resolve these duplicate keys "
                "through an approved data review, then retry; no invoice rows were changed: "
                f"{details}"
            )

    op.create_index(
        INDEX_NAME,
        "invoices",
        ["business_id", "source", "invoice_no"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
        sqlite_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    protected_rows = (
        ("import_batches", "SELECT COUNT(*) FROM import_batches"),
        ("import_batch_items", "SELECT COUNT(*) FROM import_batch_items"),
        ("invoices", "SELECT COUNT(*) FROM invoices WHERE import_batch_id IS NOT NULL OR deleted_at IS NOT NULL"),
        (
            "gstr3b_returns",
            "SELECT COUNT(*) FROM gstr3b_returns WHERE import_batch_id IS NOT NULL OR deleted_at IS NOT NULL",
        ),
    )
    for _table_name, query in protected_rows:
        if bind.execute(sa.text(query)).scalar_one() > 0:
            raise RuntimeError(
                "Active invoice uniqueness migration downgrade blocked because audit data exists. "
                "Preserve the audit history before considering a downgrade."
            )
    op.drop_index(INDEX_NAME, table_name="invoices")
