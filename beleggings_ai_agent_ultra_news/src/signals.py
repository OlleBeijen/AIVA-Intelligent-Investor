from __future__ import annotations
from typing import Dict, Any
import numpy as np
import pandas as pd

def _sma(s: pd.Series, n: int) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce")
    return s.rolling(n, min_periods=max(5, n//3)).mean()

def _ema(s: pd.Series, n: int) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce")
    return s.ewm(span=n, adjust=False).mean()

def _rsi(s: pd.Series, n: int = 14) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce")
    delta = s.diff()
    up = delta.clip(lower=0).rolling(n).mean()
    down = (-delta.clip(upper=0)).rolling(n).mean()
    rs = up / down.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def _bbands(s: pd.Series, n: int = 20, k: float = 2.0):
    m = _sma(s, n)
    std = pd.to_numeric(s, errors="coerce").rolling(n).std()
    upper = m + k * std
    lower = m - k * std
    return lower, upper

def _macd(s: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = _ema(s, fast)
    ema_slow = _ema(s, slow)
    macd = ema_fast - ema_slow
    sig = macd.ewm(span=signal, adjust=False).mean()
    return macd, sig

def indicators(df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = pd.DataFrame(index=df.index.copy())
    close = pd.to_numeric(df.get("Close"), errors="coerce")
    out["Close"] = close
    ma_s = int(params.get("ma_short", 20))
    ma_l = int(params.get("ma_long", 50))
    rsi_n = int(params.get("rsi_period", 14))
    out["SMA_S"] = _sma(close, ma_s)
    out["SMA_L"] = _sma(close, ma_l)
    out["SMA_200"] = _sma(close, 200)
    out["EMA_20"] = _ema(close, 20)
    out["RSI"] = _rsi(close, rsi_n)
    out["MACD"], out["MACD_SIG"] = _macd(close, 12, 26, 9)
    out["BB_L"], out["BB_H"] = _bbands(close, 20, 2.0)
    return out

def signal_from_row(row: pd.Series, rsi_buy: float = 35, rsi_sell: float = 65) -> str:
    try:
        rsi = float(row.get("RSI", np.nan))
        s = float(row.get("SMA_S", np.nan))
        l = float(row.get("SMA_L", np.nan))
        if np.isfinite(rsi) and np.isfinite(s) and np.isfinite(l):
            if rsi <= rsi_buy and s > l:
                return "BUY"
            if rsi >= rsi_sell and s < l:
                return "SELL"
    except Exception:
        pass
    return "HOLD"

def _regime_ok(ind: pd.DataFrame) -> bool:
    try:
        if len(ind) == 0: return True
        c = pd.to_numeric(ind["Close"], errors="coerce").dropna()
        s200 = pd.to_numeric(ind["SMA_200"], errors="coerce").dropna()
        if len(c) == 0 or len(s200) == 0:
            return True
        return bool(c.iloc[-1] > s200.iloc[-1])
    except Exception:
        return True

def _hysteresis_ok(ind: pd.DataFrame, days: int, kind: str) -> bool:
    if days <= 1 or len(ind) == 0:
        return True
    last = ind.tail(days)
    if kind == "BUY":
        return bool((last["SMA_S"] > last["SMA_L"]).all())
    if kind == "SELL":
        return bool((last["SMA_S"] < last["SMA_L"]).all())
    return True

def generate_signals(prices: Dict[str, pd.DataFrame], params: Dict[str, Any], opts: Dict[str, Any] | None = None) -> Dict[str, Dict]:
    opts = opts or {}
    res: Dict[str, Dict] = {}
    for t, df in (prices or {}).items():
        ind = indicators(df, params)
        if ind.empty or len(ind) < 3:
            continue
        row = ind.iloc[-1]
        base = signal_from_row(row, params.get("rsi_buy", 35), params.get("rsi_sell", 65))
        if base != "HOLD":
            if bool(opts.get("regime_filter", False)) and not _regime_ok(ind):
                base = "HOLD"
            if int(opts.get("hysteresis_days", 1)) > 1 and not _hysteresis_ok(ind, int(opts.get("hysteresis_days", 1)), base):
                base = "HOLD"
            if bool(opts.get("macd_confirm", False)):
                macd = float(row.get("MACD", np.nan)); sig = float(row.get("MACD_SIG", np.nan))
                if base == "BUY" and not (np.isfinite(macd) and np.isfinite(sig) and macd > sig):
                    base = "HOLD"
                if base == "SELL" and not (np.isfinite(macd) and np.isfinite(sig) and macd < sig):
                    base = "HOLD"
        res[t] = {
            "signal": base,
            "close": float(row.get("Close", np.nan)),
            "rsi": float(row.get("RSI", np.nan)),
            "sma_s": float(row.get("SMA_S", np.nan)),
            "sma_l": float(row.get("SMA_L", np.nan)),
            "sma_200": float(row.get("SMA_200", np.nan)),
            "macd": float(row.get("MACD", np.nan)),
            "macd_sig": float(row.get("MACD_SIG", np.nan)),
            "bb_l": float(row.get("BB_L", np.nan)),
            "bb_h": float(row.get("BB_H", np.nan)),
        }
    return res
