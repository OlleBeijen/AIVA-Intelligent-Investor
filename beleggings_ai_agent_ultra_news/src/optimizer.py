from typing import Dict
import numpy as np
import pandas as pd

def inverse_variance_weights(returns: pd.DataFrame) -> Dict[str, float]:
    vol = returns.std()
    inv = 1.0 / vol.replace(0, np.nan)
    w = inv / inv.sum()
    return {c: float(w[c]) for c in returns.columns}

def target_vol_weights(returns: pd.DataFrame, target_vol: float = 0.15) -> Dict[str, float]:
    w = pd.Series(inverse_variance_weights(returns))
    cov = returns.cov()
    port_vol = float(np.sqrt(np.dot(w.values, np.dot(cov.values, w.values))) * np.sqrt(252))
    if port_vol == 0 or np.isnan(port_vol):
        return {c: float(w[c]) for c in returns.columns}
    scale = target_vol / port_vol
    w2 = (w * scale)
    w2 = w2 / w2.sum()
    return {c: float(max(0.0, v)) for c, v in w2.items()}
