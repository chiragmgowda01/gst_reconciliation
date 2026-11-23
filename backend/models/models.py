from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

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


class Invoice(Base):
    __tablename__ = "invoices"

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

    business: Mapped["Business"] = relationship(
        back_populates="invoices"
    )


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

    business: Mapped["Business"] = relationship(back_populates="gstr3b_returns")
