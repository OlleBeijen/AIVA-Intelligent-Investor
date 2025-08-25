from typing import List, Dict
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

def _flatten_columns(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        try:
            df = df.xs(ticker, axis=1, level=1)
        except Exception:
            df.columns = df.columns.get_level_values(0)
    return df

def fetch_prices(tickers: List[str], lookback_days: int = 365) -> Dict[str, pd.DataFrame]:
    start = datetime.today() - timedelta(days=lookback_days*2)
    data: Dict[str, pd.DataFrame] = {}
    for t in tickers:
        try:
            df = yf.download(t, start=start.strftime("%Y-%m-%d"), progress=False, auto_adjust=True, group_by="column", threads=False)
            if df is None or df.empty:
                continue
            df = _flatten_columns(df, t).rename(columns=str.title)
            if "Close" not in df.columns and "Adj Close" in df.columns:
                df["Close"] = df["Adj Close"]
            if isinstance(df.get("Close"), pd.DataFrame):
                df["Close"] = df["Close"].iloc[:, 0]
            df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
            df = df.dropna(subset=["Close"])
            if not df.empty:
                data[t] = df
        except Exception as e:
            print(f"[WARN] Kon data niet ophalen voor {t}: {e}")
    return data

def latest_close(prices: Dict[str, pd.DataFrame]) -> Dict[str, float]:
    return {t: float(df["Close"].iloc[-1]) for t, df in prices.items() if not df.empty and "Close" in df.columns}
