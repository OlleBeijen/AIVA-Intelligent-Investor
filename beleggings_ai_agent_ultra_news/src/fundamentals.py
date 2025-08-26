from __future__ import annotations
from typing import Dict, List, Any
import os, requests
import pandas as pd
import yfinance as yf

def _yf_one(ticker: str) -> Dict[str, Any]:
    try:
        t = yf.Ticker(ticker)
        info = t.fast_info.__dict__ if hasattr(t, "fast_info") else {}
        finfo = {}
        try:
            inf = t.get_info()
            if isinstance(inf, dict):
                finfo.update(inf)
        except Exception:
            pass
        price = info.get("last_price") or finfo.get("currentPrice")
        out = {
            "price": float(price) if price else None,
            "marketCap": finfo.get("marketCap"),
            "trailingPE": finfo.get("trailingPE") or finfo.get("forwardPE"),
            "priceToBook": finfo.get("priceToBook"),
            "enterpriseToEbitda": finfo.get("enterpriseToEbitda"),
            "ebitda": finfo.get("ebitda"),
            "freeCashflow": finfo.get("freeCashflow"),
            "totalDebt": finfo.get("totalDebt"),
            "totalCash": finfo.get("totalCash"),
            "sharesOutstanding": finfo.get("sharesOutstanding"),
            "longName": finfo.get("longName") or finfo.get("shortName") or ticker,
            "exchange": finfo.get("exchange"),
            "currency": finfo.get("financialCurrency") or finfo.get("currency"),
            "link": finfo.get("website"),
        }
        return out
    except Exception:
        return {}

def _fmp_many(tickers: List[str]) -> Dict[str, Dict[str, Any]]:
    key = os.getenv("FMP_API_KEY")
    if not key:
        return {}
    base = "https://financialmodelingprep.com/api/v3/"
    res: Dict[str, Dict[str, Any]] = {}
    try:
        r = requests.get(base + "profile/" + ",".join(tickers), params={"apikey": key}, timeout=20)
        if r.ok:
            for it in r.json():
                t = it.get("symbol")
                res.setdefault(t, {}).update({
                    "price": it.get("price"), "marketCap": it.get("mktCap"),
                    "longName": it.get("companyName"), "currency": it.get("currency"),
                    "link": it.get("website")
                })
    except Exception:
        pass
    try:
        r = requests.get(base + "key-metrics/" + ",".join(tickers), params={"apikey": key, "period":"annual","limit":1}, timeout=20)
        if r.ok:
            for it in r.json():
                t = it.get("symbol")
                res.setdefault(t, {}).update({
                    "trailingPE": it.get("peRatio"),
                    "priceToBook": it.get("pbRatio"),
                    "enterpriseToEbitda": it.get("enterpriseValueOverEBITDA"),
                    "freeCashflow": it.get("freeCashFlowPerShare"),
                })
    except Exception:
        pass
    return res

def _finnhub_many(tickers: List[str]) -> Dict[str, Dict[str, Any]]:
    key = os.getenv("FINNHUB_KEY")
    if not key:
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for t in tickers:
        try:
            r = requests.get("https://finnhub.io/api/v1/stock/metric",
                             params={"symbol": t, "metric": "all", "token": key}, timeout=15)
            if r.ok:
                m = r.json().get("metric", {})
                out[t] = {
                    "trailingPE": m.get("peInclExtraTTM") or m.get("peExclExtraTTM"),
                    "priceToBook": m.get("pbAnnual") or m.get("pbQuarterly"),
                    "enterpriseToEbitda": m.get("enterpriseValueEBITDAAnnual"),
                    "freeCashflow": m.get("freeCashFlowPerShareTTM"),
                    "marketCap": m.get("marketCapitalization"),
                }
        except Exception:
            pass
    return out

def get_fundamentals(tickers: List[str]) -> Dict[str, Dict[str, Any]]:
    base = {t: _yf_one(t) for t in tickers}
    fmp = _fmp_many(tickers)
    for t, d in fmp.items():
        base.setdefault(t, {}).update({k:v for k,v in d.items() if v is not None})
    fin = _finnhub_many(tickers)
    for t, d in fin.items():
        base.setdefault(t, {}).update({k:v for k,v in d.items() if v is not None})
    return base