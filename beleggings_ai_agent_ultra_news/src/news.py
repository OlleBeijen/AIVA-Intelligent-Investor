from __future__ import annotations
from typing import List, Dict
import os, requests

# Prioriteit: NewsAPI → Finnhub

def _get_newsapi(ticker: str, limit: int) -> List[Dict]:
    key = os.getenv("NEWSAPI_KEY")
    if not key:
        return []
    url = f"https://newsapi.org/v2/everything?q={ticker}&language=en&pageSize={limit}&apiKey={key}"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        if data.get("status") != "ok":
            return []
        articles = []
        for a in data.get("articles", []):
            articles.append({
                "ticker": ticker,
                "title": a.get("title") or "",
                "publisher": a.get("source", {}).get("name") or "Unknown",
                "link": a.get("url") or "",
                "published": a.get("publishedAt") or ""
            })
        return articles
    except Exception:
        return []

def _get_finnhub(ticker: str, limit: int) -> List[Dict]:
    key = os.getenv("FINNHUB_KEY")
    if not key:
        return []
    url = f"https://finnhub.io/api/v1/company-news?symbol={ticker}&from=2023-01-01&to=2030-01-01&token={key}"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        articles = []
        for a in data[:limit]:
            articles.append({
                "ticker": ticker,
                "title": a.get("headline") or "",
                "publisher": a.get("source") or "Unknown",
                "link": a.get("url") or "",
                "published": a.get("datetime") or ""
            })
        return articles
    except Exception:
        return []

def get_news(tickers: List[str], limit_per: int = 5, provider: str = "auto") -> List[Dict]:
    """
    Haalt headlines op. Alleen NewsAPI en Finnhub toegestaan.
    - Als provider="auto" → probeert eerst NewsAPI, dan Finnhub.
    - Als provider="newsapi" → forceer alleen NewsAPI.
    - Als provider="finnhub" → forceer alleen Finnhub.
    """
    out: List[Dict] = []
    tickers = tickers or []

    for t in tickers:
        if provider == "newsapi":
            out.extend(_get_newsapi(t, limit_per))
        elif provider == "finnhub":
            out.extend(_get_finnhub(t, limit_per))
        else:
            # auto: eerst NewsAPI, dan fallback Finnhub
            data = _get_newsapi(t, limit_per)
            if not data:
                data = _get_finnhub(t, limit_per)
            out.extend(data)
    return out
