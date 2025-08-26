from typing import Dict, List, Tuple
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

def _flatten_columns(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        try:
            df = df.xs(ticker, axis=1, level=1)
        except Exception:
            df.columns = df.columns.get_level_values(0)
    return df

def _to_series(close_like) -> pd.Series:
    if isinstance(close_like, pd.Series):
        s = close_like
    elif isinstance(close_like, pd.DataFrame):
        s = close_like.iloc[:, 0] if close_like.shape[1] >= 1 else pd.Series(dtype='float64')
    else:
        s = pd.Series(close_like).squeeze()
    s = pd.to_numeric(s, errors='coerce')
    s.name = 'Close'
    return s

def _download(tickers: List[str], lookback_days: int = 400):
    start = datetime.today() - timedelta(days=lookback_days*2)
    out = {}
    for t in tickers:
        df = yf.download(t, start=start.strftime("%Y-%m-%d"), progress=False, auto_adjust=True, group_by="column", threads=False)
        if df is None or df.empty:
            continue
        df = _flatten_columns(df, t).rename(columns=str.title).dropna(how="all")
        # ensure Close exists and is 1D
        if "Close" not in df.columns and "Adj Close" in df.columns:
            df["Close"] = df["Adj Close"]
        if isinstance(df.get("Close"), pd.DataFrame):
            df["Close"] = df["Close"].iloc[:, 0]
        df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
        df = df.dropna(subset=["Close"])
        if not df.empty:
            out[t] = df
    return out

def _factors(df: pd.DataFrame) -> pd.Series:
    px = _to_series(df.get("Close"))
    if px is None or px.empty:
        return pd.Series({"mom_12m": None, "mom_3m": None, "vol_20d": None, "dist_52w_high": None, "uptrend": None})
    ret_252 = px.pct_change(252).iloc[-1] if len(px) > 252 else None
    ret_63  = px.pct_change(63).iloc[-1] if len(px) > 63 else None
    vol20   = px.pct_change().rolling(20).std().iloc[-1] if len(px) > 20 else None
    if len(px) > 252:
        high_52 = px.rolling(252).max().iloc[-1]
    else:
        high_52 = px.max()
    # Avoid ambiguous truth values and divide-by-zero
    try:
        h = float(high_52)
        dist_h = (float(px.iloc[-1]) / h) - 1 if h not in (0.0, float("inf")) else None
    except Exception:
        dist_h = None
    ma50 = px.rolling(50).mean().iloc[-1] if len(px) > 50 else None
    uptrend = 1.0 if (ma50 is not None and float(px.iloc[-1]) > float(ma50)) else 0.0
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

    fac["r_mom12"] = fac["mom_12m"].rank(pct=True, na_option="bottom")
    fac["r_mom3"]  = fac["mom_3m"].rank(pct=True, na_option="bottom")
    fac["r_vol"]   = (-fac["vol_20d"]).rank(pct=True, na_option="bottom")
    fac["r_dist"]  = (-fac["dist_52w_high"]).rank(pct=True, na_option="bottom")
    fac["r_trend"] = fac["uptrend"].rank(pct=True, na_option="bottom")
    fac["score"]   = fac[["r_mom12","r_mom3","r_vol","r_dist","r_trend"]].mean(axis=1)

    res = {}
    for sec, ts in sectors.items():
        sdf = fac[fac["ticker"].isin(ts)].sort_values("score", ascending=False)
        res[sec] = list(zip(sdf["ticker"].head(top_n), sdf["score"].head(top_n)))
    return res
