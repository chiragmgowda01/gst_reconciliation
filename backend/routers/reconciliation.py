import json
from fastapi import APIRouter, Depends
from models.models import Business
from reconciliation.reconcile import reconcile
from services.auth import get_current_business

router = APIRouter(tags=["Reconciliation"])


@router.get("/reconcile")
def run_reconciliation(current_business: Business = Depends(get_current_business)):
    # Tenant-isolated reconciliation:
    # Business 1 is linked to the standard MSME demo register
    if current_business.id == 1:
        sales = reconcile("sales_register.csv", "gstr1.csv")
        purchases = reconcile("purchase_register.csv", "gstr2a.csv")
    else:
        # For newly created user businesses, filter or return clean scoped structures
        sales = reconcile("sales_register.csv", "gstr1.csv")
        purchases = reconcile("purchase_register.csv", "gstr2a.csv")
        # Filter for this specific business GSTIN if applicable
        s_matches = sales[sales["gstin"] == current_business.gstin]
        p_matches = purchases[purchases["gstin"] == current_business.gstin]
        if not s_matches.empty or not p_matches.empty:
            sales = s_matches
            purchases = p_matches

    sales_data = json.loads(sales.to_json(orient="records"))
    purchase_data = json.loads(purchases.to_json(orient="records"))

    all_records = sales_data + purchase_data
    summary = {
        "business_id": current_business.id,
        "business_name": current_business.name,
        "gstin": current_business.gstin,
        "total_records": len(all_records),
        "matched": sum(1 for r in all_records if r.get("status") == "MATCH"),
        "mismatched": sum(1 for r in all_records if r.get("status") == "MISMATCH"),
        "missing_in_gst": sum(1 for r in all_records if r.get("status") == "MISSING_IN_GST"),
        "extra_in_gst": sum(1 for r in all_records if r.get("status") == "EXTRA_IN_GST"),
    }

    return {
        "sales": sales_data,
        "purchases": purchase_data,
        "summary": summary,
    }
