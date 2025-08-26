from __future__ import annotations
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf

def _sanitize(tickers: List[str]) -> List[str]:
    out = []
    for t in tickers or []:
        t = str(t).strip().upper()
        if t:
            out.append(t)
    return list(dict.fromkeys(out))

def fetch_prices(tickers: List[str], lookback_days: int = 365) -> Dict[str, pd.DataFrame]:
    """Fetch daily OHLCV per ticker. Always returns a dict[ticker]=DataFrame with 'Close' column if possible."""
    tickers = _sanitize(tickers)
    if not tickers:
        return {}
    start = (datetime.utcnow() - timedelta(days=max(lookback_days, 30))).strftime("%Y-%m-%d")
    out: Dict[str, pd.DataFrame] = {}
    for t in tickers:
        try:
            df = yf.download(t, start=start, interval="1d", progress=False, auto_adjust=False, group_by='column')
            if isinstance(df.columns, pd.MultiIndex):
                if ("Close","") in df.columns:
                    df = df.rename(columns={("Close",""): "Close"})
                elif ("Close", t) in df.columns:
                    df = df.rename(columns={("Close", t): "Close"})
                else:
                    close_cols = [c for c in df.columns if isinstance(c, tuple) and c[0]=="Close"]
                    if close_cols:
                        df = df.rename(columns={close_cols[0]: "Close"})
            if "Close" not in df.columns and "Adj Close" in df.columns:
                df = df.rename(columns={"Adj Close": "Close"})
            df = df[["Close"]].dropna()
            out[t] = df
        except Exception:
            pass
    return out

def latest_close(tickers: List[str], lookback_days: int = 10) -> Dict[str, float]:
    px = fetch_prices(tickers, lookback_days=lookback_days)
    res: Dict[str, float] = {}
    for t, df in px.items():
        try:
            res[t] = float(pd.to_numeric(df["Close"], errors="coerce").dropna().iloc[-1])
        except Exception:
            pass
    return res
