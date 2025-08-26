# src/data_sources.py
from __future__ import annotations
from typing import Dict, List
import time
import pandas as pd
import yfinance as yf

# ---------- helpers ----------

def _sanitize_tickers(tickers: List[str]) -> List[str]:
    out = []
    seen = set()
    for t in tickers or []:
        t = str(t).strip().upper()
        if not t:
            continue
        # yfinance notatie: BRK-B (geen punt)
        if t == "BRK.B":
            t = "BRK-B"
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out

def _split_batches(items: List[str], batch_size: int = 25) -> List[List[str]]:
    return [items[i:i + batch_size] for i in range(0, len(items), batch_size)]

def _download_batch(batch: List[str], period: str, interval: str, auto_adjust: bool, timeout: int) -> Dict[str, pd.DataFrame]:
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
    if isinstance(data.columns, pd.MultiIndex):
        for t in batch:
            if t in data.columns.get_level_values(0):
                df = data[t].copy().dropna(how="all")
                if not df.empty and "Close" in df.columns:
                    out[t] = df
    else:
        if not data.empty and "Close" in data.columns:
            out[batch[0]] = data.dropna(how="all").copy()
    return out

# ---------- public API ----------

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
    - retries met exponentiële backoff
    - filtert lege frames weg
    """
    syms = _sanitize_tickers(tickers)
    if not syms:
        return {}

    days = max(int(lookback_days or 0), 60)
    period = f"{days}d"

    result: Dict[str, pd.DataFrame] = {}
    for batch in _split_batches(syms, batch_size=25):
        tries = 0
        todo = list(batch)
        while todo and tries <= max_retries:
            try:
                chunk = _download_batch(todo, period, interval, auto_adjust, timeout)
                good = {}
                for t, df in chunk.items():
                    if df is None or df.empty:
                        continue
                    # zorg dat index datetime is
                    if not isinstance(df.index, pd.DatetimeIndex):
                        df = df.reset_index()
                        if "Date" in df.columns:
                            df = df.rename(columns={"Date": "Datetime"}).set_index("Datetime")
                        df.index = pd.to_datetime(df.index, utc=True, errors="coerce")
                    if "Close" in df.columns and df["Close"].dropna().shape[0] > 0:
                        good[t] = df
                result.update(good)
                # opnieuw proberen voor missende symbolen
                todo = [t for t in todo if t not in result]
                if todo:
                    tries += 1
                    time.sleep((backoff ** tries) + 0.3)
            except Exception:
                tries += 1
                time.sleep((backoff ** tries) + 0.5)
        # als er nog missende zijn, gaan we door; app blijft draaien
    return result

def latest_close(tickers: List[str], lookback_days: int = 10) -> Dict[str, float]:
    """
    Geeft laatste geldige Close per ticker.
    """
    px = fetch_prices(tickers, lookback_days=lookback_days)
    out: Dict[str, float] = {}
    for t, df in px.items():
        try:
            val = float(df["Close"].dropna().iloc[-1])
            out[t] = val
        except Exception:
            # geen geldige close
            pass
    return out
