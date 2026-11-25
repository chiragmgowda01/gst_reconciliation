from datetime import date, datetime, timezone
from pathlib import PurePosixPath
import re
import uuid

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.orm import validates

from .base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(150), unique=True, index=True)
    password: Mapped[str] = mapped_column(String(255))

    businesses: Mapped[list["Business"]] = relationship(
        back_populates="user"
    )
    import_batches: Mapped[list["ImportBatch"]] = relationship(
        foreign_keys="ImportBatch.imported_by_user_id", back_populates="imported_by"
    )


class Business(Base):
    __tablename__ = "businesses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(150))
    gstin: Mapped[str] = mapped_column(String(15), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    user: Mapped["User"] = relationship(back_populates="businesses")
    invoices: Mapped[list["Invoice"]] = relationship(
        back_populates="business"
    )
    gstr3b_returns: Mapped[list["GSTR3BReturn"]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )
    import_batches: Mapped[list["ImportBatch"]] = relationship(back_populates="business")


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        Index(
            "uq_invoices_active_business_source_invoice",
            "business_id",
            "source",
            "invoice_no",
            unique=True,
            sqlite_where=text("deleted_at IS NULL"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    invoice_no: Mapped[str] = mapped_column(String(50), index=True)
    invoice_date: Mapped[date] = mapped_column(Date)
    gstin: Mapped[str] = mapped_column(String(15))
    taxable_value: Mapped[float] = mapped_column(Float)
    gst_amount: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )

    business_id: Mapped[int] = mapped_column(
        ForeignKey("businesses.id")
    )
    import_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("import_batches.batch_id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    business: Mapped["Business"] = relationship(
        back_populates="invoices"
    )
    import_batch: Mapped["ImportBatch | None"] = relationship(back_populates="invoices")

    @property
    def import_tracking_status(self) -> str:
        """Rows without a batch are legacy/untracked; no historical batch is inferred."""
        return "tracked" if self.import_batch_id is not None else "legacy_untracked"


class ImportBatch(Base):
    """Auditable metadata for one completed or attempted data import."""

    __tablename__ = "import_batches"
    __table_args__ = (
        CheckConstraint(
            "source_category IN ('csv_upload', 'gst_simulator', 'legacy_untracked')",
            name="ck_import_batches_source_category",
        ),
        CheckConstraint(
            "source_type IN ('sales_register', 'gstr1', 'purchase_register', 'gstr2a', 'gstr2b', 'gstr3b', 'unknown')",
            name="ck_import_batches_source_type",
        ),
        CheckConstraint(
            "fixture_identifier IS NULL OR fixture_identifier IN ('gstr1.csv', 'gstr2a.csv', 'gstr2b.csv', 'gstr3b.csv')",
            name="ck_import_batches_fixture_identifier",
        ),
        CheckConstraint(
            "status IN ('in_progress', 'completed', 'partial', 'failed', 'deleted')",
            name="ck_import_batches_status",
        ),
        CheckConstraint(
            "total_rows >= 0 AND imported_rows >= 0 AND duplicate_rows >= 0 AND rejected_rows >= 0",
            name="ck_import_batches_nonnegative_counts",
        ),
        CheckConstraint("revised_rows >= 0", name="ck_import_batches_nonnegative_revised_rows"),
        CheckConstraint(
            "(source_category = 'csv_upload' AND original_filename IS NOT NULL AND fixture_identifier IS NULL) "
            "OR (source_category = 'gst_simulator' AND original_filename IS NULL AND "
            "((source_type = 'gstr1' AND fixture_identifier = 'gstr1.csv') "
            "OR (source_type = 'gstr2a' AND fixture_identifier = 'gstr2a.csv') "
            "OR (source_type = 'gstr2b' AND fixture_identifier = 'gstr2b.csv') "
            "OR (source_type = 'gstr3b' AND fixture_identifier = 'gstr3b.csv'))) "
            "OR (source_category = 'legacy_untracked' AND original_filename IS NULL AND fixture_identifier IS NULL)",
            name="ck_import_batches_source_reference",
        ),
        CheckConstraint(
            "(source_category = 'legacy_untracked' AND imported_by_user_id IS NULL) "
            "OR (source_category IN ('csv_upload', 'gst_simulator') AND imported_by_user_id IS NOT NULL)",
            name="ck_import_batches_importer",
        ),
        Index("ix_import_batches_business_created_at", "business_id", "created_at"),
    )

    batch_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    business_id: Mapped[int] = mapped_column(
        ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    imported_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    source_category: Mapped[str] = mapped_column(String(30), nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fixture_identifier: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tax_period: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    imported_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    revised_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    rejected_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="in_progress")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    business: Mapped["Business"] = relationship(back_populates="import_batches")
    imported_by: Mapped["User | None"] = relationship(
        foreign_keys=[imported_by_user_id], back_populates="import_batches"
    )
    deleted_by: Mapped["User | None"] = relationship(foreign_keys=[deleted_by_user_id])
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="import_batch")
    items: Mapped[list["ImportBatchItem"]] = relationship(back_populates="batch")

    @validates("original_filename")
    def _sanitize_original_filename(self, _key: str, value: str | None) -> str | None:
        if value is None:
            return None
        # UploadFile filenames are client supplied. Store only a printable basename,
        # never a path that could be interpreted as a local filesystem location.
        basename = PurePosixPath(str(value).replace("\\", "/")).name
        if basename in {"", ".", ".."}:
            return None
        safe_name = "".join(char for char in basename if char.isprintable()).strip()
        safe_name = re.sub(r"[\x00-\x1f\x7f]", "", safe_name)
        return safe_name[:255] or None


class ImportBatchItem(Base):
    """Per-row outcome and value snapshots retained for audit and later restoration."""

    __tablename__ = "import_batch_items"
    __table_args__ = (
        CheckConstraint(
            "target_record_type IN ('invoice', 'gstr3b_return')",
            name="ck_import_batch_items_target_type",
        ),
        CheckConstraint(
            "outcome IN ('imported', 'duplicate', 'rejected', 'revised')",
            name="ck_import_batch_items_outcome",
        ),
        CheckConstraint(
            "(target_record_type = 'invoice' AND gstr3b_return_id IS NULL AND target_period IS NULL "
            "AND ((outcome = 'rejected' AND invoice_id IS NULL) "
            "OR (outcome IN ('imported', 'duplicate', 'revised') AND invoice_id IS NOT NULL))) "
            "OR (target_record_type = 'gstr3b_return' AND invoice_id IS NULL AND target_period IS NOT NULL "
            "AND ((outcome = 'rejected' AND gstr3b_return_id IS NULL) "
            "OR (outcome IN ('imported', 'duplicate', 'revised') AND gstr3b_return_id IS NOT NULL)))",
            name="ck_import_batch_items_target_reference",
        ),
        Index("ix_import_batch_items_batch_outcome", "batch_id", "outcome"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("import_batches.batch_id", ondelete="RESTRICT"),
        nullable=False,
    )
    target_record_type: Mapped[str] = mapped_column(String(30), nullable=False)
    invoice_id: Mapped[int | None] = mapped_column(
        ForeignKey("invoices.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    gstr3b_return_id: Mapped[int | None] = mapped_column(
        ForeignKey("gstr3b_returns.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    target_period: Mapped[str | None] = mapped_column(String(10), nullable=True)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    previous_values: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_values: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), nullable=False
    )

    batch: Mapped["ImportBatch"] = relationship(back_populates="items")
    invoice: Mapped["Invoice | None"] = relationship()
    gstr3b_return: Mapped["GSTR3BReturn | None"] = relationship()


class GSTR3BReturn(Base):
    __tablename__ = "gstr3b_returns"
    __table_args__ = (
        UniqueConstraint("business_id", "tax_period", name="uq_gstr3b_business_tax_period"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    business_id: Mapped[int] = mapped_column(
        ForeignKey("businesses.id"), index=True, nullable=False
    )
    tax_period: Mapped[str] = mapped_column(String(10), index=True, nullable=False)
    output_tax: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    eligible_itc: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    itc_reversed: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    net_itc: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    import_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("import_batches.batch_id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    business: Mapped["Business"] = relationship(back_populates="gstr3b_returns")
    import_batch: Mapped["ImportBatch | None"] = relationship()

    @property
    def import_tracking_status(self) -> str:
        """Rows without a batch are legacy/untracked; history is never inferred."""
        return "tracked" if self.import_batch_id is not None else "legacy_untracked"
