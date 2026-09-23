from pathlib import Path
from fastapi import APIRouter, Depends
import pandas as pd
from models.models import Business
from services.auth import get_current_business

router = APIRouter(prefix="/gstr3b", tags=["GSTR-3B"])

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"


@router.get("/summary")
def gstr3b_summary(current_business: Business = Depends(get_current_business)):
    df = pd.read_csv(DATA / "gstr3b.csv")
    row = df.iloc[0]

    # Return demo numbers for business 1, or scoped default for secondary businesses
    if current_business.id == 1:
        return {
            "business_id": current_business.id,
            "tax_period": row["tax_period"],
            "output_tax": float(row["output_tax"]),
            "eligible_itc": float(row["eligible_itc"]),
            "itc_reversed": float(row["itc_reversed"]),
            "net_itc": float(row["net_itc"]),
        }

    return {
        "business_id": current_business.id,
        "tax_period": row["tax_period"],
        "output_tax": 0.0,
        "eligible_itc": 0.0,
        "itc_reversed": 0.0,
        "net_itc": 0.0,
    }