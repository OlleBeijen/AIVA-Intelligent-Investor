import os, sys
from pathlib import Path

# ---- Zorg dat 'src' importeerbaar is (werkt vanuit repo root of subdir) ----
APP_DIR = Path(__file__).resolve().parent
candidates = [APP_DIR] + list(APP_DIR.parents[:3])
for base in candidates:
    if (base / "src").exists() and str(base) not in sys.path:
        sys.path.insert(0, str(base))

import streamlit as st
import pandas as pd
import yaml

# ---- App modules ----
from src.utils import resolve_config, load_config, save_config, now_ams
from src.data_sources import fetch_prices, latest_close
from src.signals import generate_signals
from src.forecasting import simple_forecast
from src.portfolio import sector_report
from src.scanner import screen_universe
from src.news import get_news
from src.chat import chat_answer
from src.alerts import build_alerts
from src.report import make_report_md
from src.policy import EDU_LABEL, DEF_DISCLAIMER
from src.ui import inject_css, hero

st.set_page_config(page_title="AIVA • Intelligent Investor", layout="wide")

# ========= Helpers =========

@st.cache_data(ttl=3600, show_spinner=False)
def cached_prices(tickers, days, provider):
    # provider in cache-key opnemen
    os.environ["DATA_PROVIDER"] = provider
    return fetch_prices(tickers, lookback_days=days)

@st.cache_data(ttl=900, show_spinner=False)
def cached_latest_close(tickers, days, provider):
    os.environ["DATA_PROVIDER"] = provider
    return latest_close(tickers, lookback_days=days)

@st.cache_data(ttl=900, show_spinner=False)
def cached_news(tickers, per_ticker, provider):
    return get_news(tickers=tickers, limit_per=per_ticker, provider=provider)

def _env_present(name: str) -> bool:
    val = os.getenv(name)
    return bool(val and len(val.strip()) > 0)

def _badge(ok: bool) -> str:
    return "✅" if ok else "❌"

