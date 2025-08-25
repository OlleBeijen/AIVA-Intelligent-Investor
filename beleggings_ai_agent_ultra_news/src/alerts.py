from typing import Dict, List
import pandas as pd

def build_alerts(signals: Dict[str, Dict]) -> List[str]:
    out = []
    for t, s in signals.items():
        if s["signal"] == "BUY":
            out.append(f"{t}: BUY-signaal (RSI {s['rsi']:.1f}, SMA {s['sma_s']:.0f}>{s['sma_l']:.0f})")
        if s["signal"] == "SELL":
            out.append(f"{t}: SELL-signaal (RSI {s['rsi']:.1f})")
        if s["close"] <= s["bb_l"]:
            out.append(f"{t}: onder Bollinger-band (mogelijk oversold)")
        if s["close"] >= s["bb_h"]:
            out.append(f"{t}: boven Bollinger-band (mogelijk overbought)")
    return out
