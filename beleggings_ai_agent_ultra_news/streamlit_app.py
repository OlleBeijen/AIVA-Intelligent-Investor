import os, sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
if (APP_DIR / "src").exists() and str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
REPO_ROOT = APP_DIR.parent
if (REPO_ROOT / "src").exists() and str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import streamlit as st
import pandas as pd
import yaml
import json

from src.agent import run_day
from src.data_sources import fetch_prices
from src.signals import indicators
from src.backtest import backtest_ticker, backtest_portfolio
from src.optimizer import inverse_variance_weights, target_vol_weights
from src.risk import trailing_stop, value_at_risk
from src.report import make_report_md, send_slack, send_email
from src.news import get_news
from src.scanner import screen_universe
from src.utils import resolve_config, load_config, save_config

st.set_page_config(page_title="Beleggings AI Agent — Ultra", layout="wide")

# Mobile-friendly CSS
st.markdown("""
<style>
:root { --text: 1.06rem; }
.stApp { font-size: var(--text); }
button, .stButton>button { padding: 0.75rem 1rem; border-radius: 14px; }
div[data-testid="stSidebar"] { width: 300px; }
.card { padding: 0.8rem 1rem; border: 1px solid #eee; border-radius: 14px; margin-bottom: 0.5rem; }
.card h4 { margin: 0 0 0.25rem 0; }
.small { opacity: 0.75; font-size: 0.92rem; }
</style>
""", unsafe_allow_html=True)

st.title("Beleggings AI Agent — Ultra")

# ------- Config handling -------
def ensure_config():
    try:
        cfg = load_config("config.yaml")
        return cfg, resolve_config("config.yaml")
    except Exception:
        default = {
            "portfolio":{"tickers":["ASML.AS","AAPL","MSFT","NVDA"],"weights":None},
            "watchlist":["ASML.AS","AAPL","NVDA"],
            "sectors":{"Tech":["ASML.AS","AAPL","MSFT","NVDA"]},
            "risk":{"max_position_pct":0.2,"stop_loss_pct":0.1,"take_profit_pct":0.2,"target_portfolio_vol":0.15},
            "signals":{"ma_short":20,"ma_long":50,"rsi_period":14,"rsi_buy":35,"rsi_sell":65},
            "data":{"lookback_days":365},
            "reporting":{"currency":"EUR"},
            "news":{"provider":"auto","per_ticker":8},
        }
        p = save_config(default, "config.yaml")
        return default, p

cfg, cfg_path = ensure_config()

# ------- Sidebar: quick add tickers & sectors -------
with st.sidebar:
    st.header("Instellingen")
    st.caption(f"Config: {cfg_path}")
    st.write("### Watchlist")
    new_t = st.text_input("Ticker toevoegen", placeholder="ASML.AS, AAPL, ...")
    if st.button("➕ Voeg toe"):
        if new_t:
            cfg.setdefault("watchlist", [])
            if new_t not in cfg["watchlist"]:
                cfg["watchlist"].append(new_t.strip())
                save_config(cfg, cfg_path.name)
                st.success(f"{new_t} toegevoegd.")
            else:
                st.info("Ticker staat al in de watchlist.")
    rem_t = st.selectbox("Verwijder uit watchlist", ["—"] + cfg.get("watchlist", []))
    if st.button("🗑️ Verwijder") and rem_t != "—":
        cfg["watchlist"] = [t for t in cfg.get("watchlist", []) if t != rem_t]
        save_config(cfg, cfg_path.name)
        st.success(f"{rem_t} verwijderd.")

    st.write("### Sectors")
    sec_name = st.text_input("Nieuwe sector naam")
    sec_tickers = st.text_input("Tickers (komma-gescheiden)")
    if st.button("➕ Sector opslaan"):
        if sec_name and sec_tickers:
            cfg.setdefault("sectors", {})
            cfg["sectors"][sec_name] = [t.strip() for t in sec_tickers.split(",") if t.strip()]
            save_config(cfg, cfg_path.name)
            st.success(f"Sector '{sec_name}' opgeslagen.")

tabs = st.tabs(["📊 Overview", "🗞️ News", "🔎 Screener", "🧪 Strategy Lab", "📦 Portfolio tools", "🔔 Alerts & Report", "⚙️ Config Wizard", "📝 Journal", "❓ Help"])

