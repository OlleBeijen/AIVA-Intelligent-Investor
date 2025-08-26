from __future__ import annotations
from typing import Dict, Tuple
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_absolute_error

def _features(df: pd.DataFrame) -> pd.DataFrame:
    px = df["Close"].astype(float)
    r = px.pct_change()
    feats = pd.DataFrame({
        "r1": r.shift(1),
        "r5": px.pct_change(5).shift(1),
        "r20": px.pct_change(20).shift(1),
        "vol20": r.rolling(20).std().shift(1),
        "ma20_gap": (px/px.rolling(20).mean()-1).shift(1),
        "ma50_gap": (px/px.rolling(50).mean()-1).shift(1),
        "rsi14": _rsi(px, 14).shift(1),
    }, index=df.index)
    feats = feats.dropna()
    return feats

def _rsi(series: pd.Series, n=14) -> pd.Series:
    delta = series.diff()
    up = np.maximum(delta, 0.0)
    down = -np.minimum(delta, 0.0)
    roll_up = pd.Series(up).rolling(n).mean()
    roll_down = pd.Series(down).rolling(n).mean()
    rs = roll_up / (roll_down + 1e-12)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi.index = series.index
    return rsi

def forecast_ml(prices: Dict[str, pd.DataFrame], horizon: int = 5) -> Dict[str, Dict[str, float]]:
    out = {}
    for t, df in prices.items():
        if len(df) < 300 or "Close" not in df.columns:
            continue
        feats = _features(df)
        y = df["Close"].pct_change(horizon).shift(-horizon).reindex(feats.index)
        data = pd.concat([feats, y.rename("target")], axis=1).dropna()
        if len(data) < 200:
            continue
        X = data.drop(columns=["target"]).values
        y = data["target"].values
        tscv = TimeSeriesSplit(n_splits=5)
        best = None; best_mae = 1e9
        for depth in [2,3]:
            for lr in [0.05, 0.1]:
                mae = []
                for train_idx, test_idx in tscv.split(X):
                    model = GradientBoostingRegressor(max_depth=depth, learning_rate=lr, n_estimators=200)
                    model.fit(X[train_idx], y[train_idx])
                    pred = model.predict(X[test_idx])
                    mae.append(mean_absolute_error(y[test_idx], pred))
                m = float(np.mean(mae))
                if m < best_mae:
                    best_mae = m; best = (depth, lr)
        model = GradientBoostingRegressor(max_depth=best[0], learning_rate=best[1], n_estimators=300)
        model.fit(X, y)
        x_last = feats.iloc[[-1]].values
        pred_ret = float(model.predict(x_last)[0])
        out[t] = {"exp_return_%dd"%horizon: pred_ret, "mae_cv": best_mae}
    return out