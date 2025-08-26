# src/data_sources.py
from __future__ import annotations
from typing import Dict, List, Tuple
import io, time
import pandas as pd
import requests
import yfinance as yf

# ========= Config =========
_YF_TIMEOUT = 20
_MAX_RETRIES = 4
_BACKOFF = 1.8

# Sommige EU-tickers hebben een US-ADR die beter beschikbaar is bij fallback
_ADR_US_MAP = {
    "ASML": "ASML",   # ASML.AS  -> ASML (Nasdaq)
    "PHIA": "PHG",    # Philips   -> PHG (NYSE)
    "ADYEN": "ADYEY", # Adyen     -> OTC ADR
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

def _split(items: List[str], n: int = 25) -> List[List[str]]:
    return [items[i:i+n] for i in range(0, len(items), n)]

# ========= Yahoo (primaire) =========
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

# ========= Stooq (fallback) =========
def _stooq_symbol(t: str) -> str:
    """
    Stooq symbolen:
      - US: AAPL -> aapl
      - US ADR van EU bedrijf: ASML -> asml.us
      - Veel EU tickers hebben .de/.pl/.jp etc., maar beperkte dekking.
    We richten ons op US/ADR fallback zodat AAPL/MSFT/NVDA/ASML werken.
    """
    base = t.split(".")[0]
    # Als het al US-achtig is (AAPL, MSFT, NVDA, ASML), gebruik plain of .us
    if "." not in t or t.endswith(".AS") or t.endswith(".PA") or t.endswith(".DE"):
        # Probeer US-ADR mapping voor bekende EU namen
        if base in _ADR_US_MAP:
            return _ADR_US_MAP[base].lower()  # bv ASML -> asml
        # Anders: plain (voor echte US tickers)
        return base.lower()
    return base.lower()

def _stooq_download_one(t: str, days: int) -> pd.DataFrame | None:
    """
    Stooq CSV endpoint: https://stooq.com/q/d/l/?s=aapl&i=d
    Geen api key nodig. Historie is meestal voldoende (dagdata).
    """
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
            # Knip lookback af (ongeveer)
            if days and len(df) > days + 10:
                df = df.iloc[-(days+10):]
            return df[["Open","High","Low","Close","Volume"]].copy()
    except Exception:
        return None
    return None

# ========= Publieke API =========
try:
    import streamlit as st
    _cache = st.cache_data
except Exception:
    # als Streamlit niet loaded is (unit tests), maak no-op decorator
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
    Robuuste prijsloader met provider-keten:
      1) Yahoo (yfinance, gebatcht)
      2) Stooq (publieke CSV) per symbool, incl. ADR-remap (ASML.AS -> ASML)
    - Deelsucces is oké: ontbrekende symbolen worden overgeslagen.
    - Caching (15 min) om rate-limits te beperken.
    """
    syms = _sanitize(tickers)
    if not syms:
        return {}

    period = f"{max(int(lookback_days or 0), 60)}d"
    result: Dict[str, pd.DataFrame] = {}

    # --- Eerst: Yahoo in batches met retries ---
    missing: List[str] = list(syms)
    for batch in _split(syms, 25):
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
        # wat na retries ontbreekt, blijft missing
        for t in batch:
            if t not in result:
                if t not in missing:
                    missing.append(t)

    # --- Dan: Stooq fallback per overgebleven symbool ---
    still_missing = [t for t in syms if t not in result]
    for t in still_missing:
        df = _stooq_download_one(t, max(int(lookback_days or 0), 60))
        if df is not None and not df.empty and "Close" in df.columns:
            result[t] = df

    return result

def latest_close(tickers: List[str], lookback_days: int = 10) -> Dict[str, float]:
    """
    Laatste geldige Close per ticker via fetch_prices-keten.
    """
    px = fetch_prices(tickers, lookback_days=lookback_days)
    out: Dict[str, float] = {}
    for t, df in px.items():
        try:
            out[t] = float(df["Close"].dropna().iloc[-1])
        except Exception:
            pass
    return out
