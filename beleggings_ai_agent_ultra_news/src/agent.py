from typing import Dict
import yaml
import pandas as pd

from .data_sources import fetch_prices, latest_close
from .signals import generate_signals
from .forecasting import simple_forecast
from .portfolio import sector_report
from .scanner import screen_universe
from .utils import now_ams, resolve_config, load_config

def run_day(config_path: str = "config.yaml") -> Dict:
    """
    Draait 1 dag-cyclus:
    - laadt config
    - haalt prijzen op
    - bouwt signalen en forecast
    - sectorrapport + kansen
    - geeft alles terug als dict voor UI/rapportage
    """
    cfg_path = resolve_config(config_path)
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    tickers = (cfg.get("portfolio") or {}).get("tickers", []) or []
    params = cfg.get("signals", {}) or {}
    lookback_days = int((cfg.get("data") or {}).get("lookback_days", 365))
    sectors = cfg.get("sectors", {}) or {}

    prices = fetch_prices(tickers, lookback_days=lookback_days)
    last = latest_close(tickers, lookback_days=lookback_days)
    sigs = generate_signals(prices, params=params)
    fc = simple_forecast(prices, horizon_days=5)
    sector_df = sector_report(sectors, last)

    try:
        opps = screen_universe(sectors)
    except Exception:
        opps = {}

    return {
        "timestamp": now_ams(),
        "last_prices": last,
        "signals": sigs,
        "forecast_5d": fc,
        "sector_report": sector_df.to_dict(orient="records"),
        "opportunities": opps,
        "risk": cfg.get("risk", {}),
    }
