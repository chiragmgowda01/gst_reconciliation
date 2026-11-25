"""Expected schema created by ReconcilePro's pre-Alembic ORM models."""

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
)


LEGACY_METADATA = MetaData()

users = Table(
    "users",
    LEGACY_METADATA,
    Column("id", Integer, primary_key=True, nullable=False),
    Column("name", String(100), nullable=False),
    Column("email", String(150), nullable=False),
    Column("password", String(255), nullable=False),
)
Index("ix_users_id", users.c.id)
Index("ix_users_email", users.c.email, unique=True)

businesses = Table(
    "businesses",
    LEGACY_METADATA,
    Column("id", Integer, primary_key=True, nullable=False),
    Column("name", String(150), nullable=False),
    Column("gstin", String(15), nullable=False),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False),
)
Index("ix_businesses_id", businesses.c.id)
Index("ix_businesses_gstin", businesses.c.gstin, unique=True)

invoices = Table(
    "invoices",
    LEGACY_METADATA,
    Column("id", Integer, primary_key=True, nullable=False),
    Column("invoice_no", String(50), nullable=False),
    Column("invoice_date", Date, nullable=False),
    Column("gstin", String(15), nullable=False),
    Column("taxable_value", Float, nullable=False),
    Column("gst_amount", Float, nullable=False),
    Column("source", String(30), nullable=False),
    Column("created_at", DateTime, nullable=False),
    Column("business_id", Integer, ForeignKey("businesses.id"), nullable=False),
)
Index("ix_invoices_id", invoices.c.id)
Index("ix_invoices_invoice_no", invoices.c.invoice_no)

gstr3b_returns = Table(
    "gstr3b_returns",
    LEGACY_METADATA,
    Column("id", Integer, primary_key=True, nullable=False),
    Column("business_id", Integer, ForeignKey("businesses.id"), nullable=False),
    Column("tax_period", String(10), nullable=False),
    Column("output_tax", Float, nullable=False),
    Column("eligible_itc", Float, nullable=False),
    Column("itc_reversed", Float, nullable=False),
    Column("net_itc", Float, nullable=False),
    Column("created_at", DateTime, nullable=False),
    Column("updated_at", DateTime, nullable=False),
    UniqueConstraint("business_id", "tax_period", name="uq_gstr3b_business_tax_period"),
)
Index("ix_gstr3b_returns_id", gstr3b_returns.c.id)
Index("ix_gstr3b_returns_business_id", gstr3b_returns.c.business_id)
Index("ix_gstr3b_returns_tax_period", gstr3b_returns.c.tax_period)