# ------- Overview -------
with tabs[0]:
    st.subheader("Dagrapport")
    if st.button("Run nu"):
        rep = run_day(str(cfg_path))
        st.session_state["report"] = rep
    rep = st.session_state.get("report")
    if rep:
        c1, c2, c3 = st.columns(3)
        with c1: st.metric("Tickers", len(rep["last_prices"]))
        with c2: st.metric("Tijd", rep["timestamp"])
        with c3: st.json(rep["risk"])
        st.write("### Signalen")
        st.dataframe(pd.DataFrame(rep["signals"]).T, use_container_width=True)
        st.write("### 5-daagse forecast")
        st.dataframe(pd.DataFrame.from_dict(rep["forecast_5d"], orient="index", columns=["forecast_price"]).round(2), use_container_width=True)
    else:
        st.info("Klik **Run nu** om te starten.")

# ------- News -------
with tabs[1]:
    st.subheader("Nieuws per ticker")
    provider = st.selectbox("Provider", ["auto","yahoo","newsapi","finnhub"], index=["auto","yahoo","newsapi","finnhub"].index(cfg.get("news",{}).get("provider","auto")))
    per = st.slider("Aantal items per ticker", 1, 20, int(cfg.get("news",{}).get("per_ticker",8)))
    sel = st.multiselect("Kies tickers", cfg.get("watchlist", []) or cfg["portfolio"]["tickers"], default=(cfg.get("watchlist", [])[:3] or cfg["portfolio"]["tickers"][:3]))
    if st.button("Haal nieuws op") and sel:
        items = get_news(sel, limit_per=per, provider=provider)
        if not items:
            st.info("Geen nieuws gevonden (controleer je provider/API keys).")
        for it in items:
            with st.container():
                st.markdown(f"""<div class='card'>
                <h4>{it.get('title','(zonder titel)')}</h4>
                <div class='small'>{it.get('publisher','?')} • {it.get('ticker','')} • {it.get('type','')}</div>
                <a href="{it.get('link','#')}" target="_blank">Open artikel</a>
                </div>""", unsafe_allow_html=True)
    st.caption("Optionele API keys: `NEWSAPI_KEY`, `FINNHUB_KEY` via Streamlit Secrets. Zonder keys valt de app terug op Yahoo nieuws via yfinance.")

# ------- Screener -------
with tabs[2]:
    st.subheader("Screener per sector")
    if st.button("Run screener"):
        res = screen_universe(cfg.get("sectors", {}))
        rows = []
        for sec, items in res.items():
            for t, score in items:
                rows.append({"sector": sec, "ticker": t, "score": round(float(score),3)})
        if rows:
            st.dataframe(pd.DataFrame(rows).sort_values(["sector","score"], ascending=[True, False]), use_container_width=True)
        else:
            st.info("Geen resultaten.")

