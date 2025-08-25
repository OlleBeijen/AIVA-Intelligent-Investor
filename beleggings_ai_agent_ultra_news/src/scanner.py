from typing import Dict, List, Tuple
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

def _download(tickers: List[str], lookback_days: int = 400):
    start = datetime.today() - timedelta(days=lookback_days*2)
    out = {}
    for t in tickers:
        df = yf.download(t, start=start.strftime("%Y-%m-%d"), progress=False, auto_adjust=True)
        if not df.empty:
            out[t] = df.rename(columns=str.title).dropna()
    return out

def _factors(df: pd.DataFrame) -> pd.Series:
    px = df["Close"]
    ret_252 = px.pct_change(252).iloc[-1] if len(px) > 252 else None
    ret_63  = px.pct_change(63).iloc[-1] if len(px) > 63 else None
    vol20   = px.pct_change().rolling(20).std().iloc[-1]
    high_52 = px.rolling(252).max().iloc[-1] if len(px) > 252 else px.max()
    dist_h  = (px.iloc[-1] / high_52) - 1 if high_52 else None
    ma50 = px.rolling(50).mean().iloc[-1] if len(px) > 50 else None
    uptrend = 1.0 if (ma50 and px.iloc[-1] > ma50) else 0.0
    return pd.Series({"mom_12m": ret_252, "mom_3m": ret_63, "vol_20d": vol20, "dist_52w_high": dist_h, "uptrend": uptrend})

def screen_universe(sectors: Dict[str, List[str]], top_n: int = 5) -> Dict[str, List[Tuple[str, float]]]:
    all_tickers = sorted({t for ts in sectors.values() for t in ts})
    data = _download(all_tickers, 400)
    rows = []
    for t, df in data.items():
        if len(df) < 120: 
            continue
        fac = _factors(df)
        rows.append({"ticker": t, **fac.to_dict()})
    if not rows:
        return {s: [] for s in sectors}
    fac = pd.DataFrame(rows).dropna()
    if fac.empty:
        return {s: [] for s in sectors}

    fac["r_mom12"] = fac["mom_12m"].rank(pct=True)
    fac["r_mom3"]  = fac["mom_3m"].rank(pct=True)
    fac["r_vol"]   = (-fac["vol_20d"]).rank(pct=True)
    fac["r_dist"]  = (-fac["dist_52w_high"]).rank(pct=True)
    fac["r_trend"] = fac["uptrend"].rank(pct=True)
    fac["score"]   = fac[["r_mom12","r_mom3","r_vol","r_dist","r_trend"]].mean(axis=1)

    res = {}
    for sec, ts in sectors.items():
        sdf = fac[fac["ticker"].isin(ts)].sort_values("score", ascending=False)
        res[sec] = list(zip(sdf["ticker"].head(top_n), sdf["score"].head(top_n)))
    return res
