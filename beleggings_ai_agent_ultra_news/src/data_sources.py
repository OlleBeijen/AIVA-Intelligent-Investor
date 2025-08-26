from __future__ import annotations
from typing import Dict, List
from datetime import datetime, timedelta
import time, os
import pandas as pd
import requests
import yfinance as yf

# ---------- helpers ----------
def _sanitize(tickers: List[str]) -> List[str]:
    out = []
    for t in tickers or []:
        t = str(t).strip().upper()
        if t:
            out.append(t)
    return list(dict.fromkeys(out))

def _normalize_close(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    # yfinance kan MultiIndex kolommen geven
    if isinstance(df.columns, pd.MultiIndex):
        close_cols = [c for c in df.columns if isinstance(c, tuple) and c[0] == "Close"]
        if close_cols:
            df = df.rename(columns={close_cols[0]: "Close"})
    # fallback Adj Close → Close
    if "Close" not in df.columns and "Adj Close" in df.columns:
        df = df.rename(columns={"Adj Close": "Close"})
    if "Close" in df.columns:
        close = pd.to_numeric(df["Close"], errors="coerce").dropna()
        if not close.empty:
            return pd.DataFrame({"Close": close})
    return pd.DataFrame()

def _sleep_smol():
    time.sleep(0.15)

# ---------- yfinance ----------
def _fetch_yf_one(ticker: str, start: str, session: requests.Session | None) -> pd.DataFrame:
    # 1) history (stabieler), 2) download als fallback
    try:
        tk = yf.Ticker(ticker, session=session)
        df1 = tk.history(start=start, interval="1d", auto_adjust=False, actions=False, repair=True)
        df = _normalize_close(df1)
        if not df.empty:
            return df
    except Exception:
        pass
    try:
        df2 = yf.download(
            ticker, start=start, interval="1d",
            progress=False, auto_adjust=False, group_by="column", threads=False
        )
        return _normalize_close(df2)
    except Exception:
        return pd.DataFrame()

def _fetch_yfinance(tickers: List[str], start: str) -> Dict[str, pd.DataFrame]:
    sess = requests.Session()
    sess.headers.update({"User-Agent": "Mozilla/5.0 (AIVA-Intelligent-Investor; +local)"})
    out: Dict[str, pd.DataFrame] = {}
    for t in tickers:
        df = _fetch_yf_one(t, start, sess)
        if not df.empty:
            out[t] = df
        _sleep_smol()
    return out

# ---------- Finnhub ----------
def _fetch_finnhub_one(ticker: str, start_ts: int, end_ts: int, key: str) -> pd.DataFrame:
    # probeer exact symbool, anders zonder suffix (.AS → ASML)
    for sym in (ticker, ticker.split(".")[0]):
        url = "https://finnhub.io/api/v1/stock/candle"
        params = {"symbol": sym, "resolution": "D", "from": start_ts, "to": end_ts, "token": key}
        try:
            r = requests.get(url, params=params, timeout=12)
            r.raise_for_status()
            j = r.json()
            if j.get("s") == "ok" and j.get("t") and j.get("c"):
                idx = pd.to_datetime(j["t"], unit="s", utc=True).tz_convert(None)
                df = pd.DataFrame({"Close": j["c"]}, index=idx)
                df = df[~df.index.duplicated(keep="last")].sort_index()
                if not df.empty:
                    return df
        except Exception:
            pass
    return pd.DataFrame()

def _fetch_finnhub(tickers: List[str], lookback_days: int, now_ts: int) -> Dict[str, pd.DataFrame]:
    key = os.getenv("FINNHUB_KEY")
    if not key:
        return {}
    start_ts = now_ts - int((lookback_days + 10) * 86400)
    out: Dict[str, pd.DataFrame] = {}
    for t in tickers:
        df = _fetch_finnhub_one(t, start_ts, now_ts, key)
        if not df.empty:
            out[t] = df
        _sleep_smol()
    return out

# ---------- Alpha Vantage ----------
def _fetch_av_one(ticker: str, key: str) -> pd.DataFrame:
    url = "https://www.alphavantage.co/query"
    params = {"function": "TIME_SERIES_DAILY_ADJUSTED", "symbol": ticker, "outputsize": "compact", "apikey": key}
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        j = r.json()
        data = j.get("Time Series (Daily)") or {}
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame({k: float(v.get("4. close")) for k, v in data.items()}, index=["Close"]).T
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        return pd.DataFrame({"Close": pd.to_numeric(df["Close"], errors="coerce").dropna()})
    except Exception:
        return pd.DataFrame()

def _fetch_alpha_vantage(tickers: List[str]) -> Dict[str, pd.DataFrame]:
    key = os.getenv("ALPHAVANTAGE_KEY")
    if not key:
        return {}
    out: Dict[str, pd.DataFrame] = {}
    for t in tickers:
        for sym in (t, t.split(".")[0]):
            df = _fetch_av_one(sym, key)
            if not df.empty:
                out[t] = df
                break
        _sleep_smol()
    return out

# ---------- public API ----------
def fetch_prices(tickers: List[str], lookback_days: int = 365) -> Dict[str, pd.DataFrame]:
    """
    Ophalen met fallback:
    1) yfinance
    2) Finnhub (als FINNHUB_KEY is gezet)
    3) Alpha Vantage (als ALPHAVANTAGE_KEY is gezet)
    """
    tickers = _sanitize(tickers)
    if not tickers:
        return {}
    start = (datetime.utcnow() - timedelta(days=max(lookback_days, 30))).strftime("%Y-%m-%d")
    now_ts = int(time.time())
    provider = (os.getenv("DATA_PROVIDER") or "auto").lower().strip()

    def run_auto() -> Dict[str, pd.DataFrame]:
        out = _fetch_yfinance(tickers, start)
        missing = [t for t in tickers if t not in out]
        if not missing:
            return out
        if os.getenv("FINNHUB_KEY"):
            out2 = _fetch_finnhub(missing, lookback_days, now_ts)
            out.update(out2)
            missing = [t for t in tickers if t not in out]
            if not missing:
                return out
        if os.getenv("ALPHAVANTAGE_KEY"):
            out3 = _fetch_alpha_vantage(missing)
            out.update(out3)
        return out

    if provider == "yfinance":
        return _fetch_yfinance(tickers, start)
    if provider == "finnhub":
        return _fetch_finnhub(tickers, lookback_days, now_ts)
    if provider in ("alpha_vantage", "alphavantage"):
        return _fetch_alpha_vantage(tickers)
    return run_auto()

def latest_close(tickers: List[str], lookback_days: int = 10) -> Dict[str, float]:
    px = fetch_prices(tickers, lookback_days=lookback_days)
    res: Dict[str, float] = {}
    for t, df in px.items():
        try:
            res[t] = float(pd.to_numeric(df["Close"], errors="coerce").dropna().iloc[-1])
        except Exception:
            pass
    return res
