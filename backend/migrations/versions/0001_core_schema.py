"""Baseline for the existing ReconcilePro relational schema.

Revision ID: 0001_core_schema
Revises:
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_core_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=150), nullable=False),
        sa.Column("password", sa.String(length=255), nullable=False),
    )
    op.create_index("ix_users_id", "users", ["id"])
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "businesses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("gstin", sa.String(length=15), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
    )
    op.create_index("ix_businesses_id", "businesses", ["id"])
    op.create_index("ix_businesses_gstin", "businesses", ["gstin"], unique=True)

    op.create_table(
        "invoices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("invoice_no", sa.String(length=50), nullable=False),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("gstin", sa.String(length=15), nullable=False),
        sa.Column("taxable_value", sa.Float(), nullable=False),
        sa.Column("gst_amount", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("business_id", sa.Integer(), sa.ForeignKey("businesses.id"), nullable=False),
    )
    op.create_index("ix_invoices_id", "invoices", ["id"])
    op.create_index("ix_invoices_invoice_no", "invoices", ["invoice_no"])

    op.create_table(
        "gstr3b_returns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("business_id", sa.Integer(), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("tax_period", sa.String(length=10), nullable=False),
        sa.Column("output_tax", sa.Float(), nullable=False),
        sa.Column("eligible_itc", sa.Float(), nullable=False),
        sa.Column("itc_reversed", sa.Float(), nullable=False),
        sa.Column("net_itc", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("business_id", "tax_period", name="uq_gstr3b_business_tax_period"),
    )
    op.create_index("ix_gstr3b_returns_id", "gstr3b_returns", ["id"])
    op.create_index("ix_gstr3b_returns_business_id", "gstr3b_returns", ["business_id"])
    op.create_index("ix_gstr3b_returns_tax_period", "gstr3b_returns", ["tax_period"])


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in ("gstr3b_returns", "invoices", "businesses", "users"):
        if bind.execute(sa.text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one() > 0:
            raise RuntimeError(
                "Core schema downgrade blocked because application records exist. "
                "No user or business data was removed."
            )

    op.drop_index("ix_gstr3b_returns_tax_period", table_name="gstr3b_returns")
    op.drop_index("ix_gstr3b_returns_business_id", table_name="gstr3b_returns")
    op.drop_index("ix_gstr3b_returns_id", table_name="gstr3b_returns")
    op.drop_table("gstr3b_returns")
    op.drop_index("ix_invoices_invoice_no", table_name="invoices")
    op.drop_index("ix_invoices_id", table_name="invoices")
    op.drop_table("invoices")
    op.drop_index("ix_businesses_gstin", table_name="businesses")
    op.drop_index("ix_businesses_id", table_name="businesses")
    op.drop_table("businesses")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_id", table_name="users")
    op.drop_table("users")
