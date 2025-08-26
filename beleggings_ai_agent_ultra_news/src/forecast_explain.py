from typing import Dict, List
import pandas as pd
from .forecasting import simple_forecast
from .news import get_news

def forecast_with_sources(prices: Dict[str, pd.DataFrame], horizon_days: int = 5, news_per: int = 3, provider: str = "auto"):
    fc = simple_forecast(prices, horizon_days=horizon_days)
    # Build sources per ticker
    sources = {}
    if fc:
        tickers = list(fc.keys())
        items = get_news(tickers, limit_per=news_per, provider=provider)
        # Group by ticker
        by_t = {}
        for it in items:
            by_t.setdefault(it.get("ticker","?"), []).append(it)
        for t in tickers:
            sources[t] = by_t.get(t, [])
    return fc, sources