from __future__ import annotations
from typing import Dict, List, Any
import math
import pandas as pd
import numpy as np

from .signals import indicators, signal_from_row
try:
    from ta.volatility import AverageTrueRange
except Exception:
    AverageTrueRange = None

def _sma(s: pd.Series, n: int) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").rolling(n, min_periods=max(5, n//3)).mean()

def _atr(prices: pd.DataFrame, n: int = 14) -> float:
    if prices is None or prices.empty:
        return float("nan")
    if {"High","Low","Close"}.issubset(prices.columns):
        if AverageTrueRange:
            atr = AverageTrueRange(
                high=prices["High"], low=prices["Low"], close=prices["Close"], window=n
            ).average_true_range().dropna()
            return float(atr.iloc[-1]) if len(atr) else float("nan")
    c = pd.to_numeric(prices["Close"], errors="coerce").dropna()
    rets = c.pct_change().dropna()
    return float(c.iloc[-1] * rets.std()) if len(rets) else float("nan")

def _regime_ok(close: pd.Series) -> bool:
    sma200 = _sma(close, 200)
    return bool(len(close) and len(sma200) and close.iloc[-1] > sma200.iloc[-1])

def _hysteresis_ok(df: pd.DataFrame, days: int, kind: str) -> bool:
    if days <= 1: 
        return True
    cols = {"SMA_S","SMA_L"}
    if not cols.issubset(df.columns): 
        return True
    last = df.tail(days)
    if kind == "BUY":
        return bool((last["SMA_S"] > last["SMA_L"]).all())
    if kind == "SELL":
        return bool((last["SMA_S"] < last["SMA_L"]).all())
    return True

def system_actions(prices: Dict[str, pd.DataFrame], params: Dict[str, Any], system_cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    if not prices:
        return actions

    regime = bool(system_cfg.get("regime_filter", True))
    macd_ok = bool(system_cfg.get("macd_confirm", True))
    hyst = int(system_cfg.get("hysteresis_days", 2))
    sl = float(system_cfg.get("stop_loss_pct", 0.08))
    tp = float(system_cfg.get("take_profit_pct", 0.16))
    risk_pct = float(system_cfg.get("risk_per_trade_pct", 0.5)) / 100.0
    max_pos = int(system_cfg.get("max_positions", 8))
    use_atr = bool(system_cfg.get("use_atr", True))
    atr_n = int(system_cfg.get("atr_window", 14))
    capital = float(system_cfg.get("capital_eur", 25000))

    ind_map: Dict[str, pd.DataFrame] = {}
    for t, df in prices.items():
        ind_map[t] = indicators(df, params)

    scored = []
    for t, ind in ind_map.items():
        if ind.empty: 
            continue
        row = ind.iloc[-1]
        score = float(row.get("SMA_S", np.nan) - row.get("SMA_L", np.nan))
        scored.append((t, score))
    scored.sort(key=lambda x: (x[1] if math.isfinite(x[1]) else -1e9), reverse=True)
    tickers = [t for t, _ in scored]

    for t in tickers:
        ind = ind_map[t]
        if ind.empty: 
            continue
        row = ind.iloc[-1]
        close = float(row.get("Close", np.nan))
        if not math.isfinite(close):
            continue

        base = signal_from_row(row, params.get("rsi_buy", 35), params.get("rsi_sell", 65))

        if base == "BUY" and regime:
            if not _regime_ok(ind["Close"]):
                base = "HOLD"
        if base in ("BUY","SELL") and hyst > 1:
            if not _hysteresis_ok(ind, hyst, base):
                base = "HOLD"
        if base == "BUY" and macd_ok and ("MACD" in row and "MACD_SIG" in row):
            if not (row["MACD"] > row["MACD_SIG"]):
                base = "HOLD"
        if base == "SELL" and macd_ok and ("MACD" in row and "MACD_SIG" in row):
            if not (row["MACD"] < row["MACD_SIG"]):
                base = "HOLD"

        if base == "HOLD":
            continue

        # sizing
        # ATR-based risk unit; fallback 3% band
        atr_val = float("nan")
        if use_atr:
            try:
                from ta.volatility import AverageTrueRange as _ATR
                if {"High","Low","Close"}.issubset(ind.columns):
                    atr_val = _ATR(high=ind["High"], low=ind["Low"], close=ind["Close"], window=atr_n).average_true_range().dropna().iloc[-1]
            except Exception:
                atr_val = float("nan")
        if not math.isfinite(atr_val):
            risk_unit = close * 0.03
        else:
            risk_unit = float(atr_val)
        risk_per_share = max(1e-6, risk_unit)
        euro_risk = max(1.0, capital * risk_pct)
        size = int(max(0.0, euro_risk / risk_per_share))

        entry = close
        stop = entry * (1 - sl) if base == "BUY" else entry * (1 + sl)
        take = entry * (1 + tp) if base == "BUY" else entry * (1 - tp)

        actions.append({
            "ticker": t,
            "action": "LONG" if base == "BUY" else "FLAT",
            "entry": round(entry, 4),
            "size": int(size),
            "stop": round(stop, 4),
            "take_profit": round(take, 4),
            "rsi": float(row.get("RSI", float("nan"))),
            "note": f"{base} • regime={'on' if regime else 'off'}, macd={'on' if macd_ok else 'off'}, hyst={hyst}",
        })
        if len(actions) >= max_pos:
            break

    return actions
