from typing import Dict
import yaml
from pathlib import Path
import pandas as pd  # <- Zorg dat deze import aanwezig is!

from .data_sources import fetch_prices, latest_close
from .signals import generate_signals
from .forecasting import simple_forecast
from .portfolio import sector_report
from .scanner import screen_universe
from .utils import now_ams, resolve_config

def run_day(config_path: str = "config.yaml") -> Dict:
    cfg_file = resolve_config(config_path)
    cfg = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    tickers = cfg["portfolio"]["tickers"]
    lookback = cfg["data"]["lookback_days"]

    # 1. Prijzen ophalen
    prices = fetch_prices(tickers, lookback_days=lookback)
    last = latest_close(tickers)

    # 2. Signalen & Forecast
    sigs = generate_signals(prices, cfg["signals"])
    fc = simple_forecast(prices, horizon_days=5)

    # 3. Sector rapport veilig ophalen
    try:
        sector_df = sector_report(cfg.get("sectors", {}), last)
    except Exception:
        sector_df = pd.DataFrame(columns=["sector","covered","missing","avg_price","median_price","tickers"])

    # 4. Screener veilig ophalen
    try:
        opps = screen_universe(cfg.get("sectors", {}))
    except Exception:
        opps = {}

    # 5. Rapport samenstellen
    return {
        "timestamp": now_ams(),
        "last_prices": last,
        "signals": sigs,
        "forecast_5d": fc,
        "sector_report": sector_df.to_dict(orient="records"),
        "opportunities": opps,
        "risk": cfg["risk"],
    }
