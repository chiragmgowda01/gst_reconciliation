from fastapi import APIRouter
from pathlib import Path
import pandas as pd

router = APIRouter(prefix="/gstr3b", tags=["GSTR-3B"])

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"


@router.get("/summary")
def gstr3b_summary():
    df = pd.read_csv(DATA / "gstr3b.csv")

    row = df.iloc[0]

    return {
        "tax_period": row["tax_period"],
        "output_tax": float(row["output_tax"]),
        "eligible_itc": float(row["eligible_itc"]),
        "itc_reversed": float(row["itc_reversed"]),
        "net_itc": float(row["net_itc"])
    }