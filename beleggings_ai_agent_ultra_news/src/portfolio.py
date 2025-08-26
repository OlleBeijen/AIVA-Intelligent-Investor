# src/portfolio.pyfrom __future__ import annotations
from typing import Mapping, List, Dict, Any
import pandas as pd

BASE_COLS = ["sector", "covered", "missing", "avg_price", "median_price", "tickers"]

def sector_report(
    sectors: Mapping[str, List[str]] | None,
    last_prices: Mapping[str, float] | None
) -> pd.DataFrame:
    """
    Robuuste sector-tabel.
    Geeft ALTIJD een DataFrame met kolom 'sector' terug, ook als er geen data is.
    Kolommen: sector, covered, missing, avg_price, median_price, tickers
    """
    sectors = sectors or {}
    last_prices = last_prices or {}

    # Geen sectoren? Geef lege DF met juiste kolommen.
    if not sectors:
        return pd.DataFrame(columns=BASE_COLS)

    rows: List[Dict[str, Any]] = []
    for sec, ticks in sectors.items():
        ticks = ticks or []

        covered: List[str] = []
        missing: List[str] = []
        vals: List[float] = []

        for t in ticks:
            v = last_prices.get(t)
            if v is None:
                missing.append(t)
            else:
                covered.append(t)
                try:
                    vals.append(float(v))
                except Exception:
                    # negeer niet-numerieke waarden
                    pass

        avg = sum(vals) / len(vals) if vals else None
        med = float(pd.Series(vals).median()) if vals else None

        rows.append({
            "sector": sec,
            "covered": len(covered),
            "missing": len(missing),
            "avg_price": avg,
            "median_price": med,
            "tickers": ", ".join(covered) if covered else "",
        })

    df = pd.DataFrame(rows, columns=BASE_COLS)
    return df.sort_values("sector", na_position="last")
