from __future__ import annotations
from typing import Dict, List
from datetime import datetime, timedelta
import time
import pandas as pd
import requests
import yfinance as yf

def _sanitize(tickers: List[str]) -> List[str]:
    out = []
    for t in tickers or []:
        t = str(t).strip().upper()
        if t:
            out.append(t)
    return list(dict.fromkeys(out))

def _normalize_close(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    # yfinance kan multiindex kolommen geven
    if isinstance(df.columns, pd.MultiIndex):
        # Zoek een "Close"-kolom
        close_cols = [c for c in df.columns if isinstance(c, tuple) and c[0] == "Close"]
        if close_cols:
            df = df.rename(columns={close_cols[0]: "Close"})
    # Fallback van Adj Close → Close
    if "Close" not in df.columns and "Adj Close" in df.columns:
        df = df.rename(columns={"Adj Close": "Close"})
    # Tot slot alleen Close, netjes numeriek
    if "Close" in df.columns:
        close = pd.to_numeric(df["Close"], errors="coerce").dropna()
        return pd.DataFrame({"Close": close})
    return pd.DataFrame()

def fetch_prices(tickers: List[str], lookback_days: int = 365) -> Dict[str, pd.DataFrame]:
    """
    Haal dagdata per ticker op. Probeert eerst Ticker.history (met eigen sessie en repair),
    valt dan terug op yf.download. Resultaat: dict[ticker] -> DataFrame met 'Close'.
    """
    tickers = _sanitize(tickers)
    if not tickers:
        return {}

    start = (datetime.utcnow() - timedelta(days=max(lookback_days, 30))).strftime("%Y-%m-%d")

    # Eigen sessie + user-agent helpt vaak tegen "tz missing"/HTML responses
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": "Mozilla/5.0 (AIVA-Intelligent-Investor; +local)"
    })

    out: Dict[str, pd.DataFrame] = {}

    for t in tickers:
        df = pd.DataFrame()

        # 1) Probeer history (meestal stabieler, ondersteunt session)
        try:
            tk = yf.Ticker(t, session=sess)
            df1 = tk.history(start=start, interval="1d", auto_adjust=False, actions=False, repair=True)
            df = _normalize_close(df1, t)
        except Exception:
            df = pd.DataFrame()

        # 2) Fallback: download (zonder session-param), soms werkt dit wel
        if df.empty:
            try:
                df2 = yf.download(
                    t, start=start, interval="1d",
                    progress=False, auto_adjust=False, group_by="column", threads=False
                )
                df = _normalize_close(df2, t)
            except Exception:
                df = pd.DataFrame()

        # 3) Als het nog leeg is: skippen (netwerk/Yahoo blokkade e.d.)
        if not df.empty:
            out[t] = df
        else:
            # kleine pauze om throttling te verminderen
            time.sleep(0.2)

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