def _safe_df(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()
    return df

def _section(title: str):
    st.markdown(f"### {title}")

def _err(msg: str):
    st.error(msg, icon="⚠️")

def _info(msg: str):
    st.info(msg, icon="ℹ️")

# ========= UI Start =========
inject_css()
hero("AIVA Intelligent Investor", "Snelle dag-run, signalen, nieuws & uitleg (educatief)")

day_report = {}

with st.sidebar:
    st.subheader("Instellingen")
    default_cfg = "config.yaml"
    config_path = st.text_input("Config-bestand", value=default_cfg, help="Pad naar config.yaml")
    try:
        cfg_file = resolve_config(config_path)
        cfg = load_config(cfg_file)
        st.caption(f"Config: `{cfg_file}` geladen")
    except Exception as e:
        cfg = {}
        _err(f"Config niet gevonden of ongeldig: {e}")

    # Basis uit config
    portfolio = (cfg.get("portfolio") or {})
    tickers = portfolio.get("tickers") or []
    watchlist = cfg.get("watchlist") or []
    sectors = cfg.get("sectors") or {}
    sig_params = cfg.get("signals") or {}
    lookback_days = int((cfg.get("data") or {}).get("lookback_days", 365))
    currency = (cfg.get("reporting") or {}).get("currency", "EUR")
    news_cfg = cfg.get("news") or {}
    news_provider = news_cfg.get("provider", "auto")
    news_per_ticker = int(news_cfg.get("per_ticker", 6))

    # LLM provider
    provider = st.selectbox(
        "LLM provider",
        ["openai", "groq", "gemini", "hf"],
        index=["openai","groq","gemini","hf"].index(os.getenv("LLM_PROVIDER", "openai"))
    )
    os.environ["LLM_PROVIDER"] = provider

    # Data provider (koersdata)
    data_provider = st.selectbox(
        "Data provider",
        ["auto", "yfinance", "finnhub", "alpha_vantage"],
        index=["auto","yfinance","finnhub","alpha_vantage"].index(os.getenv("DATA_PROVIDER","auto")),
        help="‘auto’ probeert yfinance → finnhub → alpha_vantage."
    )
    os.environ["DATA_PROVIDER"] = data_provider

    # Lookback en nieuws
    lookback_days = st.slider("Lookback (dagen)", min_value=60, max_value=1095, value=lookback_days, step=15)
    news_provider = st.selectbox("Nieuwsbron", ["auto","newsapi","finnhub"], index=["auto","newsapi","finnhub"].index(news_provider))
    news_per_ticker = st.slider("Nieuws per ticker", 0, 12, news_per_ticker, 1)

    st.markdown("---")
    with st.expander("Diagnostiek"):
        st.write("**API keys**")
        st.write(f"OpenAI: {_badge(_env_present('OPENAI_API_KEY'))}")
        st.write(f"Groq:   {_badge(_env_present('GROQ_API_KEY'))}")
        st.write(f"Gemini: {_badge(_env_present('GEMINI_API_KEY'))}")
        st.write(f"HF:     {_badge(_env_present('HF_API_KEY'))}")
        st.write(f"NewsAPI:{_badge(_env_present('NEWSAPI_KEY'))}")
        st.write(f"Finnhub:{_badge(_env_present('FINNHUB_KEY'))}")
        st.write(f"AlphaVantage:{_badge(_env_present('ALPHAVANTAGE_KEY'))}")
        st.write(f"Data provider: `{os.getenv('DATA_PROVIDER','auto')}`")
        st.write(f"SMTP_HOST: {_badge(_env_present('SMTP_HOST'))} • EMAIL_TO: {_badge(_env_present('EMAIL_TO'))}")
        st.caption("Keys worden hier niet getoond; alleen aanwezig/afwezig.")

    st.markdown("---")
    if st.button("Config opslaan", use_container_width=True):
        try:
            save_config(cfg, config_path)
            st.success("Config opgeslagen.")
        except Exception as e:
            _err(f"Kon config niet opslaan: {e}")

st.markdown(f"> {DEF_DISCLAIMER}")

# ========= Data load =========
colA, colB, colC = st.columns([2,2,3])

with colA:
    _section("Dag-run")
    if not tickers:
        _info("Geen tickers in config.")
    else:
        try:
            prices = cached_prices(tickers, lookback_days, data_provider)
            last = cached_latest_close(tickers, 10, data_provider)
            signals = generate_signals(prices, params=sig_params)
            forecast = simple_forecast(prices, horizon_days=5)
            sector_df = sector_report(sectors, last)
            alerts = build_alerts(signals)
            day_report = {
                "timestamp": now_ams(),
                "last_prices": last,
                "signals": signals,
                "forecast_5d": forecast,
                "sector_report": sector_df.to_dict(orient="records"),
                "alerts": alerts,
                "risk": (cfg.get("risk") or {}),
            }
            if not prices:
                _err("Geen koersdata ontvangen. Probeer een andere Data provider en/of zet FINNHUB_KEY of ALPHAVANTAGE_KEY.")
            else:
                st.success("Dag-run klaar.")
        except Exception as e:
            day_report = {}
            _err(f"Dag-run fout: {e}")

with colB:
    _section("Signalen")
    if day_report.get("signals"):
        sig_rows = []
        for t, s in day_report["signals"].items():
            sig_rows.append({
                "Ticker": t,
                "Signaal": s.get("signal"),
                "Close": s.get("close"),
                "RSI": s.get("rsi"),
                "SMA_S": s.get("sma_s"),
                "SMA_L": s.get("sma_l"),
                "MACD": s.get("macd"),
            })
        df_sig = pd.DataFrame(sig_rows).sort_values(["Signaal","Ticker"])
        st.dataframe(df_sig, use_container_width=True, hide_index=True)
    else:
        st.caption("Nog geen signalen.")

    _section("Forecast (5 dagen)")
    if day_report.get("forecast_5d"):
        df_fc = pd.DataFrame({
            "Ticker": list(day_report["forecast_5d"].keys()),
            "Verwachting_Close_5d": list(day_report["forecast_5d"].values())
        })
        st.dataframe(df_fc.sort_values("Ticker"), use_container_width=True, hide_index=True)
    else:
        st.caption("Nog geen forecast.")

with colC:
    _section("Sector-overzicht")
    if day_report.get("sector_report"):
        df_sector = pd.DataFrame(day_report["sector_report"])
        st.dataframe(df_sector, use_container_width=True, hide_index=True)
    else:
        st.caption("Geen sectordata.")

# ========= Nieuws & Chat =========
st.markdown("---")
col1, col2 = st.columns([2,3])

with col1:
    _section("Nieuws")
    news_tickers = tickers[:5]
    items = []
    try:
        if news_per_ticker > 0 and news_tickers:
            items = cached_news(news_tickers, news_per_ticker, news_provider)
    except Exception as e:
        _err(f"Nieuws kon niet laden: {e}")

    if items:
        for it in items[:20]:
            t = it.get("ticker","")
            title = it.get("title","")
            src = it.get("publisher","")
            link = it.get("link","")
            st.markdown(f"- **[{t}]** [{title}]({link}) — {src}")
    else:
        st.caption("Geen headlines.")

with col2:
    _section("Chat (educatief)")
    user_msg = st.text_area("Vraag of onderwerp", placeholder="Voorbeeld: 'Wat speelt er rond ASML en NVDA?'", height=120)
    c1, c2, c3 = st.columns([1,1,2])
    with c1:
        temp = st.slider("Creativiteit", 0.0, 1.0, float(os.getenv("LLM_TEMPERATURE","0.2")), 0.05)
    with c2:
        max_toks = st.slider("Max tokens", 200, 1200, int(os.getenv("LLM_MAX_TOKENS","600")), 50)
    os.environ["LLM_TEMPERATURE"] = str(temp)
    os.environ["LLM_MAX_TOKENS"] = str(max_toks)

    if st.button("Vraag beantwoorden", type="primary"):
        if not user_msg.strip():
            _info("Typ eerst je vraag.")
        else:
            if provider == "openai" and not _env_present("OPENAI_API_KEY"):
                _err("OPENAI_API_KEY ontbreekt.")
            elif provider == "groq" and not _env_present("GROQ_API_KEY"):
                _err("GROQ_API_KEY ontbreekt.")
            elif provider == "gemini" and not _env_present("GEMINI_API_KEY"):
                _err("GEMINI_API_KEY ontbreekt.")
            elif provider == "hf" and not _env_present("HF_API_KEY"):
                _err("HF_API_KEY ontbreekt.")
            else:
                with st.spinner("Denken..."):
                    try:
                        ans = chat_answer(user_msg)
                        st.markdown(ans.get("text","(leeg)"))
                        if ans.get("sources"):
                            st.caption("Bronnen:")
                            for it in ans["sources"][:10]:
                                st.markdown(f"- [{it.get('ticker','')}] {it.get('title','')} — {it.get('publisher','')} ({it.get('link','')})")
                    except Exception as e:
                        _err(f"Chat fout: {e}")

# ========= Alerts =========
st.markdown("---")
_section("Alerts")
if day_report.get("alerts"):
    for a in day_report["alerts"]:
        st.write("• " + a)
else:
    st.caption("Geen alerts.")

# ========= Rapport (Markdown) =========
st.markdown("---")
_section("Rapport")
if day_report:
    md = make_report_md({
        "timestamp": day_report.get("timestamp", now_ams()),
        "signals": day_report.get("signals", {}),
        "forecast_5d": day_report.get("forecast_5d", {}),
        "sector_report": day_report.get("sector_report", []),
        "opportunities": day_report.get("opportunities", {}),
        "risk": day_report.get("risk", {}),
    })
    st.download_button("Download rapport (.md)", data=md, file_name=f"rapport_{now_ams().replace(' ','_').replace(':','')}.md", mime="text/markdown")
    with st.expander("Voorbeeld"):
        st.code(md, language="markdown")
else:
    st.caption("Geen rapportdata.")

st.markdown("---")
st.caption(EDU_LABEL)