# ------- Strategy Lab -------
with tabs[3]:
    st.subheader("Vergelijk strategieën (ticker)")
    ticker = st.text_input("Ticker", value=(cfg.get("watchlist",[None])[0] or "ASML.AS"))
    ma_s = st.number_input("MA kort", 5, 200, int(cfg["signals"]["ma_short"]))
    ma_l = st.number_input("MA lang", 10, 400, int(cfg["signals"]["ma_long"]))
    rsi_p = st.number_input("RSI periode", 5, 30, int(cfg["signals"]["rsi_period"]))
    rsi_buy = st.number_input("RSI koop", 5, 60, int(cfg["signals"]["rsi_buy"]))
    rsi_sell = st.number_input("RSI verkoop", 40, 95, int(cfg["signals"]["rsi_sell"]))
    if st.button("Run strategie-comparisons"):
        prices = fetch_prices([ticker])
        if ticker in prices:
            df = prices[ticker]
            # Strategie 1: MA/RSI/MACD (bestaande backtest)
            from src.backtest import backtest_ticker
            strat1 = backtest_ticker(df, {"ma_short": ma_s, "ma_long": ma_l, "rsi_period": rsi_p, "rsi_buy": rsi_buy, "rsi_sell": rsi_sell}, cost_bps=5)
            # Strategie 2: Buy & Hold
            bh_ret = df["Close"].pct_change().fillna(0.0)
            import numpy as np
            def _metrics(returns):
                mean, vol = returns.mean(), returns.std()
                sharpe = float((np.sqrt(252) * mean / vol) if vol else float("nan"))
                eq = (1+returns).cumprod()
                dd = (eq/eq.cummax() - 1).min()
                years = len(returns)/252 if len(returns) else float("nan")
                cagr = float(eq.iloc[-1] ** (1/years) - 1) if len(eq) and years and years>0 else float("nan")
                return {"cagr": cagr, "sharpe": sharpe, "max_drawdown": float(dd)}
            strat2 = {"metrics": _metrics(bh_ret), "equity": (1+bh_ret).cumprod()}
            # Strategie 3: RSI-mean-reversion (koop <30, verkoop >70)
            pos = (indicators(df)["RSI"] < 30).astype(float).shift(1).fillna(0.0)
            r = df["Close"].pct_change().fillna(0.0)
            returns = pos * r
            strat3 = {"metrics": _metrics(returns), "equity": (1+returns).cumprod()}

            st.write("**Metrics**")
            st.json({
                "MA/RSI/MACD": {k: (round(v,4) if isinstance(v,float) else v) for k,v in strat1["metrics"].items()},
                "Buy&Hold": {k: (round(v,4) if isinstance(v,float) else v) for k,v in strat2["metrics"].items()},
                "RSI mean-reversion": {k: (round(v,4) if isinstance(v,float) else v) for k,v in strat3["metrics"].items()},
            })
            st.write("**Equity curves**")
            import pandas as pd
            eq = pd.DataFrame({
                "MA/RSI/MACD": strat1["equity"],
                "Buy&Hold": strat2["equity"],
                "RSI MR": strat3["equity"],
            }).dropna()
            st.line_chart(eq)
        else:
            st.error("Geen data voor deze ticker.")

# ------- Portfolio tools -------
with tabs[4]:
    st.subheader("Optimizers & Risk")
    tickers = cfg["portfolio"]["tickers"]
    prices = fetch_prices(tickers, lookback_days=cfg["data"]["lookback_days"])
    if prices:
        rets = pd.concat([df["Close"].pct_change().rename(t) for t, df in prices.items()], axis=1).dropna().tail(252)
        if not rets.empty:
            c1, c2 = st.columns(2)
            with c1:
                st.write("Inverse-variance gewichten")
                w_iv = inverse_variance_weights(rets)
                st.json({k: round(v,4) for k,v in w_iv.items()})
            with c2:
                target = st.slider("Doel-volatiliteit (jaarlijks)", 0.05, 0.3, cfg["risk"].get("target_portfolio_vol", 0.15), 0.01)
                w_tv = target_vol_weights(rets, target_vol=target)
                st.write("Target-vol gewichten")
                st.json({k: round(v,4) for k,v in w_tv.items()})
            st.write("Schatting VaR (95%) per ticker")
            var_rows = {c: value_at_risk(rets[c], 0.05) for c in rets.columns}
            st.json({k: round(v,4) for k,v in var_rows.items()})
        else:
            st.info("Niet genoeg data voor optimizer.")
    else:
        st.info("Kon geen prijzen ophalen.")

# ------- Alerts & Report -------
with tabs[5]:
    st.subheader("Alerts & Rapport")
    rep = st.session_state.get("report")
    if rep:
        from src.alerts import build_alerts
        alerts = build_alerts(rep["signals"])
        if alerts:
            for a in alerts:
                st.write("• ", a)
        else:
            st.info("Geen alerts.")
        md = make_report_md(rep)
        st.download_button("Download rapport (Markdown)", data=md, file_name="daily_report.md")
        if st.button("Verstuur rapport (Slack/E-mail)"):
            sent_any = False
            if os.getenv("SLACK_WEBHOOK_URL"):
                ok, msg = send_slack(md); st.write("Slack:", "OK" if ok else f"FOUT: {msg}"); sent_any = sent_any or ok
            if os.getenv("EMAIL_TO") and os.getenv("SMTP_HOST"):
                ok, msg = send_email("Dagrapport Beleggings Agent", md); st.write("E-mail:", "OK" if ok else f"FOUT: {msg}"); sent_any = sent_any or ok
            if not sent_any:
                st.warning("Zet env vars (SLACK_WEBHOOK_URL of SMTP_* + EMAIL_TO).")
    else:
        st.info("Eerst een rapport draaien op Overview.")

