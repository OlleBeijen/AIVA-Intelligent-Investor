import os, smtplib, ssl, requests
from email.mime.text import MIMEText

def make_report_md(rep: dict) -> str:
    lines = []
    lines.append(f"# Dagrapport • {rep.get('timestamp','')}")
    sigs = rep.get("signals", {})
    if sigs:
        lines.append("\n## Signalen")
        lines.append("| Ticker | Advies | Close | RSI | SMA S | SMA L |")
        lines.append("|---|---|---:|---:|---:|---:|")
        for t, s in sigs.items():
            lines.append(f"| {t} | {s['signal']} | {s['close']:.2f} | {s['rsi']:.1f} | {s['sma_s']:.2f} | {s['sma_l']:.2f} |")
    fc = rep.get("forecast_5d", {})
    if fc:
        lines.append("\n## 5-daagse forecast (price)")
        lines.append("| Ticker | Verwacht |")
        lines.append("|---|---:|")
        for t, v in fc.items():
            lines.append(f"| {t} | {v:.2f} |")
    opps = rep.get("opportunities", {})
    if opps:
        lines.append("\n## Kansen per sector (screener)")
        for sec, items in opps.items():
            pretty = ", ".join([f"{t} ({score:.2f})" for t, score in items])
            lines.append(f"- **{sec}**: {pretty if pretty else '—'}")
    sector = rep.get("sector_report", [])
    if sector:
        lines.append("\n## Sector-rapport")
        lines.append("| Sector | Tickers | Gem. prijs | Aantal |")
        lines.append("|---|---|---:|---:|")
        for row in sector:
            lines.append(f"| {row['sector']} | {row['tickers']} | {row['avg_price']:.2f} | {row['count']} |")
    return "\n".join(lines)

def send_slack(markdown: str, webhook_url: str = None, timeout: int = 10):
    url = webhook_url or os.getenv("SLACK_WEBHOOK_URL")
    if not url:
        return False, "SLACK_WEBHOOK_URL ontbreekt"
    try:
        res = requests.post(url, json={"text": markdown}, timeout=timeout)
        ok = 200 <= res.status_code < 300
        return ok, res.text if not ok else "OK"
    except Exception as e:
        return False, str(e)

def send_email(subject: str, markdown: str, to_addr: str = None):
    host = os.getenv("SMTP_HOST"); port = int(os.getenv("SMTP_PORT", "587"))
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
