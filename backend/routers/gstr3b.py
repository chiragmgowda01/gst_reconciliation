from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query
import pandas as pd
from models.models import Business
from services.auth import get_current_business

router = APIRouter(prefix="/gstr3b", tags=["GSTR-3B"])

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"


@router.get("/summary")
def gstr3b_summary(
    tax_period: Optional[str] = Query(None, description="Optional tax period filter YYYY-MM"),
    current_business: Business = Depends(get_current_business),
):
    df = pd.read_csv(DATA / "gstr3b.csv")
    row = df.iloc[0]

    period = tax_period.strip() if tax_period else str(row["tax_period"])

    # Return demo numbers for business 1, or scoped default for secondary businesses
    if current_business.id == 1:
        return {
            "business_id": current_business.id,
            "tax_period": period,
            "output_tax": float(row["output_tax"]),
            "eligible_itc": float(row["eligible_itc"]),
            "itc_reversed": float(row["itc_reversed"]),
            "net_itc": float(row["net_itc"]),
        }

    return {
        "business_id": current_business.id,
        "tax_period": period,
        "output_tax": 0.0,
        "eligible_itc": 0.0,
        "itc_reversed": 0.0,
        "net_itc": 0.0,
    }