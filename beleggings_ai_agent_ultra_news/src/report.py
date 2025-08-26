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

    opps = rep.get("opportunities", {}) or {}
    if opps:
        lines.append("\n## Kansen (screening)")
        for sec, rows in opps.items():
            items = ", ".join([f"{t} ({_fmt_num(score)})" for t, score in rows])
            lines.append(f"- **{sec}**: {items}")

    risk = rep.get("risk", {}) or {}
    if risk:
        lines.append("\n## Risico-instellingen")
        for k, v in risk.items():
            lines.append(f"- {k}: {v}")

    return "\n".join(lines)

def send_slack(markdown: str, webhook_url: str = None, timeout: int = 10):
    url = webhook_url or os.getenv("SLACK_WEBHOOK")
    if not url:
        return False, "Geen Slack webhook ingesteld."
    try:
        r = requests.post(url, json={"text": markdown}, timeout=timeout)
        r.raise_for_status()
        return True, "OK"
    except Exception as e:
        return False, str(e)

def send_email(markdown: str, subject: str = "Dagrapport", to_addr: str = None):
    host = os.getenv("SMTP_HOST"); port = int(os.getenv("SMTP_PORT","587"))
    user = os.getenv("SMTP_USER"); pwd = os.getenv("SMTP_PASS")
    to = to_addr or os.getenv("EMAIL_TO")
    if not all([host, port, user, pwd, to]):
        return False, "SMTP variabelen ontbreken (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_TO)"
    msg = MIMEText(markdown, "plain", "utf-8")
    msg["Subject"] = subject; msg["From"] = user; msg["To"] = to
    try:
        with smtplib.SMTP(host, port) as s:
            s.starttls(context=ssl.create_default_context())
            s.login(user, pwd)
            s.sendmail(user, [to], msg.as_string())
        return True, "OK"
    except Exception as e:
        return False, str(e)
