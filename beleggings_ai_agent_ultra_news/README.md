# Beleggings AI Agent — ULTRA (incl. News, Config Wizard, Journal)

**Features**
- Multi-tab app (Overview, News, Screener, Strategy Lab, Portfolio tools, Alerts & Report, Config Wizard, Journal, Help)
- News via Yahoo / NewsAPI / Finnhub (auto fallback)
- In-app **Config Wizard** + watchlist/sector beheer
- Notes & Trade **Journal** (CSV)
- Strategievergelijking (MA/RSI/MACD vs Buy&Hold vs RSI MR)
- Optimizers (inverse variance, target-vol), Risk (VaR, trailing stop)
- Dagrapport + Slack/e-mail verzending + GitHub Actions

**Streamlit Cloud**
- Main file path: `streamlit_app.py` (of `submap/streamlit_app.py`)
- Secrets (optioneel): `SLACK_WEBHOOK_URL`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `EMAIL_TO`, `NEWSAPI_KEY`, `FINNHUB_KEY`

**Mobiel**
- Voeg als **Home screen** app op iOS/Android.
