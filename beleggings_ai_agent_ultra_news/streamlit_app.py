
import os, sys
from pathlib import Path

# ---- Robust sys.path so 'src' is found whether app runs at repo root or subdir ----
APP_DIR = Path(__file__).resolve().parent
candidates = [APP_DIR] + list(APP_DIR.parents[:3])
for base in candidates:
    if (base / "src").exists() and str(base) not in sys.path:
        sys.path.insert(0, str(base))

import streamlit as st
import pandas as pd
import yaml
import json

# ---- App modules ----
from src.ui import inject_css, hero
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
from src.guardrails import no_advice, audit_log
from src.plan import portfolio_weights_from_positions, aggregate_by_sector, nudge_vs_plan
from src.portfolio_import import parse_positions_csv
from src.policy import EDU_LABEL, DEF_DISCLAIMER
from src.forecast_explain import forecast_with_sources
from src.chat import chat_answer

# ---- Page config & styles ----
st.set_page_config(page_title="Beleggings AI Agent — Ultra++", layout="wide")
inject_css()
hero("Beleggings AI Agent — Ultra++", "Snellere inzichten • bronverwijzingen • AI‑chat (educatief)")
st.caption(EDU_LABEL)

# ---- Config handling ----
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
            "plan":{"target_allocations":{"Tech":1.0},"bands_pct":5},
            "risk_profile":{"horizon_years":10,"loss_tolerance_pct":20,"knowledge_level":"basis"},
            "kid_links":{},
        }
        p = save_config(default, "config.yaml")
        return default, p

cfg, cfg_path = ensure_config()

# ---- Sidebar ----
with st.sidebar:
    st.header("Instellingen")
    consent = st.checkbox("Lokaal opslaan (notities/trades/audit)", value=True)
    st.session_state["consent"] = consent
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

# ---- Tabs DEFINITION (single point) ----
tab_names = [
    "📊 Overview", "📈 Forecast + bronnen", "💬 AI Chat", "🗞️ News",
    "🔎 Screener", "🧪 Strategy Lab", "📦 Portfolio tools",
    "🎯 Doelen & Risico", "📥 Portefeuille import", "🔒 Compliance",
    "⚙️ Config Wizard", "📝 Journal", "❓ Help"
]
tabs = st.tabs(tab_names)

# ====================== TABS CONTENT ======================

# ------- Overview -------
with tabs[0]:
    st.subheader("Dagrapport")
    if st.button("Run nu"):
        rep = run_day(str(cfg_path))
        st.session_state["report"] = rep
        try:
            audit_log("run_day", {"tickers": list(rep.get("last_prices", {}).keys())})
        except Exception:
            pass
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

# ------- Forecast + bronnen -------
with tabs[1]:
    st.subheader("Korte-termijn forecast (5d) met context")
    provider = cfg.get("news", {}).get("provider","auto")
    tickers = cfg["portfolio"]["tickers"]
    prices = fetch_prices(tickers, lookback_days=cfg["data"]["lookback_days"])
    if prices:
        fc, srcs = forecast_with_sources(prices, horizon_days=5, news_per=3, provider=provider)
        if fc:
            rows = [{"ticker": t, "forecast": v} for t, v in fc.items()]
            st.dataframe(pd.DataFrame(rows).sort_values("ticker"), use_container_width=True)
            # Charts + bronnen
            for t in tickers:
                if t not in prices or t not in fc:
                    continue
                with st.expander(f"{t} — uitleg & bronnen"):
                    df = prices[t].copy().tail(200).reset_index()
                    df = df.rename(columns={"Date":"dt"})
                    # Try Plotly, else fallback
                    try:
                        import plotly.express as px
                        fig = px.line(df, x="dt", y="Close", title=f"{t} — prijs (laatste 200d)")
                        st.plotly_chart(fig, use_container_width=True)
                    except Exception:
                        st.line_chart(df.set_index("dt")["Close"])
                    st.write(f"**Model**: eenvoudige lineaire trend op log-returns → verwacht prijs over 5 dagen ≈ **{fc[t]:.2f}**.")
                    items = srcs.get(t, [])
                    if items:
                        st.write("**Recente headlines (context)**")
                        for it in items:
                            st.markdown(f"- {it.get('publisher','?')}: [{it.get('title','(zonder titel)')}]({it.get('link','#')})")
                    else:
                        st.caption("Geen headlines gevonden.")
        else:
            st.info("Geen forecast beschikbaar (te weinig data).")
    else:
        st.info("Kon geen prijzen ophalen.")

