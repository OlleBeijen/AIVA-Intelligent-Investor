# src/data_sources.py  (robuste fetch met batching, retry & caching)
from __future__ import annotations
from typing import Dict, List, Optional
import time, math, os
import pandas as pd
import yfinance as yf

# Optionele caching (geen extra lib nodig; yfinance heeft interne cache)
# Wil je extra hard-cache over requests, zet in requirements: requests-cache==1.2.0
# en voeg hieronder een sessie toe.

def _sanitize_tickers(tickers: List[str]) -> List[str]:
    out = []
    for t in tickers:
        if not t: 
            continue
        t = t.strip().upper()
        # yfinance gebruikt BRK-B (niet BRK.B) en GOOG(L) zonder punt
        t = t.replace("BRK.B", "BRK-B").replace("BRK.B", "BRK-B")
        out.append(t)
    # dedupe maar behoud volgorde
    seen = set(); keep = []
    for t in out:
        if t not in seen:
            seen.add(t); keep.append(t)
    return keep

def _split_batches(items: List[str], batch_size: int = 25) -> List[List[str]]:
    return [items[i:i+batch_size] for i in range(0, len(items), batch_size)]

def _download_batch(batch: List[str], period: str, interval: str, auto_adjust: bool, timeout: int) -> Dict[str, pd.DataFrame]:
    """
    Gebruik 1 multi-call naar Yahoo i.p.v. tientallen losse verzoeken.
    """
    data = yf.download(
        tickers=" ".join(batch),
        period=period,
        interval=interval,
        auto_adjust=auto_adjust,
        group_by="ticker",
        threads=True,
        progress=False,
        timeout=timeout
    )
    out: Dict[str, pd.DataFrame] = {}
    # Bij één ticker geeft yfinance geen kolomniveau 'ticker'
    if isinstance(data.columns, pd.MultiIndex):
        for t in batch:
            if t in data.columns.get_level_values(0):
                df = data[t].copy()
                if not df.empty and "Close" in df.columns:
                    df = df.dropna(how="all")
                    out[t] = df
    else:
        # single ticker
        if not data.empty and "Close" in data.columns:
            df = data.dropna(how="all").copy()
            out[batch[0]] = df
    return out

def fetch_prices(
    tickers: List[str],
    lookback_days: int = 365,
    interval: str = "1d",
    auto_adjust: bool = True,
    timeout: int = 20,
    max_retries: int = 4,
    backoff: float = 1.8
) -> Dict[str, pd.DataFrame]:
    """
    Robuuste prijsloader:
    - batcht tickers (25 per call)
    - retries met exponentiële backoff bij lege/timeout responses
    - normaliseert bekende notaties (BRK-B)
    - filtert lege frames (veroorzaakt YFTzMissingError) weg
    """
    if not tickers:
        return {}

    # yfinance period-string
    days = max(lookback_days, 60)
    period = f"{days}d"

    syms = _sanitize_tickers(tickers)
    result: Dict[str, pd.DataFrame] = {}
    batches = _split_batches(syms, batch_size=25)

    for batch in batches:
        tries = 0
        while tries <= max_retries:
            try:
                chunk = _download_batch(batch, period, interval, auto_adjust, timeout)
                # filter frames zonder datum/tz (leeg of alleen NaN)
                good = {}
                for t, df in chunk.items():
                    if df is None or df.empty:
                        continue
                    # soms komt tz/DateIndex mis terug: fix door te resetten en weer te zetten
                    if not isinstance(df.index, pd.DatetimeIndex):
                        df = df.reset_index()
                        if "Date" in df.columns:
                            df = df.rename(columns={"Date": "Datetime"}).set_index("Datetime")
                            df.index = pd.to_datetime(df.index, utc=True, errors="coerce")
                    if "Close" in df.columns and df["Close"].dropna().shape[0] > 0:
                        good[t] = df
                result.update(good)

                missing = [t for t in batch if t not in result]
                if not missing:
                    break  # batch klaar
                # kleine pauze en retry alleen voor missende symbols
                batch = missing
                tries += 1
                time.sleep((backoff ** tries) + 0.3)
            except Exception:
                tries += 1
                time.sleep((backoff ** tries) + 0.5)
        # als er nog steeds missende zijn: negeer (app blijft werken) 
        # je kunt hier eventueel loggen naar audit
    return result