# ------- Config Wizard -------
with tabs[6]:
    st.subheader("Config Wizard")
    cfg_edit = st.text_area("Bewerk config.yaml", value=Path(cfg_path).read_text(encoding="utf-8"), height=340)
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("Opslaan"):
            Path(cfg_path).write_text(cfg_edit, encoding="utf-8")
            st.success("Config opgeslagen.")
    with c2:
        uploaded = st.file_uploader("Importeer watchlist (CSV: kolom 'ticker')", type=["csv"])
        if uploaded is not None:
            df = pd.read_csv(uploaded)
            ticks = [t for t in df.get("ticker", []) if isinstance(t,str)]
            cfg["watchlist"] = sorted(set(cfg.get("watchlist", []) + ticks))
            save_config(cfg, cfg_path.name)
            st.success(f"{len(ticks)} tickers toegevoegd aan watchlist.")
    with c3:
        st.download_button("Export config.yaml", data=Path(cfg_path).read_text(encoding="utf-8"), file_name="config.yaml")

# ------- Journal -------
with tabs[7]:
    st.subheader("Notities & Trades")
    notes_path = Path("data/notes.json")
    trades_path = Path("data/trades.csv")
    notes = {}
    if notes_path.exists():
        import json as _json
        notes = _json.loads(notes_path.read_text(encoding="utf-8"))
    t = st.selectbox("Ticker", sorted(set(cfg.get("watchlist", []) + cfg["portfolio"]["tickers"])))
    note = st.text_area("Notitie", value=notes.get(t, ""))
    if st.button("Bewaar notitie"):
        notes[t] = note
        notes_path.parent.mkdir(exist_ok=True, parents=True)
        import json as _json
        notes_path.write_text(_json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8")
        st.success("Notitie opgeslagen.")
    st.markdown("---")
    st.write("**Trade journal** (CSV)")
    import pandas as pd
    if trades_path.exists():
        st.dataframe(pd.read_csv(trades_path))
    col = st.columns(5)
    with col[0]:
        tj_t = st.text_input("Ticker", value=t)
    with col[1]:
        tj_d = st.date_input("Datum")
    with col[2]:
        tj_side = st.selectbox("Side", ["BUY","SELL"])
    with col[3]:
        tj_qty = st.number_input("Aantal", min_value=1, value=1)
    with col[4]:
        tj_px = st.number_input("Prijs", min_value=0.0, value=0.0)
    if st.button("➕ Voeg trade toe"):
        new = pd.DataFrame([{"date": str(tj_d), "ticker": tj_t, "side": tj_side, "qty": tj_qty, "price": tj_px}])
        if trades_path.exists():
            df = pd.read_csv(trades_path)
            df = pd.concat([df, new], ignore_index=True)
        else:
            df = new
        trades_path.parent.mkdir(exist_ok=True, parents=True)
        df.to_csv(trades_path, index=False)
        st.success("Trade toegevoegd.")
        st.dataframe(df)

# ------- Help -------
with tabs[8]:
    st.subheader("Mobiel gebruiken")
    st.markdown("""
**Je telefoon als client**
1. Deploy op Streamlit Community Cloud → kopieer de app‑link.
2. Open op je telefoon.
   - **iOS Safari**: *Share* → **Add to Home Screen** → krijg 1‑tap toegang.
   - **Android Chrome**: ⋮ → **Add to Home screen**.
3. In de app: Sidebar → **Instellingen** of **Config Wizard** om tickers, sectoren, watchlist te beheren.

**Nieuws providers**
- Standaard: Yahoo via yfinance (geen sleutel nodig).
- Optioneel: zet **Secrets** in Streamlit Cloud → `NEWSAPI_KEY` en/of `FINNHUB_KEY`.

**Dagrapporten**
- GitHub Actions workflow draait werkdags 06:00 UTC (~08:00 NL).

**Let op**
- Dit is educatief; geen financieel advies.
""")
