from __future__ import annotations
from typing import Dict, List, Any
import math
import pandas as pd
from .fundamentals import get_fundamentals
from .dcf import intrinsic_value

def _safe(v, default=None):
    try:
        if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            return default
        return float(v)
    except Exception:
        return default

def compute_scores(tickers: List[str], price_map: Dict[str, float] | None = None,
                   dcf_growth: float = 0.04, dcf_discount: float = 0.10) -> pd.DataFrame:
    f = get_fundamentals(tickers)
    rows = []
    for t in tickers:
        d = f.get(t, {})
        price = _safe(d.get("price") or (price_map or {}).get(t))
        pe = _safe(d.get("trailingPE"))
        pb = _safe(d.get("priceToBook"))
        ev_ebitda = _safe(d.get("enterpriseToEbitda"))
        fcf = _safe(d.get("freeCashflow"))
        sh_out = _safe(d.get("sharesOutstanding"))
        if fcf and fcf < 1 and sh_out and price and price > 1:
            fcf = fcf * sh_out
        iv = intrinsic_value(price=price, fcf=fcf, growth=dcf_growth, discount=dcf_discount) if price and fcf else None
        mos = (iv/price - 1.0) if (iv and price) else None
        v_parts = []
        for x in [pe, pb, ev_ebitda]:
            if x and x > 0:
                v_parts.append(1.0 / x)
        value_score = sum(v_parts)/len(v_parts) if v_parts else None
        quality = 0.0
        ebitda = _safe(d.get("ebitda"))
        if ebitda and ebitda > 0: quality += 0.5
        if fcf and fcf > 0: quality += 0.5
        rows.append({
            "ticker": t,
            "name": d.get("longName") or t,
            "price": price,
            "PE": pe, "PB": pb, "EV/EBITDA": ev_ebitda,
            "FCF": fcf,
            "IntrinsicValue": iv,
            "MarginOfSafety": mos,
            "ValueScore": value_score,
            "Quality": quality,
            "currency": d.get("currency"),
            "source": d.get("link"),
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df["mos_rank"] = df["MarginOfSafety"].rank(ascending=False, method="min", na_option="bottom")
        df["value_rank"] = df["ValueScore"].rank(ascending=False, method="min", na_option="bottom")
        df["quality_rank"] = df["Quality"].rank(ascending=False, method="min", na_option="bottom")
        df["score"] = (df["mos_rank"] * 0.5 + df["value_rank"] * 0.3 + df["quality_rank"] * 0.2)
        df = df.sort_values("score")
    return df