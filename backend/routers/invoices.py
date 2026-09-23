import io
from datetime import datetime
from typing import List, Optional
import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import get_db
from models.models import Business, Invoice
from services.auth import get_current_business
from services.validation import validate_invoice_row


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
    source_type: str = Form(..., description="sales_register, gstr1, purchase_register, or gstr2a"),
    current_business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    valid_sources = {"sales_register", "gstr1", "purchase_register", "gstr2a"}
    if source_type not in valid_sources:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid source_type. Must be one of {list(valid_sources)}",
        )

    if not file.filename.endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV files are supported for upload",
        )

    try:
        content = await file.read()
        df = pd.read_csv(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse CSV file: {str(e)}",
        )

    if df.empty:
        return {
            "file_name": file.filename,
            "total_records": 0,
            "imported": 0,
            "duplicates": 0,
            "invalid_records": 0,
            "errors": [],
            "message": "CSV file was empty. No records imported.",
        }

    total_records = len(df)
    imported = 0
    duplicates = 0
    validation_errors: List[str] = []

    for idx, row in df.iterrows():
        row_dict = row.to_dict()
        is_valid, errs = validate_invoice_row(row_dict, idx + 1)
        if not is_valid:
            validation_errors.extend(errs)
            continue

        invoice_no = str(row_dict["invoice_no"]).strip()
        gstin = str(row_dict.get("customer_gstin") or row_dict.get("supplier_gstin") or row_dict.get("gstin") or "").strip()

        # Parse date safely
        date_raw = str(row_dict["invoice_date"]).strip()
        inv_date = None
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                inv_date = datetime.strptime(date_raw, fmt).date()
                break
            except ValueError:
                continue

        if not inv_date:
            validation_errors.append(f"Row {idx + 1}: Unrecognized date format '{date_raw}'")
            continue

        taxable_value = float(row_dict["taxable_value"])
        gst_amount = float(row_dict["gst_amount"])

        # Check existing duplicate for this business
        existing = db.scalar(
            select(Invoice).where(
                Invoice.invoice_no == invoice_no,
                Invoice.business_id == current_business.id,
                Invoice.source == source_type,
            )
        )
        if existing:
            duplicates += 1
            continue

        invoice = Invoice(
            invoice_no=invoice_no,
            invoice_date=inv_date,
            gstin=gstin,
            taxable_value=taxable_value,
            gst_amount=gst_amount,
            source=source_type,
            business_id=current_business.id,
        )
        db.add(invoice)
        imported += 1

    db.commit()

    return {
        "file_name": file.filename,
        "source_type": source_type,
        "business_id": current_business.id,
        "total_records": total_records,
        "imported": imported,
        "duplicates": duplicates,
        "invalid_records": len(validation_errors),
        "errors": validation_errors[:20],  # Cap preview errors
        "message": f"Processed {total_records} records: {imported} imported, {duplicates} duplicates, {len(validation_errors)} invalid.",
    }
