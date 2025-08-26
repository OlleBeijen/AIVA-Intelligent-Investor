from __future__ import annotations
from typing import List, Dict, Optional
import os, requests, datetime as dt

# Helpers
def _now_iso() -> str:
    return dt.datetime.utcnow().isoformat()+"Z"

def _norm_item(ticker: str, title: str, publisher: str, url: str, published: str) -> Dict:
    return {
        "ticker": ticker,
        "title": title.strip() if title else "",
        "publisher": publisher.strip() if publisher else "",
        "link": url,
        "publishedAt": published or _now_iso(),
    }

def _get_newsapi(ticker: str, limit: int) -> List[Dict]:
    key = os.getenv("NEWSAPI_KEY")
    if not key:
        return []
    q = ticker.replace(".AS","")
    url = f"https://newsapi.org/v2/everything?q={q}&language=en&pageSize={limit}&sortBy=publishedAt&apiKey={key}"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        if data.get("status") != "ok":
            return []
        out = []
        for art in data.get("articles", [])[:limit]:
            out.append(_norm_item(
                ticker=ticker,
                title=art.get("title",""),
                publisher=(art.get("source") or {}).get("name",""),
                url=art.get("url",""),
                published=art.get("publishedAt",""),
            ))
        return out
    except Exception:
        return []

def _get_finnhub(ticker: str, limit: int) -> List[Dict]:
    key = os.getenv("FINNHUB_KEY")
    if not key:
        return []
    # Laatste ~3 weken
    to = dt.date.today()
    frm = to - dt.timedelta(days=21)
    url = f"https://finnhub.io/api/v1/company-news?symbol={ticker}&from={frm}&to={to}&token={key}"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        out = []
        for it in (data or [])[:limit]:
            out.append(_norm_item(
                ticker=ticker,
                title=it.get("headline",""),
                publisher=it.get("source",""),
                url=it.get("url",""),
                published=dt.datetime.utcfromtimestamp(it.get("datetime",0)).isoformat()+"Z" if it.get("datetime") else "",
            ))
        return out
    except Exception:
        return []

def get_news(tickers: Optional[List[str]]=None, limit_per: int = 6, provider: str = "auto") -> List[Dict]:
    """Return a flat list of news dicts across tickers."""
    out: List[Dict] = []
    tickers = tickers or []
    for t in tickers:
        if provider == "newsapi":
            out.extend(_get_newsapi(t, limit_per))
        elif provider == "finnhub":
            out.extend(_get_finnhub(t, limit_per))
        else:
            data = _get_newsapi(t, limit_per)
            if not data:
                data = _get_finnhub(t, limit_per)
            out.extend(data)
    # de-dupe op (title, publisher)
    seen = set()
    uniq = []
    for it in out:
        key = (it.get("title","").strip(), it.get("publisher","").strip())
        if key in seen:
            continue
        seen.add(key)
        uniq.append(it)
    return uniq[: (limit_per * max(1, len(tickers)) )]
