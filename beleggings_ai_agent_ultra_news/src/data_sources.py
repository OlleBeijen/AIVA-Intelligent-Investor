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
        timeout=timeou
