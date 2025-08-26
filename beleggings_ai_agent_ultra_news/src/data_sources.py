# src/data_sources.py
from __future__ import annotations
from typing import Dict, List, Optional
import io, time, os
import pandas as pd
import requests

# ---------- instellingen ----------
_FINNHUB_TIMEOUT = 12
_STOOQ_TIMEOUT = 12

# Bekende ADR/alternatieven voor EU tickers
_ADR_US_MAP = {
    "ASML": "ASML",    # ASML.AS -> ASML (Nasdaq)
    "PHIA": "PHG",     # Philips -> PHG (NYSE)
    "URW":  "UNBLF",   # Unibail -> OTC
    "NN":   "NNGPF",   # NN Group -> OTC
    "ADYEN": "ADYEY",  # Adyen -> OTC
}

def _sanitize(tickers: List[str]) -> List[str]:
    out, seen = [], set()
    for t in tickers or []:
        if not t:
            continue
        s = str(t).strip().upper()
        if s == "BRK.B":  # conventieverschil
            s = "BRK-B"
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out

def _candidates(t: str) -> List[str]:
    """
    Maak een lijst met te proberen symbolen:
    1. Originele notatie (ASML.AS)
    2. Basis zonder suffix (ASML)
    3. US/ADR alternatief (bv PHIA->PHG)
    """
    cands = []
    base = t.split(".")[0]
    cands.append(t)
    if base not in cands:
        cands.append(base)
    adr = _ADR_US_MAP.get(base)
    if adr and adr not in cands:
        cands.append(adr)
    return cands

# ---------- Finnhub ----------
def _fh_candles_one(sym: str, days: int, token: str) -> Optional[pd.DataFrame]:
    now = int(time.time())
    secs = max(int(days or 60), 60) * 86400
    params = {
        "symbol": sym,
        "resolution": "D",
        "from": now - secs,
        "to": now,
        "token": token,
    }
    try:
        r = requests.get("https://finnhub.io/api/v1/stock/candle", params=params, timeout=_FINNHUB_TIMEOUT)
        r.raise_for_status()
        j = r.json()
        if not j or j.get("s") != "ok":
            return None
        idx = pd.to_datetime(j.get("t", []), unit="s", utc=True)
        df = pd.DataFrame({
            "Open": j.get("o", []),
            "High": j.get("h", []),
            "Low": j.get("l", []),
            "Close": j.get("c", []),
            "Volume": j.get("v", []),
        }, index=idx)
        df = df.sort_index().dropna(how="any")
        if df.empty or df["Close"].dropna().empty:
            return None
        return df
    except Exception:
        return None

# ---------- Stooq (gratis CSV) ----------
def _stooq_symbol(t: str) -> str:
    base = t.split(".")[0]
    return (_ADR_US_MAP.get(base) or base).lower()

def _stooq_one(t: str, days: int) -> Optional[pd.DataFrame]:
    url = f"https://stooq.com/q/d/l/?s={_stooq_symbol(t)}&i=d"
    try:
        r = requests.get(url, timeout=_STOOQ_TIMEOUT)
        r.raise_for_status()
        if not r.text.strip():
            return None
        df = pd.read_csv(io.StringIO(r.text))
        if "Date" not in df.columns or "Close" not in df.columns:
            return None
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce", utc=True)
        df = df.set_index("Date").sort_index().dropna(how="any")
        if df.empty:
            return None
        if days and len(df) > days + 10:
            df = df.iloc[-(days+10):]
        cols = [c for c in ["Open","High","Low","Close","Volume"] if c in df.columns]
        return df[cols].copy()
    except Exception:
        return None

# ---------- Publieke API ----------
def fetch_prices(
    tickers: List[str],
    lookback_days: int = 365,
    interval: str = "1d",              # genegeerd (D-resolutie only)
    auto_adjust: bool = True           # genegeerd hier
) -> Dict[str, pd.DataFrame]:
    """
    Prijsdata zonder Yahoo:
      1) Finnhub (met FINNHUB_KEY), probeert originele + alternatieve symbolen
      2) Stooq als fallback
    Retourneert dict[ticker] = DataFrame(Open, High, Low, Close, Volume)
    """
    syms = _sanitize(tickers)
    if not syms:
        return {}

    token = os.getenv("FINNHUB_KEY", "")
    out: Dict[str, pd.DataFrame] = {}

    # 1) Finnhub
    if token:
        for t in syms:
            for cand in _candidates(t):
                df = _fh_candles_one(cand, lookback_days, token)
                if df is not None:
                    out[t] = df
                    break

    # 2) Stooq fallback
    for t in syms:
        if t in out:
            continue
        df = _stooq_one(t, lookback_days)
        if df is not None:
            out[t] = df

    return out

def latest_close(tickers: List[str], lookback_days: int = 10) -> Dict[str, float]:
    px = fetch_prices(tickers, lookback_days=lookback_days)
    res: Dict[str, float] = {}
    for t, df in px.items():
        try:
            res[t] = float(df["Close"].dropna().iloc[-1])
        except Exception:
            pass
    return res