# ------- AI Chat -------
with tabs[2]:
    st.subheader("AI Chat (educatief)")
    st.caption("Scenario’s, risico’s en wat te monitoren. Geen bindende koop/verkopen. Headlines = context, geen bewijs.")
    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []
    for msg in st.session_state["chat_history"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
    q = st.chat_input("Stel je vraag over tickers, sectoren of risico's...")
    if q:
        st.session_state["chat_history"].append({"role":"user", "content": q})
        with st.chat_message("assistant"):
            with st.spinner("Denken..."):
                ans = chat_answer(q, provider=cfg.get("news",{}).get("provider","auto"))
                st.markdown(ans["text"])
                if ans["sources"]:
                    st.markdown("**Bronnen (laatste headlines):**")
                    for it in ans["sources"]:
                        st.markdown(f"- {it.get('publisher','?')}: [{it.get('title','(zonder titel)')}]({it.get('link','#')}) — _{it.get('ticker','')}_")
        st.session_state["chat_history"].append({"role":"assistant", "content": ans["text"]})

# ------- News -------
with tabs[3]:
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
                <div class='muted'>{it.get('publisher','?')} • {it.get('ticker','')} • {it.get('type','')}</div>
                <a href="{it.get('link','#')}" target="_blank">Open artikel</a>
                </div>""", unsafe_allow_html=True)
    st.caption("Optionele API keys: `NEWSAPI_KEY`, `FINNHUB_KEY` via Secrets. Zonder keys valt de app terug op Yahoo nieuws.")

# ------- Screener -------
with tabs[4]:
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
with tabs[5]:
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
            strat1 = backtest_ticker(df, {"ma_short": ma_s, "ma_long": ma_l, "rsi_period": rsi_p, "rsi_buy": rsi_buy, "rsi_sell": rsi_sell}, cost_bps=5)
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
with tabs[6]:
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

# ------- Doelen & Risico -------
with tabs[7]:
    st.subheader("Doelen & risicoprofiel (educatief)")
    rp = cfg.get("risk_profile", {})
    col = st.columns(3)
    with col[0]:
        rp["horizon_years"] = st.number_input("Horizon (jaren)", 1, 60, int(rp.get("horizon_years", 10)))
    with col[1]:
        rp["loss_tolerance_pct"] = st.number_input("Mentaal aanvaardbaar verlies (%)", 5, 80, int(rp.get("loss_tolerance_pct", 20)))
    with col[2]:
        rp["knowledge_level"] = st.selectbox("Kennisniveau", ["basis","gevorderd","expert"], index=["basis","gevorderd","expert"].index(rp.get("knowledge_level","basis")))
    if st.button("Opslaan (profiel)"):
        cfg["risk_profile"] = rp
        Path(cfg_path).write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")
        st.success("Profiel opgeslagen.")

    st.markdown("### Plan & bandbreedtes")
    plan = cfg.get("plan", {})
    bands_pp = st.number_input("Bandbreedte (pp)", 0, 20, int(plan.get("bands_pct", 5)))
    st.write("Doel-allocaties per sector (som ≈ 1.0):")
    plan_alloc = plan.get("target_allocations", {})
    edits = {}
    for sec in sorted(cfg.get("sectors", {}).keys()):
        edits[sec] = st.number_input(f"{sec}", 0.0, 1.0, float(plan_alloc.get(sec, 0.0)), 0.01)
    if st.button("Opslaan (plan)"):
        total = sum(edits.values())
        if total > 0:
            norm = {k: (v/total) for k,v in edits.items()}
            cfg["plan"] = {"target_allocations": norm, "bands_pct": bands_pp}
            Path(cfg_path).write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")
            st.success("Plan opgeslagen (genormaliseerd).")
        else:
            st.error("Som moet > 0.")

    st.markdown("---")
    st.markdown("### Coach-nudges (zonder advies)")
    rep = st.session_state.get("report")
    if rep and "last_prices" in rep and st.session_state.get("positions_df") is not None:
        weights = portfolio_weights_from_positions(st.session_state["positions_df"], rep["last_prices"])
        sec_w = aggregate_by_sector(weights, cfg.get("sectors", {}))
        plan_alloc = cfg.get("plan", {}).get("target_allocations", {})
        nudges = nudge_vs_plan(sec_w, plan_alloc, band_pp=cfg.get("plan", {}).get("bands_pct", 5))
        if nudges:
            for n in nudges:
                st.write("• ", n)
        else:
            st.info("Geen duidelijke afwijkingen t.o.v. plan.")
    else:
        st.info("Voer posities in bij **📥 Portefeuille import** en draai **Overview → Run nu**.")

# ------- Portefeuille import -------
with tabs[8]:
    st.subheader("Importeer posities (CSV)")
    st.caption("CSV met kolommen: ticker, qty, (optioneel) avg_price, currency")
    up = st.file_uploader("Kies CSV", type=["csv"])
    if up is not None:
        try:
            dfp = parse_positions_csv(up.read())
            st.dataframe(dfp, use_container_width=True)
            st.session_state["positions_df"] = dfp
            if st.session_state.get("consent", True):
                (Path("data") / "positions.csv").parent.mkdir(parents=True, exist_ok=True)
                dfp.to_csv("data/positions.csv", index=False)
                st.success("Posities opgeslagen (lokaal).")
        except Exception as e:
            st.error(f"Kon CSV niet lezen: {e}")

    if Path("data/positions.csv").exists() and "positions_df" not in st.session_state:
        import pandas as pd
        st.session_state["positions_df"] = pd.read_csv("data/positions.csv")

    if st.button("Bereken actuele gewichten") and st.session_state.get("report"):
        rep = st.session_state["report"]
        dfp = st.session_state.get("positions_df")
        if dfp is None:
            st.error("Geen posities.")
        else:
            w = portfolio_weights_from_positions(dfp, rep["last_prices"])
            st.json({k: round(float(v),4) for k,v in w.items()})

# ------- Compliance -------
with tabs[9]:
    st.subheader("Compliance & transparantie")
    st.write(DEF_DISCLAIMER)
    st.markdown("**KID/factsheet links (indien gezet in config):**")
    kid = cfg.get("kid_links", {})
    if kid:
        for t, url in kid.items():
            st.markdown(f"- [{t}]({url})")
    else:
        st.info("Geen KID-links ingesteld in config.yaml → 'kid_links'.")

    st.markdown("**Audit-log** (lokaal): `data/audit.log`")
    if Path("data/audit.log").exists():
        txt = Path("data/audit.log").read_text(encoding="utf-8").splitlines()[-200:]
        st.code("\n".join(txt), language="json")
    else:
        st.caption("Nog geen audit-items.")

# ------- Config Wizard -------
with tabs[10]:
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
with tabs[11]:
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
with tabs[12]:
    st.subheader("Mobiel gebruiken")
    st.markdown("""
**Je telefoon als client**
1. Deploy op Streamlit Community Cloud → kopieer de app‑link.
2. Open op je telefoon.
   - **iOS Safari**: *Share* → **Add to Home Screen** → 1‑tap toegang.
   - **Android Chrome**: ⋮ → **Add to Home screen**.
3. In de app: **Instellingen** of **Config Wizard** om tickers/sectoren te beheren.

**Nieuws providers**
- Standaard: Yahoo via yfinance (geen sleutel nodig).
- Optioneel: zet **Secrets** → `NEWSAPI_KEY` en/of `FINNHUB_KEY`.

**Dagrapporten**
- GitHub Actions workflow draait werkdags 06:00 UTC (~08:00 NL).

**Let op**
- Educatief; geen persoonlijk advies.
""")
