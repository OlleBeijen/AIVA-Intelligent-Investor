from typing import Dict, Any
import numpy as np
import pandas as pd
from .signals import indicators, signal_from_row

def _metrics(returns: pd.Series) -> Dict[str, float]:
    mean = returns.mean()
    vol = returns.std()
    sharpe = float(np.sqrt(252) * mean / vol) if vol and vol != 0 else float("nan")
    equity = (1 + returns).cumprod()
    rollmax = equity.cummax()
    dd = equity / rollmax - 1.0
    max_dd = float(dd.min()) if len(dd) else float("nan")
    years = len(returns) / 252 if len(returns) else float("nan")
    cagr = float(equity.iloc[-1] ** (1/years) - 1) if len(equity) and years and years > 0 else float("nan")
    hit_ratio = float((returns > 0).mean()) if len(returns) else float("nan")
    return {"cagr": cagr, "sharpe": sharpe, "max_drawdown": max_dd, "hit_ratio": hit_ratio}

def backtest_ticker(df: pd.DataFrame, params: Dict[str, Any], cost_bps: int = 5) -> Dict[str, Any]:
    ind = indicators(df, params["ma_short"], params["ma_long"], params["rsi_period"]).dropna()
    if ind.empty:
        return {"metrics": {}, "returns": pd.Series(dtype=float), "positions": pd.Series(dtype=float), "equity": pd.Series(dtype=float)}
    signals = ind.apply(lambda r: signal_from_row(r, params["rsi_buy"], params["rsi_sell"]), axis=1)
    pos = signals.replace({"BUY":1.0,"SELL":-1.0,"HOLD":0.0}).shift(1).fillna(0.0)
    ret = df["Close"].reindex(ind.index).pct_change().fillna(0.0)
    strat = pos * ret
    trades = pos.diff().abs().fillna(0.0)
    tc = trades * (cost_bps/10000.0)
    strat_net = strat - tc
    return {"metrics": _metrics(strat_net), "returns": strat_net, "positions": pos, "equity": (1+strat_net).cumprod()}

def backtest_portfolio(prices: Dict[str, pd.DataFrame], params: Dict[str, Any], weights: Dict[str, float] = None, cost_bps: int = 5) -> Dict[str, Any]:
    tickers = list(prices.keys())
    if not tickers:
        return {"metrics": {}, "equity": pd.Series(dtype=float), "returns": pd.Series(dtype=float)}
    if not weights:
        weights = {t: 1/len(tickers) for t in tickers}
    rets = []
    for t in tickers:
        res = backtest_ticker(prices[t], params, cost_bps)
        rets.append(res["returns"].rename(t))
    if not rets:
        return {"metrics": {}, "equity": pd.Series(dtype=float), "returns": pd.Series(dtype=float)}
    df = pd.concat(rets, axis=1).fillna(0.0)
    w = pd.Series(weights).reindex(df.columns).fillna(0.0)
    port_ret = (df * w).sum(axis=1)
    equity = (1 + port_ret).cumprod()
    mean, vol = port_ret.mean(), port_ret.std()
    sharpe = float(np.sqrt(252) * mean / vol) if vol and vol != 0 else float("nan")
    rollmax = equity.cummax()
    dd = equity / rollmax - 1.0
    max_dd = float(dd.min()) if len(dd) else float("nan")
    years = len(port_ret) / 252 if len(port_ret) else float("nan")
    cagr = float(equity.iloc[-1] ** (1/years) - 1) if len(equity) and years and years > 0 else float("nan")
    return {"metrics": {"cagr": cagr, "sharpe": sharpe, "max_drawdown": max_dd}, "equity": equity, "returns": port_ret}
