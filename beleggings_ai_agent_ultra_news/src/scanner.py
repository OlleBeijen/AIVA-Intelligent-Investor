# src/scanner.py
from __future__ import annotations
from typing import Dict, List, Tuple
import math
import numpy as np
import pandas as pd

from .data_sources import fetch_prices

# =============== Helpers ===============

def _to_close_series(px: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
    out: Dict[str, pd.Series] = {}
    for t, df in px.items():
        try:
            s = df["Close"].astype(float).dropna()
            if len(s) >= 60:  # minimaal 60 dagen om iets zinnigs te berekenen
                out[t] = s
        except Exception:
            pass
    return out

def _safe_pct(a: float, b: float) -> float:
    try:
        if b and not math.isclose(b, 0.0):
            return float(a / b - 1.0)
    except Exception:
        pass
    return float("nan")

def _factors(s: pd.Series) -> Dict[str, float]:
    """Bereken simpele factorfeatures zonder te crashen."""
    s = s.dropna()
    if s.empty:
        return {}
    last = float(s.iloc[-1])
    # 52 weken ~ 252 handelsdagen
    look = min(252, len(s))
    window = s.iloc[-look:]
    hi = float(window.max())
    lo = float(window.min())

    # momentum 20/60/120
    def mom(n: int) -> float:
        if len(s) > n:
            return _safe_pct(float(s.iloc[-1]), float(s.iloc[-n-1]))
        return float("nan")

    m20  = mom(20)
    m60  = mom(60)
    m120 = mom(120)

    # afstand tot high/low
    dist_h = _safe_pct(last, hi)   # negatief als onder high
    dist_l = _safe_pct(last, lo)   # positief als boven low

    # volatiliteit (std van dagret)
    rets = window.pct_change().dropna()
    vol = float(rets.std()) if not rets.empty else float("nan")

    # samengestelde score: momentum ↑, dichter bij low (positief dist_l), verder van high (negatieve dist_h is OK)
    # penaliseer heel hoge vol
    parts = []
    for v in [m20, m60, m120, dist_l, -dist_h]:
        if not math.isnan(v):
            parts.append(v)
    score = float(np.nanmean(parts)) if parts else float("nan")
    if not math.isnan(vol) and vol > 0:
        score = score / (1.0 + 3.0 * vol)

    return {
        "last": last,
        "high_52": hi,
        "low_52": lo,
        "mom20": m20,
        "mom60": m60,
        "mom120": m120,
        "dist_high": dist_h,
        "dist_low": dist_l,
        "vol": vol,
        "score": score,
    }

# =============== Public API ===============

def screen_universe(sectors: Dict[str, List[str]], lookback_days: int = 400, top_k: int = 5) -> Dict[str, List[Tuple[str, float]]]:
    """
    Maakt per sector een lijst met (ticker, score), gesorteerd aflopend.
    - gebruikt fetch_prices (Finnhub -> Stooq) i.p.v. yfinance
    - faalt nooit hard: lege sectoren geven []
    """
    res: Dict[str, List[Tuple[str, float]]] = {}
    sectors = sectors or {}

    # Verzamel alle tickers uniek
    universe: List[str] = []
    for _, ticks in sectors.items():
        if not ticks: 
            continue
        for t in ticks:
            if t and t not in universe:
                universe.append(t)

    if not universe:
        return {sec: [] for sec in sectors.keys()}

    # 1) Haal prijzen (deelsucces oké)
    px = fetch_prices(universe, lookback_days=lookback_days)
    closes = _to_close_series(px)

    # 2) Factors per ticker
    fac_map: Dict[str, Dict[str, float]] = {}
    for t, s in closes.items():
        f = _factors(s)
        if f and not math.isnan(f.get("score", float("nan"))):
            fac_map[t] = f

    # 3) Per sector: sorteer op score en pak top_k
    for sec, ticks in sectors.items():
        rows: List[Tuple[str, float]] = []
        for t in (ticks or []):
            f = fac_map.get(t)
            if f:
                rows.append((t, float(f["score"])))
        rows.sort(key=lambda x: x[1], reverse=True)
        res[sec] = rows[:top_k]
    return res
