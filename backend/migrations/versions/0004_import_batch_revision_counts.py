"""Track revised GSTR-3B period counts on import batches.

Revision ID: 0004_import_batch_rev_counts
Revises: 0003_active_invoice_uniqueness
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_import_batch_rev_counts"
down_revision = "0003_active_invoice_uniqueness"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("import_batches") as batch_op:
        batch_op.add_column(
            sa.Column(
                "revised_rows",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
        batch_op.create_check_constraint(
            "ck_import_batches_nonnegative_revised_rows",
            "revised_rows >= 0",
        )


def downgrade() -> None:
    bind = op.get_bind()
    revised_batches = bind.execute(
        sa.text("SELECT COUNT(*) FROM import_batches WHERE revised_rows > 0")
    ).scalar_one()
    if revised_batches:
        raise RuntimeError(
            "Revision-count migration downgrade blocked because revised import history exists. "
            "Preserve the batch audit counts before considering a downgrade."
        )

    protected_rows = (
        ("import_batches", "SELECT COUNT(*) FROM import_batches"),
        ("import_batch_items", "SELECT COUNT(*) FROM import_batch_items"),
        ("invoices", "SELECT COUNT(*) FROM invoices WHERE import_batch_id IS NOT NULL OR deleted_at IS NOT NULL"),
        (
            "gstr3b_returns",
            "SELECT COUNT(*) FROM gstr3b_returns WHERE import_batch_id IS NOT NULL OR deleted_at IS NOT NULL",
        ),
    )
    if any(bind.execute(sa.text(query)).scalar_one() for _table, query in protected_rows):
        raise RuntimeError(
            "Revision-count migration downgrade blocked because import batch audit data exists. "
            "Preserve the audit history before considering a downgrade."
        )

    with op.batch_alter_table("import_batches") as batch_op:
        batch_op.drop_constraint("ck_import_batches_nonnegative_revised_rows", type_="check")
        batch_op.drop_column("revised_rows")
