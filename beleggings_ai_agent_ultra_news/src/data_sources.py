# src/data_sources.py
from __future__ import annotations
from typing import Dict, List, Tuple, Optional
import io, time, math
import pandas as pd
import requests
import yfinance as yf

# ---------- instellingen ----------
_YF_TIMEOUT = 20
_MAX_RETRIES = 3
_BACKOFF = 1.8

# Bekende ADR/alternatieven voor EU tickers die vaak haperen
# key = basis (zonder suffix), value = US/ADR symbool
_ADR_US_MAP = {
    "ASML": "ASML",   # ASML.AS -> ASML (Nasdaq)
    "PHIA": "PHG",    # Philips  -> PHG (NYSE)
    "ADYEN": "ADYEY", # Adyen    -> OTC ADR
    "URW": "UNBLF",   # Unibail-Rodamco-Westfield (fallback OTC)
    "NN":  "NNGPF",   # NN Group (fallback OTC)
}

def _sanitize(tickers: List[str]) -> List[str]:
    out, seen = [], set()
    for t in tickers or []:
        if not t: continue
        s = str(t).strip().upper()
        if s == "BRK.B": s = "BRK-B"  # yfinance conventie
        if s and s not in seen:
            seen.add(s); out.append(s)
    return out

def _split(items: List[str], n: int = 20) -> List[List[str]]:
    return [items[i:i+n] for i in range(0, len(items), n)]

# ---------- Yahoo (primair, gebatcht) ----------
def _yf_batch(batch: List[str], period: str, interval: str, auto_adjust: bool) -> Dict[str, pd.DataFrame]:
    data = yf.download(
        tickers=" ".join(batch),
        period=period,
        interval=interval,
        auto_adjust=auto_adjust,
        group_by="ticker",
        threads=True,
        progress=False,
        timeout=_YF_TIMEOUT,
    )
    out: Dict[str, pd.DataFrame] = {}
    if isinstance(data.columns, pd.MultiIndex):
        tick_lv0 = set(data.columns.get_level_values(0))
        for t in batch:
            if t in tick_lv0:
                df = data[t].copy().dropna(how="all")
                if not df.empty and "Close" in df.columns and df["Close"].dropna().shape[0] > 0:
                    out[t] = df
    else:
        if not data.empty and "Close" in data.columns:
            out[batch[0]] = data.dropna(how="all").copy()
    return out

# ---------- Stooq fallback (gratis CSV) ----------
def _stooq_symbol(t: str) -> str:
    base = t.split(".")[0]
    # Voor EU-probleemgevallen: gebruik US/ADR als best-effort
    if base in _ADR_US_MAP:
        return _ADR_US_MAP[base].lower()
    # US tickers werken direct
    return base.lower()

def _stooq_one(t: str, days: int) -> Optional[pd.DataFrame]:
    sym = _stooq_symbol(t)
    url = f"https://stooq.com/q/d/l/?s={sym}&i=d"
    try:
        r = requests.get(url, timeout=12)
        r.raise_for_status()
        if not r.text or not r.text.strip():
            return None
        df = pd.read_csv(io.StringIO(r.text))
        if "Date" in df.columns and "Close" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce", utc=True)
            df = df.set_index("Date").sort_index().dropna(how="any")
            if days and len(df) > days + 10:
                df = df.iloc[-(days+10):]
            return df[["Open","High","Low","Close","Volume"]].copy()
    except Exception:
        return None
    return None

# ---------- Finnhub fallback (jouw key) ----------
def _finnhub_candles(t: str, days: int) -> Optional[pd.DataFrame]:
    key = requests.os.getenv("FINNHUB_KEY")
    if not key:
        return None
    # Probeer originele symbool, daarna US/ADR alternatief
    tries = [t]
    base = t.split(".")[0]
    if base in _ADR_US_MAP and _ADR_US_MAP[base] not in tries:
        tries.append(_ADR_US_MAP[base])

    # periode in unix timestamps (ongeveer)
    secs = max(int(days or 60), 60) * 86400
    now = int(time.time())
    _from = now - secs
    _to = now

    for sym in tries:
        url = "https://finnhub.io/api/v1/stock/candle"
        params = {"symbol": sym, "resolution": "D", "from": _from, "to": _to, "token": key}
        try:
            r = requests.get(url, params=params, timeout=12)
            r.raise_for_status()
            data = r.json()
            if not data or data.get("s") != "ok":
                continue
            # bouw DataFrame
            df = pd.DataFrame({
                "Open": data.get("o", []),
                "High": data.get("h", []),
                "Low": data.get("l", []),
                "Close": data.get("c", []),
                "Volume": data.get("v", []),
            }, index=pd.to_datetime(data.get("t", []), unit="s", utc=True))
            df = df.sort_index().dropna(how="any")
            if not df.empty and df["Close"].dropna().shape[0] > 0:
                return df
        except Exception:
            continue
    return None

# ---------- Publieke API ----------
try:
    import streamlit as st
    _cache = st.cache_data
except Exception:
    def _cache(ttl: int = 900):
        def deco(fn): return fn
        return deco

@_cache(ttl=900)
def fetch_prices(
    tickers: List[str],
    lookback_days: int = 365,
    interval: str = "1d",
    auto_adjust: bool = True
) -> Dict[str, pd.DataFrame]:
    """
    Provider-keten: Yahoo -> Stooq -> Finnhub
    - Deelsucces is oké; missende symbols worden aangevuld via fallback.
    - Cache (15 min) om rate-limits te dempen.
    """
    syms = _sanitize(tickers)
    if not syms:
        return {}
    period = f"{max(int(lookback_days or 0), 60)}d"

    result: Dict[str, pd.DataFrame] = {}

    # 1) Yahoo batched
    for batch in _split(syms, 20):
        tries, todo = 0, list(batch)
        while todo and tries <= _MAX_RETRIES:
            try:
                chunk = _yf_batch(todo, period=period, interval=interval, auto_adjust=auto_adjust)
                for t, df in chunk.items():
                    result[t] = df
                todo = [t for t in todo if t not in result]
                if todo:
                    tries += 1
                    time.sleep((_BACKOFF ** tries) + 0.3)
            except Exception:
                tries += 1
                time.sleep((_BACKOFF ** tries) + 0.5)

    # 2) Stooq fallback (per symbool)
    still = [t for t in syms if t not in result]
    for t in still:
        df = _stooq_one(t, max(int(lookback_days or 0), 60))
        if df is not None:
            result[t] = df

    # 3) Finnhub fallback (alleen wat nog mist)
    still = [t for t in syms if t not in result]
    for t in still:
        df = _finnhub_candles(t, max(int(lookback_days or 0), 60))
        if df is not None:
            result[t] = df

    return result

def latest_close(tickers: List[str], lookback_days: int = 10) -> Dict[str, float]:
    px = fetch_prices(tickers, lookback_days=lookback_days)
    out: Dict[str, float] = {}
    for t, df in px.items():
        try:
            out[t] = float(df["Close"].dropna().iloc[-1])
        except Exception:
            pass
    return out
