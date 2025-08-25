from typing import List, Dict, Any
import os, time
import requests
import yfinance as yf

def _from_yahoo(ticker: str, limit: int = 10) -> List[Dict[str, Any]]:
    try:
        n = yf.Ticker(ticker).news or []
        out = []
        for item in n[:limit]:
            out.append({
                "title": item.get("title"),
                "link": item.get("link"),
                "publisher": item.get("publisher"),
                "published": item.get("providerPublishTime"),
                "type": "yahoo",
            })
        return out
    except Exception as e:
        return []

def _from_newsapi(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    key = os.getenv("NEWSAPI_KEY")
    if not key: return []
    url = "https://newsapi.org/v2/everything"
    params = {"q": query, "pageSize": min(limit, 100), "sortBy": "publishedAt", "language": "en", "apiKey": key}
    try:
        r = requests.get(url, params=params, timeout=10); r.raise_for_status()
        data = r.json().get("articles", [])
        out = []
        for a in data[:limit]:
            out.append({
                "title": a.get("title"),
                "link": a.get("url"),
                "publisher": a.get("source",{}).get("name"),
                "published": a.get("publishedAt"),
                "type": "newsapi",
            })
        return out
    except Exception:
        return []

def _from_finnhub(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    key = os.getenv("FINNHUB_KEY")
    if not key: return []
    # Finnhub company news requires symbol + date range; here use general news (if available)
    try:
        # fallback to company-news endpoint by symbol for last 7 days
        import datetime as dt
        to = dt.date.today()
        fr = to - dt.timedelta(days=7)
        url = f"https://finnhub.io/api/v1/company-news"
        params = {"symbol": query, "from": fr.isoformat(), "to": to.isoformat(), "token": key}
        r = requests.get(url, params=params, timeout=10); r.raise_for_status()
        data = r.json() or []
        out = []
        for a in data[:limit]:
            out.append({
                "title": a.get("headline"),
                "link": a.get("url"),
                "publisher": a.get("source"),
                "published": a.get("datetime"),
                "type": "finnhub",
            })
        return out
    except Exception:
        return []

def get_news(tickers: List[str], limit_per: int = 8, provider: str = "auto") -> List[Dict[str, Any]]:
    all_items: List[Dict[str, Any]] = []
    for t in tickers:
        items = []
        provs = []
        if provider == "auto":
            provs = ["yahoo", "newsapi", "finnhub"]
        elif provider in ("yahoo","newsapi","finnhub"):
            provs = [provider]
        for p in provs:
            if p == "yahoo":
                items = _from_yahoo(t, limit_per)
            elif p == "newsapi":
                items = _from_newsapi(t, limit_per)
            elif p == "finnhub":
                items = _from_finnhub(t, limit_per)
            if items:
                break
        for it in items:
            it["ticker"] = t
        all_items.extend(items)
    # sort by published (if int epoch), else leave as-is
    def _ts(x):
        v = x.get("published")
        if isinstance(v, (int,float)): return v
        try:
            import dateutil.parser as dp
            return dp.parse(v).timestamp()
        except Exception:
            return 0
    all_items.sort(key=_ts, reverse=True)
    return all_items[: limit_per * max(1, len(tickers))]
