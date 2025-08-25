from typing import Dict, List
import pandas as pd

def sector_report(sectors: Dict[str, List[str]], last_prices: Dict[str, float]) -> pd.DataFrame:
    rows = []
    for sector, tickers in sectors.items():
        vals = [last_prices.get(t) for t in tickers if t in last_prices]
        if not vals: 
            continue
        rows.append({
            "sector": sector,
            "tickers": ", ".join([t for t in tickers if t in last_prices]),
            "avg_price": sum(vals)/len(vals),
            "count": len(vals),
        })
    return pd.DataFrame(rows).sort_values("sector")
