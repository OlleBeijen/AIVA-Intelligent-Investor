from typing import Dict
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression

def simple_forecast(prices: Dict[str, pd.DataFrame], horizon_days: int = 5) -> Dict[str, float]:
    out = {}
    for t, df in prices.items():
        close = df["Close"].dropna()
        if len(close) < 60: 
            continue
        ret = np.log(close).diff().dropna()
        X = np.arange(len(ret)).reshape(-1,1)
        model = LinearRegression().fit(X, ret.values)
        expected = model.predict([[len(ret)+i] for i in range(1, horizon_days+1)]).sum()
        out[t] = float(close.iloc[-1] * np.exp(expected))
    return out
