from typing import Dict, List, Tuple
import pandas as pd

def portfolio_weights_from_positions(positions: pd.DataFrame, last_prices: Dict[str, float]) -> pd.Series:
    vals = []
    for _, row in positions.iterrows():
        t = str(row["ticker"]).strip()
        q = float(row.get("qty", 0) or 0)
        px = float(last_prices.get(t, 0))
        vals.append((t, q * px))
    df = pd.DataFrame(vals, columns=["ticker","value"]).groupby("ticker").sum()
    total = df["value"].sum()
    if total <= 0:
        return pd.Series(dtype=float)
    w = df["value"] / total
    w.name = "weight"
    return w

def aggregate_by_sector(weights: pd.Series, sectors: Dict[str, List[str]]) -> pd.Series:
    rows = []
    for sec, ts in sectors.items():
        sec_w = weights[weights.index.isin(ts)].sum()
        rows.append((sec, sec_w))
    out = pd.Series(dict(rows)).sort_index()
    out.name = "sector_weight"
    return out

def nudge_vs_plan(sector_w: pd.Series, plan: Dict[str, float], band_pp: float = 5.0) -> List[str]:
    nudges = []
    for sec, tgt in plan.items():
        w = float(sector_w.get(sec, 0.0))
        lo = max(0.0, tgt - band_pp/100.0)
        hi = min(1.0, tgt + band_pp/100.0)
        if w < lo:
            nudges.append(f"{sec}: onder doel (huidig {w:.1%} vs doel {tgt:.1%} ±{band_pp:.0f}pp).")
        elif w > hi:
            nudges.append(f"{sec}: boven doel (huidig {w:.1%} vs doel {tgt:.1%} ±{band_pp:.0f}pp).")
    return nudges