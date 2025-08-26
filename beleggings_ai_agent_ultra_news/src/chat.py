from __future__ import annotations
from typing import List, Dict, Any
import os, re
from .guardrails import no_advice
from .news import get_news

# Adapter for OpenAI (or Azure OpenAI) via openai package
def _chat_openai(system: str, messages: List[Dict[str,str]], model: str | None = None) -> str:
    try:
        from openai import OpenAI
    except Exception as e:
        return "AI is niet geactiveerd (openai package ontbreekt of geen API-sleutel)."

    # Azure OpenAI via env (optional)
    base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("AZURE_OPENAI_API_KEY")
    if not api_key:
        return "Geen API-sleutel gevonden. Zet OPENAI_API_KEY of AZURE_OPENAI_API_KEY in Secrets."
    client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
    model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    try:
        resp = client.chat.completions.create(model=model, messages=[{"role":"system","content":system}] + messages, temperature=0.3)
        return resp.choices[0].message.content
    except Exception as e:
        return f"AI-fout: {e}"

_TICKER_RE = re.compile(r"\b[A-Z]{1,5}(?:\.[A-Z]{1,3})?\b")

def extract_tickers(text: str) -> List[str]:
    found = _TICKER_RE.findall(text.upper())
    # Basic cleanup: ignore common words
    ignore = {"AND","THE","FOR","WITH","THIS","THAT"}
    return [t for t in found if t not in ignore]

def chat_answer(user_msg: str, provider: str = "auto") -> Dict[str, Any]:
    # Pull recent headlines for mentioned tickers (context)
    tickers = list(dict.fromkeys(extract_tickers(user_msg)))[:5]
    news_items = get_news(tickers, limit_per=3, provider=provider) if tickers else []
    # Build a short sources block for the model
    src_lines = []
    for it in news_items[:10]:
        title = it.get("title","")
        pub = it.get("publisher","")
        link = it.get("link","")
        t = it.get("ticker","")
        src_lines.append(f"- [{t}] {title} — {pub} ({link})")
    sources_block = "\n".join(src_lines) if src_lines else "Geen recente headlines gevonden."

    system = (
        "Je bent een educatieve beleggingscoach. Geef GEEN bindende koop/verkoop instructies. "
        "Praat in scenario's ('als ... dan ...'), bespreek risico's, tijdshorizon, spreiding. "
        "Gebruik de meegeleverde koppen alleen als context; trek geen causale conclusies. "
        "Antwoorden in het Nederlands, kort en duidelijk."
    )
    prompt = (
        f"Vraag van gebruiker:\n{user_msg}\n\n"
        f"Context (recente headlines):\n{sources_block}\n\n"
        "Lever: 1) korte samenvatting, 2) scenario's, 3) risico's, 4) wat te monitoren. "
        "Vermijd 'koop nu' of 'verkopen' formuleringen."
    )
    raw = _chat_openai(system, [{"role":"user","content": prompt}])
    safe, changed = no_advice(raw)
    return {"text": safe, "tickers": tickers, "sources": news_items, "guarded": changed}