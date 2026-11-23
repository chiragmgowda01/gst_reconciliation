import io
from datetime import datetime, timezone
from typing import List, Optional
import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pathlib import Path
from database import get_db
from models.models import Business, GSTR3BReturn, Invoice
from services.auth import get_current_business
from services.validation import (
    normalize_gstr3b_dataframe,
    normalize_invoice_dataframe,
    parse_date_safely,
    validate_gstr3b_row,
    validate_invoice_row,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


router = APIRouter(prefix="/invoices", tags=["Invoices"])


@router.get("")
def list_invoices(
    source: Optional[str] = Query(None, description="Filter by source (sales_register, gstr1, etc.)"),
    gstin: Optional[str] = Query(None, description="Filter by customer or supplier GSTIN"),
    search: Optional[str] = Query(None, description="Search by invoice number or GSTIN"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    query = select(Invoice).where(Invoice.business_id == current_business.id)

    if source:
        query = query.where(Invoice.source == source)
    if gstin:
        query = query.where(Invoice.gstin.ilike(f"%{gstin.strip()}%"))
    if search:
        s = f"%{search.strip()}%"
        query = query.where((Invoice.invoice_no.ilike(s)) | (Invoice.gstin.ilike(s)))

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    query = query.order_by(Invoice.invoice_date.desc(), Invoice.id.desc()).offset(offset).limit(limit)
    invoices = db.scalars(query).all()

    return {
        "business_id": current_business.id,
        "business_name": current_business.name,
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [
            {
                "id": inv.id,
                "invoice_no": inv.invoice_no,
                "invoice_date": inv.invoice_date.isoformat() if inv.invoice_date else None,
                "gstin": inv.gstin,
                "taxable_value": inv.taxable_value,
                "gst_amount": inv.gst_amount,
                "source": inv.source,
                "created_at": inv.created_at.isoformat() if inv.created_at else None,
                "business_id": inv.business_id,
            }
            for inv in invoices
        ],
    }


@router.get("/{invoice_id}")
def get_invoice(
    invoice_id: int,
    current_business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    invoice = db.scalar(
        select(Invoice).where(
            Invoice.id == invoice_id,
            Invoice.business_id == current_business.id,
        )
    )
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    return {
        "id": invoice.id,
        "invoice_no": invoice.invoice_no,
        "invoice_date": invoice.invoice_date.isoformat() if invoice.invoice_date else None,
        "gstin": invoice.gstin,
        "taxable_value": invoice.taxable_value,
        "gst_amount": invoice.gst_amount,
        "source": invoice.source,
        "created_at": invoice.created_at.isoformat() if invoice.created_at else None,
        "business": {
            "id": current_business.id,
            "name": current_business.name,
            "gstin": current_business.gstin,
        },
    }


@router.post("/upload")
async def upload_csv(
    file: UploadFile = File(...),
    source_type: str = Form(..., description="sales_register, gstr1, purchase_register, gstr2a, gstr2b, or gstr3b"),
    current_business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    valid_sources = {"sales_register", "gstr1", "purchase_register", "gstr2a", "gstr2b", "gstr3b"}
    norm_source = source_type.strip().lower()
    if norm_source not in valid_sources:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid source_type '{source_type}'. Must be one of {sorted(list(valid_sources))}",
        )

    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV files (.csv) are supported for upload",
        )

    try:
        content = await file.read()
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = content.decode("latin-1", errors="replace")
        df = pd.read_csv(io.StringIO(text))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse CSV file: {str(e)}",
        )

    # Strip any stray BOM or leading/trailing whitespace from column names
    df.columns = [str(c).replace("\ufeff", "").strip() for c in df.columns]

    if df.empty:
        return {
            "file_name": file.filename,
            "source_type": norm_source,
            "business_id": current_business.id,
            "total_records": 0,
            "imported": 0,
            "duplicates": 0,
            "invalid_records": 0,
            "rejected": 0,
            "validation_findings": 0,
            "errors": [],
            "message": "CSV file was empty. No records imported.",
        }

    # ── GSTR-3B Summary Data Handling (Treated as monthly summary level, not invoice level) ──
    if norm_source == "gstr3b":
        norm_df, missing_cols = normalize_gstr3b_dataframe(df)
        if missing_cols:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"GSTR-3B upload validation error: {' | '.join(missing_cols)}",
            )

        total_records = len(norm_df)
        imported = 0
        duplicates = 0
        rejected = 0
        validation_errors: List[str] = []

        # Track tax periods encountered within the current upload batch
        batch_seen: dict[str, dict] = {}

        for idx, row in norm_df.iterrows():
            row_dict = row.to_dict()
            is_valid, errs = validate_gstr3b_row(row_dict, idx + 1)
            if not is_valid:
                rejected += 1
                validation_errors.extend(errs)
                continue

            period = str(row_dict["tax_period"]).strip()
            out_tax = float(row_dict["output_tax"])
            el_itc = float(row_dict["eligible_itc"])
            itc_rev = float(row_dict.get("itc_reversed", 0.0) or 0.0)
            net_itc = float(row_dict.get("net_itc", el_itc - itc_rev))

            # 1. Intra-batch duplicate and conflict detection
            if period in batch_seen:
                prev = batch_seen[period]
                if (
                    round(prev["output_tax"], 2) == round(out_tax, 2)
                    and round(prev["eligible_itc"], 2) == round(el_itc, 2)
                    and round(prev["itc_reversed"], 2) == round(itc_rev, 2)
                    and round(prev["net_itc"], 2) == round(net_itc, 2)
                ):
                    duplicates += 1
                    continue
                else:
                    # Conflicting figures for the same tax period inside the batch
                    db.rollback()
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=(
                            f"Conflicting GSTR-3B records found in upload for tax period '{period}'. "
                            f"Row {idx + 1} contradicts an earlier row in the same file. "
                            f"Each tax period must specify consistent summary figures."
                        ),
                    )

            batch_seen[period] = {
                "output_tax": out_tax,
                "eligible_itc": el_itc,
                "itc_reversed": itc_rev,
                "net_itc": net_itc,
            }

            # 2. Query existing record in database for this business tenant and tax_period
            existing_record = db.scalar(
                select(GSTR3BReturn).where(
                    GSTR3BReturn.business_id == current_business.id,
                    GSTR3BReturn.tax_period == period,
                )
            )

            if existing_record is not None:
                if (
                    round(existing_record.output_tax, 2) == round(out_tax, 2)
                    and round(existing_record.eligible_itc, 2) == round(el_itc, 2)
                    and round(existing_record.itc_reversed, 2) == round(itc_rev, 2)
                    and round(existing_record.net_itc, 2) == round(net_itc, 2)
                ):
                    duplicates += 1
                    continue
                else:
                    # Update existing record idempotently
                    existing_record.output_tax = out_tax
                    existing_record.eligible_itc = el_itc
                    existing_record.itc_reversed = itc_rev
                    existing_record.net_itc = net_itc
                    existing_record.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
                    imported += 1
            else:
                new_record = GSTR3BReturn(
                    business_id=current_business.id,
                    tax_period=period,
                    output_tax=out_tax,
                    eligible_itc=el_itc,
                    itc_reversed=itc_rev,
                    net_itc=net_itc,
                )
                db.add(new_record)
                imported += 1

        try:
            db.commit()
        except IntegrityError as integ_err:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A conflicting GSTR-3B return was concurrently modified or inserted for this period. Please refresh and retry.",
            )
        except Exception as commit_err:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to persist GSTR-3B records to database. Transaction has been safely rolled back.",
            )

        return {
            "file_name": file.filename,
            "source_type": "gstr3b",
            "business_id": current_business.id,
            "total_records": total_records,
            "imported": imported,
            "duplicates": duplicates,
            "invalid_records": rejected,
            "rejected": rejected,
            "validation_findings": len(validation_errors),
            "errors": validation_errors[:50],
            "message": f"Processed {total_records} GSTR-3B period(s): {imported} imported/updated, {duplicates} duplicates, {rejected} rejected ({len(validation_errors)} findings).",
        }

    # ── Invoice Register Handling (sales_register, gstr1, purchase_register, gstr2a, gstr2b) ──
    norm_df, missing_cols = normalize_invoice_dataframe(df, norm_source)
    if missing_cols:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"CSV schema validation error: {' | '.join(missing_cols)}",
        )

    total_records = len(norm_df)
    imported = 0
    duplicates = 0
    rejected = 0
    validation_errors: List[str] = []
    seen_in_batch = set()

    for idx, row in norm_df.iterrows():
        row_dict = row.to_dict()
        is_valid, errs = validate_invoice_row(row_dict, idx + 1)
        if not is_valid:
            rejected += 1
            validation_errors.extend(errs)
            continue

        invoice_no = str(row_dict["invoice_no"]).strip()
        gstin = str(row_dict.get("gstin") or "").strip().upper()

        inv_date = parse_date_safely(row_dict["invoice_date"])
        if not inv_date:
            rejected += 1
            validation_errors.append(f"Row {idx + 1}: Unrecognized date format '{row_dict['invoice_date']}'")
            continue

        try:
            taxable_value = float(row_dict["taxable_value"])
            gst_amount = float(row_dict["gst_amount"])
        except (ValueError, TypeError):
            rejected += 1
            validation_errors.append(f"Row {idx + 1}: Invalid numeric taxable_value or gst_amount")
            continue

        # Intra-batch duplicate check
        batch_key = (invoice_no, norm_source)
        if batch_key in seen_in_batch:
            duplicates += 1
            continue

        # Database duplicate check for active business
        existing = db.scalar(
            select(Invoice).where(
                Invoice.invoice_no == invoice_no,
                Invoice.business_id == current_business.id,
                Invoice.source == norm_source,
            )
        )
        if existing:
            duplicates += 1
            seen_in_batch.add(batch_key)
            continue

        invoice = Invoice(
            invoice_no=invoice_no,
            invoice_date=inv_date,
            gstin=gstin,
            taxable_value=taxable_value,
            gst_amount=gst_amount,
            source=norm_source,
            business_id=current_business.id,
        )
        db.add(invoice)
        seen_in_batch.add(batch_key)
        imported += 1

    db.commit()

    return {
        "file_name": file.filename,
        "source_type": norm_source,
        "business_id": current_business.id,
        "total_records": total_records,
        "imported": imported,
        "duplicates": duplicates,
        "invalid_records": rejected,
        "rejected": rejected,
        "validation_findings": len(validation_errors),
        "errors": validation_errors[:50],  # Cap preview errors
        "message": f"Processed {total_records} records: {imported} imported, {duplicates} duplicates, {rejected} rejected ({len(validation_errors)} findings).",
    }

