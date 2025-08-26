import os, smtplib, ssl, requests
from email.mime.text import MIMEText
import math

def _fmt_num(x, nd=2):
    try:
        if x is None:
            return "-"
        if isinstance(x, (int, float)):
            if math.isnan(x) or math.isinf(x):
                return "-"
            return f"{x:.{nd}f}"
        return str(x)
    except Exception:
        return "-"

def make_report_md(rep: dict) -> str:
    lines = []
    lines.append(f"# Dagrapport • {rep.get('timestamp','')}")
    sigs = rep.get("signals", {})
    if sigs:
        lines.append("\n## Signalen")
        lines.append("| Ticker | Advies | Close | RSI | SMA S | SMA L |")
        lines.append("|---|---|---:|---:|---:|---:|")
        for t, s in sigs.items():
            lines.append(
                f"| {t} | {s.get('signal','')} | "
                f"{_fmt_num(s.get('close'))} | {_fmt_num(s.get('rsi'),1)} | "
                f"{_fmt_num(s.get('sma_s'))} | {_fmt_num(s.get('sma_l'))} |"
            )
    fc = rep.get("forecast_5d", {})
    if fc:
        lines.append("\n## Forecast (5 dagen)")
        lines.append("| Ticker | Verwachte Close |")
        lines.append("|---|---:|")
        for t, v in fc.items():
            lines.append(f"| {t} | {_fmt_num(v)} |")

    sector = rep.get("sector_report", []) or []
    if sector:
        lines.append("\n## Sector-overzicht")
        lines.append("| Sector | Tickers | Gem. prijs | Median | Covered | Missing |")
        lines.append("|---|---|---:|---:|---:|---:|")
        for row in sector:
            lines.append(
                f"| {row.get('sector','')} | {row.get('tickers','')} | "
                f"{_fmt_num(row.get('avg_price'))} | {_fmt_num(row.get('median_price'))} | "
                f"{row.get('covered',0)} | {row.get('missing',0)} |"
            )
    return "\n".join(lines)
