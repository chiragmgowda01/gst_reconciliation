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
from models.models import Business, GSTR3BReturn, Invoice, User
from services.auth import get_current_business, get_current_user
from services.import_batch import (
    add_gstr3b_batch_item,
    add_invoice_batch_item,
    complete_import_batch,
    create_import_batch,
    is_unique_constraint_violation,
)
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
    query = select(Invoice).where(
        Invoice.business_id == current_business.id,
        Invoice.deleted_at.is_(None),
    )

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
            Invoice.deleted_at.is_(None),
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_business.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Business access is not authorized.")
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
        if not content.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="The CSV file is empty. Add a header row and at least one data row, then try again.",
            )
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = content.decode("latin-1", errors="replace")
        df = pd.read_csv(io.StringIO(text))
    except HTTPException:
        raise
    except pd.errors.EmptyDataError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The CSV file is empty. Add a header row and at least one data row, then try again.",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse CSV file: {str(e)}",
        )

    # Strip any stray BOM or leading/trailing whitespace from column names
    df.columns = [str(c).replace("\ufeff", "").strip() for c in df.columns]

    if df.empty:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The CSV contains headers but no data rows. Add at least one data row, then try again.",
        )

    # ── GSTR-3B Summary Data Handling (Treated as monthly summary level, not invoice level) ──
    if norm_source == "gstr3b":
        norm_df, missing_cols = normalize_gstr3b_dataframe(df)
        if missing_cols:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"GSTR-3B upload validation error: {' | '.join(missing_cols)}",
            )

        total_records = len(norm_df)
        imported = duplicates = revised = rejected = 0
        validation_errors: List[str] = []
        batch_seen: dict[str, dict] = {}
        current_period_values = set()
        if "tax_period" in norm_df.columns:
            for raw_period in norm_df["tax_period"].tolist():
                if pd.notna(raw_period) and str(raw_period).strip():
                    current_period_values.add(str(raw_period).strip()[:10])
        batch_period = next(iter(current_period_values)) if len(current_period_values) == 1 else None

        def snapshot(record: GSTR3BReturn) -> dict:
            return {
                "tax_period": record.tax_period,
                "output_tax": float(record.output_tax),
                "eligible_itc": float(record.eligible_itc),
                "itc_reversed": float(record.itc_reversed),
                "net_itc": float(record.net_itc),
            }

        try:
            batch = create_import_batch(
                db,
                business_id=current_business.id,
                imported_by_user_id=current_user.id,
                source_category="csv_upload",
                source_type="gstr3b",
                original_filename=file.filename,
                tax_period=batch_period,
                total_rows=total_records,
            )

            for idx, row in norm_df.iterrows():
                row_dict = row.to_dict()
                raw_period = row_dict.get("tax_period")
                period = (
                    str(raw_period).strip()[:10]
                    if pd.notna(raw_period) and str(raw_period).strip()
                    else "UNKNOWN"
                )
                is_valid, errs = validate_gstr3b_row(row_dict, idx + 1)
                if not is_valid:
                    rejected += 1
                    validation_errors.extend(errs)
                    add_gstr3b_batch_item(
                        db,
                        batch_id=batch.batch_id,
                        outcome="rejected",
                        tax_period=period,
                        gstr3b_return_id=None,
                        rejection_reason="; ".join(errs) or "Row failed GSTR-3B validation.",
                    )
                    continue

                out_tax = float(row_dict["output_tax"])
                el_itc = float(row_dict["eligible_itc"])
                itc_rev = float(row_dict.get("itc_reversed", 0.0) or 0.0)
                net_itc = float(row_dict.get("net_itc", el_itc - itc_rev))
                incoming_values = {
                    "tax_period": period,
                    "output_tax": out_tax,
                    "eligible_itc": el_itc,
                    "itc_reversed": itc_rev,
                    "net_itc": net_itc,
                }

                # Same-period values repeated in one file are accounted as
                # duplicates. Conflicting rows reject the entire transaction.
                prior = batch_seen.get(period)
                if prior is not None:
                    if any(
                        round(prior[field], 2) != round(incoming_values[field], 2)
                        for field in ("output_tax", "eligible_itc", "itc_reversed", "net_itc")
                    ):
                        raise HTTPException(
                            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=(
                                f"Conflicting GSTR-3B records found in upload for tax period '{period}'. "
                                f"Row {idx + 1} contradicts an earlier row in this file. "
                                "Each tax period must specify consistent summary figures."
                            ),
                        )
                    duplicates += 1
                    add_gstr3b_batch_item(
                        db,
                        batch_id=batch.batch_id,
                        outcome="duplicate",
                        tax_period=period,
                        gstr3b_return_id=prior["record_id"],
                        new_values=incoming_values,
                    )
                    continue

                existing_record = db.scalar(
                    select(GSTR3BReturn)
                    .where(
                        GSTR3BReturn.business_id == current_business.id,
                        GSTR3BReturn.tax_period == period,
                    )
                    .with_for_update()
                )

                if existing_record is not None and existing_record.deleted_at is not None:
                    previous_values = snapshot(existing_record)
                    existing_record.output_tax = out_tax
                    existing_record.eligible_itc = el_itc
                    existing_record.itc_reversed = itc_rev
                    existing_record.net_itc = net_itc
                    existing_record.deleted_at = None
                    existing_record.import_batch_id = batch.batch_id
                    existing_record.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
                    imported += 1
                    outcome = "imported"
                    add_gstr3b_batch_item(
                        db,
                        batch_id=batch.batch_id,
                        outcome=outcome,
                        tax_period=period,
                        gstr3b_return_id=existing_record.id,
                        previous_values=previous_values,
                        new_values=incoming_values,
                    )
                elif existing_record is None:
                    existing_record = GSTR3BReturn(
                        business_id=current_business.id,
                        tax_period=period,
                        output_tax=out_tax,
                        eligible_itc=el_itc,
                        itc_reversed=itc_rev,
                        net_itc=net_itc,
                        import_batch_id=batch.batch_id,
                    )
                    db.add(existing_record)
                    db.flush()
                    imported += 1
                    add_gstr3b_batch_item(
                        db,
                        batch_id=batch.batch_id,
                        outcome="imported",
                        tax_period=period,
                        gstr3b_return_id=existing_record.id,
                        new_values=incoming_values,
                    )
                else:
                    previous_values = snapshot(existing_record)
                    if all(
                        round(previous_values[field], 2) == round(incoming_values[field], 2)
                        for field in ("output_tax", "eligible_itc", "itc_reversed", "net_itc")
                    ):
                        duplicates += 1
                        add_gstr3b_batch_item(
                            db,
                            batch_id=batch.batch_id,
                            outcome="duplicate",
                            tax_period=period,
                            gstr3b_return_id=existing_record.id,
                            new_values=incoming_values,
                        )
                    else:
                        existing_record.output_tax = out_tax
                        existing_record.eligible_itc = el_itc
                        existing_record.itc_reversed = itc_rev
                        existing_record.net_itc = net_itc
                        existing_record.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
                        revised += 1
                        add_gstr3b_batch_item(
                            db,
                            batch_id=batch.batch_id,
                            outcome="revised",
                            tax_period=period,
                            gstr3b_return_id=existing_record.id,
                            previous_values=previous_values,
                            new_values=incoming_values,
                        )

                batch_seen[period] = {**incoming_values, "record_id": existing_record.id}

            complete_import_batch(
                batch,
                imported_rows=imported,
                duplicate_rows=duplicates,
                revised_rows=revised,
                rejected_rows=rejected,
            )
            db.commit()
        except HTTPException:
            db.rollback()
            raise
        except IntegrityError as exc:
            db.rollback()
            if is_unique_constraint_violation(exc) or "conflict" in str(getattr(exc, "orig", "")).lower():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A conflicting GSTR-3B return was concurrently modified or inserted for this period. Refresh and retry the upload.",
                ) from None
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="The GSTR-3B upload could not be saved. All batch and return changes were rolled back.",
            ) from None
        except Exception:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="The GSTR-3B upload could not be saved. All batch and return changes were rolled back.",
            ) from None

        return {
            "file_name": file.filename,
            "import_batch_id": str(batch.batch_id),
            "source_type": "gstr3b",
            "business_id": current_business.id,
            "total_records": total_records,
            "imported": imported,
            "duplicates": duplicates,
            "revised": revised,
            "invalid_records": rejected,
            "rejected": rejected,
            "validation_findings": len(validation_errors),
            "errors": validation_errors[:50],
            "status": batch.status,
            "message": (
                f"Processed {total_records} GSTR-3B period row(s): {imported} imported, "
                f"{duplicates} duplicates, {revised} revised, {rejected} rejected "
                f"({len(validation_errors)} findings)."
            ),
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
    seen_in_batch: dict[tuple[str, str], Invoice] = {}
    try:
        batch = create_import_batch(
            db,
            business_id=current_business.id,
            imported_by_user_id=current_user.id,
            source_category="csv_upload",
            source_type=norm_source,
            original_filename=file.filename,
            total_rows=total_records,
        )

        for idx, row in norm_df.iterrows():
            row_dict = row.to_dict()
            is_valid, errs = validate_invoice_row(row_dict, idx + 1)
            if not is_valid:
                rejected += 1
                validation_errors.extend(errs)
                add_invoice_batch_item(
                    db,
                    batch_id=batch.batch_id,
                    outcome="rejected",
                    rejection_reason="; ".join(errs) or "Row failed invoice validation.",
                )
                continue

            invoice_no = str(row_dict["invoice_no"]).strip()
            gstin = str(row_dict.get("gstin") or "").strip().upper()

            inv_date = parse_date_safely(row_dict["invoice_date"])
            if not inv_date:
                rejected += 1
                reason = f"Row {idx + 1}: Unrecognized date format '{row_dict['invoice_date']}'"
                validation_errors.append(reason)
                add_invoice_batch_item(
                    db, batch_id=batch.batch_id, outcome="rejected", rejection_reason=reason
                )
                continue

            try:
                taxable_value = float(row_dict["taxable_value"])
                gst_amount = float(row_dict["gst_amount"])
            except (ValueError, TypeError):
                rejected += 1
                reason = f"Row {idx + 1}: Invalid numeric taxable_value or gst_amount"
                validation_errors.append(reason)
                add_invoice_batch_item(
                    db, batch_id=batch.batch_id, outcome="rejected", rejection_reason=reason
                )
                continue

            batch_key = (invoice_no, norm_source)
            prior_in_batch = seen_in_batch.get(batch_key)
            if prior_in_batch is not None:
                duplicates += 1
                add_invoice_batch_item(
                    db,
                    batch_id=batch.batch_id,
                    outcome="duplicate",
                    invoice_id=prior_in_batch.id,
                )
                continue

            existing = db.scalar(
                select(Invoice).where(
                    Invoice.invoice_no == invoice_no,
                    Invoice.business_id == current_business.id,
                    Invoice.source == norm_source,
                    Invoice.deleted_at.is_(None),
                ).with_for_update()
            )
            if existing is not None:
                duplicates += 1
                seen_in_batch[batch_key] = existing
                add_invoice_batch_item(
                    db, batch_id=batch.batch_id, outcome="duplicate", invoice_id=existing.id
                )
                continue

            invoice = Invoice(
                invoice_no=invoice_no,
                invoice_date=inv_date,
                gstin=gstin,
                taxable_value=taxable_value,
                gst_amount=gst_amount,
                source=norm_source,
                business_id=current_business.id,
                import_batch_id=batch.batch_id,
            )
            db.add(invoice)
            db.flush()
            seen_in_batch[batch_key] = invoice
            imported += 1
            add_invoice_batch_item(
                db, batch_id=batch.batch_id, outcome="imported", invoice_id=invoice.id
            )

        complete_import_batch(
            batch, imported_rows=imported, duplicate_rows=duplicates, rejected_rows=rejected
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if not is_unique_constraint_violation(exc):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to persist CSV import. The batch and invoice changes were rolled back.",
            ) from None
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A conflicting invoice import was concurrently inserted. Please retry the upload.",
        )
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist CSV import. The batch and invoice changes were rolled back.",
        )

    return {
        "file_name": file.filename,
        "import_batch_id": str(batch.batch_id),
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

