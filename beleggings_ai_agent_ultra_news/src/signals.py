from typing import Dict
import pandas as pd
from ta.trend import SMAIndicator, EMAIndicator, MACD
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands

def _to_series(close_like) -> pd.Series:
    if isinstance(close_like, pd.Series):
        s = close_like
    elif isinstance(close_like, pd.DataFrame):
        s = close_like.iloc[:, 0] if close_like.shape[1] >= 1 else pd.Series(dtype='float64')
    else:
        s = pd.Series(close_like).squeeze()
    s = pd.to_numeric(s, errors='coerce')
    s.name = 'Close'
    return s

def indicators(df: pd.DataFrame, ma_short=20, ma_long=50, rsi_period=14) -> pd.DataFrame:
    out = df.copy()
    close = _to_series(out.get("Close"))
    out["Close"] = close
    out["SMA_S"] = SMAIndicator(close=close, window=ma_short).sma_indicator()
    out["SMA_L"] = SMAIndicator(close=close, window=ma_long).sma_indicator()
    out["EMA_20"] = EMAIndicator(close=close, window=20).ema_indicator()
    out["RSI"] = RSIIndicator(close=close, window=rsi_period).rsi()
    macd = MACD(close=close)
    out["MACD"] = macd.macd(); out["MACD_SIG"] = macd.macd_signal()
    bb = BollingerBands(close=close, window=20, window_dev=2)
    out["BB_H"] = bb.bollinger_hband(); out["BB_L"] = bb.bollinger_lband()
    return out.dropna()

def signal_from_row(row, rsi_buy=35, rsi_sell=65):
    sig = "HOLD"
    if row["SMA_S"] > row["SMA_L"] and row["MACD"] > row["MACD_SIG"] and row["RSI"] < rsi_sell:
        sig = "BUY"
    if (row["SMA_S"] < row["SMA_L"] and row["MACD"] < row["MACD_SIG"]) or row["RSI"] > rsi_sell:
        sig = "SELL"
    return sig

def generate_signals(prices: Dict[str, pd.DataFrame], params: Dict) -> Dict[str, Dict]:
    out = {}
    for t, df in prices.items():
        ind = indicators(df, params["ma_short"], params["ma_long"], params["rsi_period"])
        if ind.empty: continue
        last = ind.iloc[-1]
        sig = signal_from_row(last, params["rsi_buy"], params["rsi_sell"])
        out[t] = {
            "signal": sig,
            "close": float(last["Close"]),
            "sma_s": float(last["SMA_S"]),
            "sma_l": float(last["SMA_L"]),
            "ema_20": float(last["EMA_20"]),
            "rsi": float(last["RSI"]),
            "macd": float(last["MACD"]),
            "macd_sig": float(last["MACD_SIG"]),
            "bb_l": float(last["BB_L"]),
            "bb_h": float(last["BB_H"]),
        }
    return out
