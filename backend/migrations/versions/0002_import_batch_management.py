"""Add import batch history, row outcome snapshots, and soft-delete metadata.

Revision ID: 0002_import_batch_management
Revises: 0001_core_schema
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_import_batch_management"
down_revision = "0001_core_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "import_batches",
        sa.Column("batch_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("business_id", sa.Integer(), nullable=False),
        sa.Column("imported_by_user_id", sa.Integer(), nullable=True),
        sa.Column("source_category", sa.String(length=30), nullable=False),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("fixture_identifier", sa.String(length=64), nullable=True),
        sa.Column("tax_period", sa.String(length=10), nullable=True),
        sa.Column("total_rows", sa.Integer(), nullable=False),
        sa.Column("imported_rows", sa.Integer(), nullable=False),
        sa.Column("duplicate_rows", sa.Integer(), nullable=False),
        sa.Column("rejected_rows", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_by_user_id", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "source_category IN ('csv_upload', 'gst_simulator', 'legacy_untracked')",
            name="ck_import_batches_source_category",
        ),
        sa.CheckConstraint(
            "source_type IN ('sales_register', 'gstr1', 'purchase_register', 'gstr2a', 'gstr2b', 'gstr3b', 'unknown')",
            name="ck_import_batches_source_type",
        ),
        sa.CheckConstraint(
            "fixture_identifier IS NULL OR fixture_identifier IN ('gstr1.csv', 'gstr2a.csv', 'gstr2b.csv', 'gstr3b.csv')",
            name="ck_import_batches_fixture_identifier",
        ),
        sa.CheckConstraint(
            "status IN ('in_progress', 'completed', 'partial', 'failed', 'deleted')",
            name="ck_import_batches_status",
        ),
        sa.CheckConstraint(
            "total_rows >= 0 AND imported_rows >= 0 AND duplicate_rows >= 0 AND rejected_rows >= 0",
            name="ck_import_batches_nonnegative_counts",
        ),
        sa.CheckConstraint(
            "(source_category = 'csv_upload' AND original_filename IS NOT NULL AND fixture_identifier IS NULL) "
            "OR (source_category = 'gst_simulator' AND original_filename IS NULL AND "
            "((source_type = 'gstr1' AND fixture_identifier = 'gstr1.csv') "
            "OR (source_type = 'gstr2a' AND fixture_identifier = 'gstr2a.csv') "
            "OR (source_type = 'gstr2b' AND fixture_identifier = 'gstr2b.csv') "
            "OR (source_type = 'gstr3b' AND fixture_identifier = 'gstr3b.csv'))) "
            "OR (source_category = 'legacy_untracked' AND original_filename IS NULL AND fixture_identifier IS NULL)",
            name="ck_import_batches_source_reference",
        ),
        sa.CheckConstraint(
            "(source_category = 'legacy_untracked' AND imported_by_user_id IS NULL) "
            "OR (source_category IN ('csv_upload', 'gst_simulator') AND imported_by_user_id IS NOT NULL)",
            name="ck_import_batches_importer",
        ),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["imported_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["deleted_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("batch_id"),
    )
    op.create_index("ix_import_batches_business_id", "import_batches", ["business_id"])
    op.create_index("ix_import_batches_imported_by_user_id", "import_batches", ["imported_by_user_id"])
    op.create_index("ix_import_batches_tax_period", "import_batches", ["tax_period"])
    op.create_index("ix_import_batches_business_created_at", "import_batches", ["business_id", "created_at"])

    op.create_table(
        "import_batch_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("target_record_type", sa.String(length=30), nullable=False),
        sa.Column("invoice_id", sa.Integer(), nullable=True),
        sa.Column("gstr3b_return_id", sa.Integer(), nullable=True),
        sa.Column("target_period", sa.String(length=10), nullable=True),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("previous_values", sa.JSON(), nullable=True),
        sa.Column("new_values", sa.JSON(), nullable=True),
        sa.Column("rejection_reason", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "target_record_type IN ('invoice', 'gstr3b_return')",
            name="ck_import_batch_items_target_type",
        ),
        sa.CheckConstraint(
            "outcome IN ('imported', 'duplicate', 'rejected', 'revised')",
            name="ck_import_batch_items_outcome",
        ),
        sa.CheckConstraint(
            "(target_record_type = 'invoice' AND gstr3b_return_id IS NULL AND target_period IS NULL "
            "AND ((outcome = 'rejected' AND invoice_id IS NULL) "
            "OR (outcome IN ('imported', 'duplicate', 'revised') AND invoice_id IS NOT NULL))) "
            "OR (target_record_type = 'gstr3b_return' AND invoice_id IS NULL AND target_period IS NOT NULL "
            "AND ((outcome = 'rejected' AND gstr3b_return_id IS NULL) "
            "OR (outcome IN ('imported', 'duplicate', 'revised') AND gstr3b_return_id IS NOT NULL)))",
            name="ck_import_batch_items_target_reference",
        ),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["gstr3b_return_id"], ["gstr3b_returns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["batch_id"], ["import_batches.batch_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_import_batch_items_batch_outcome", "import_batch_items", ["batch_id", "outcome"])
    op.create_index("ix_import_batch_items_invoice_id", "import_batch_items", ["invoice_id"])
    op.create_index("ix_import_batch_items_gstr3b_return_id", "import_batch_items", ["gstr3b_return_id"])

    with op.batch_alter_table("invoices") as batch_op:
        batch_op.add_column(sa.Column("import_batch_id", sa.Uuid(as_uuid=False), nullable=True))
        batch_op.add_column(sa.Column("deleted_at", sa.DateTime(), nullable=True))
        batch_op.create_foreign_key(
            "fk_invoices_import_batch_id_import_batches",
            "import_batches",
            ["import_batch_id"],
            ["batch_id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index("ix_invoices_import_batch_id", ["import_batch_id"])

    with op.batch_alter_table("gstr3b_returns") as batch_op:
        batch_op.add_column(sa.Column("deleted_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("import_batch_id", sa.Uuid(as_uuid=False), nullable=True))
        batch_op.create_foreign_key(
            "fk_gstr3b_returns_import_batch_id_import_batches",
            "import_batches",
            ["import_batch_id"],
            ["batch_id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index("ix_gstr3b_returns_import_batch_id", ["import_batch_id"])


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
                "Import-batch migration downgrade blocked because tracked or audit data exists. "
                "Export and preserve the audit history before considering a downgrade."
            )

    with op.batch_alter_table("gstr3b_returns") as batch_op:
        batch_op.drop_index("ix_gstr3b_returns_import_batch_id")
        batch_op.drop_constraint(
            "fk_gstr3b_returns_import_batch_id_import_batches", type_="foreignkey"
        )
        batch_op.drop_column("import_batch_id")
        batch_op.drop_column("deleted_at")

    with op.batch_alter_table("invoices") as batch_op:
        batch_op.drop_index("ix_invoices_import_batch_id")
        batch_op.drop_constraint("fk_invoices_import_batch_id_import_batches", type_="foreignkey")
        batch_op.drop_column("import_batch_id")
        batch_op.drop_column("deleted_at")

    op.drop_index("ix_import_batch_items_gstr3b_return_id", table_name="import_batch_items")
    op.drop_index("ix_import_batch_items_invoice_id", table_name="import_batch_items")
    op.drop_index("ix_import_batch_items_batch_outcome", table_name="import_batch_items")
    op.drop_table("import_batch_items")
    op.drop_index("ix_import_batches_business_created_at", table_name="import_batches")
    op.drop_index("ix_import_batches_tax_period", table_name="import_batches")
    op.drop_index("ix_import_batches_imported_by_user_id", table_name="import_batches")
    op.drop_index("ix_import_batches_business_id", table_name="import_batches")
    op.drop_table("import_batches")
