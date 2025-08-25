from typing import Dict
import numpy as np
import pandas as pd

def trailing_stop(prices: pd.Series, trail_pct: float = 0.1) -> pd.Series:
    peak = prices.cummax()
    stop = peak * (1 - trail_pct)
    return stop

def value_at_risk(returns: pd.Series, alpha: float = 0.05) -> float:
    if len(returns) == 0:
        return float('nan')
    return float(np.quantile(returns.dropna(), alpha))
