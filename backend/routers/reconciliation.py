from fastapi import APIRouter
from reconciliation.reconcile import reconcile
import json

router = APIRouter()


@router.get("/reconcile")
def run_reconciliation():
    sales = reconcile("sales_register.csv", "gstr1.csv")
    purchases = reconcile("purchase_register.csv", "gstr2a.csv")

    sales_data = json.loads(sales.to_json(orient="records"))
    purchase_data = json.loads(purchases.to_json(orient="records"))

    return {
        "sales": sales_data,
        "purchases": purchase_data
    }