# src/chat.py
from __future__ import annotations
from typing import List, Dict, Any
import os, re, json, requests

from .guardrails import no_advice
from .news import get_news

# ---- Simple ticker extractor ----
_TICKER_RE = re.compile(r"\b[A-Z]{1,5}(?:\.[A-Z]{1,3})?\b")
_IGNORE = {"AND","THE","FOR","WITH","THIS","THAT"}

def extract_tickers(text: str) -> List[str]:
    found = _TICKER_RE.findall(text.upper())
    return [t for t in found if t not in _IGNORE]

# ---- LLM backends ----
def _chat_openai(system: str, user: str) -> str:
    try:
        from openai import OpenAI
    except Exception:
        return "AI niet beschikbaar: openai package ontbreekt."
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("AZURE_OPENAI_API_KEY")
    if not api_key:
        return "Geen API-sleutel gevonden. Zet OPENAI_API_KEY in Secrets."
    base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("AZURE_OPENAI_ENDPOINT")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    try:
        client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
        r = client.chat.completions.create(
            model=model,
            messages=[{"role":"system","content": system},{"role":"user","content": user}],
            temperature=0.3,
        )
        return r.choices[0].message.content
    except Exception as e:
        return f"AI-fout (OpenAI): {e}"

def _chat_groq(system: str, user: str) -> str:
    try:
        from groq import Groq
    except Exception:
        return "Groq niet geïnstalleerd. Zet LLM_PROVIDER=openai of installeer groq."
    key = os.getenv("GROQ_API_KEY")
    if not key:
        return "GROQ_API_KEY ontbreekt."
    model = os.getenv("GROQ_MODEL", "llama-3.1-70b-versatile")
    try:
        client = Groq(api_key=key)
        r = client.chat.completions.create(
            model=model,
            messages=[{"role":"system","content": system},{"role":"user","content": user}],
            temperature=0.3,
        )
        return r.choices[0].message.content
    except Exception as e:
        return f"AI-fout (Groq): {e}"

def _chat_gemini(system: str, user: str) -> str:
    try:
        import google.generativeai as genai
    except Exception:
        return "Gemini niet geïnstalleerd. Zet LLM_PROVIDER=openai of installeer google-generativeai."
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        return "GEMINI_API_KEY ontbreekt."
    model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    try:
        genai.configure(api_key=key)
        resp = genai.GenerativeModel(model).generate_content([{"role":"user","parts":[system+"\n\n"+user]}])
        return getattr(resp, "text", "") or "Leeg antwoord van Gemini."
    except Exception as e:
        return f"AI-fout (Gemini): {e}"

def _chat_hf(system: str, user: str) -> str:
    key = os.getenv("HF_API_KEY")
    if not key:
        return "HF_API_KEY ontbreekt."
    model = os.getenv("HF_MODEL", "mistralai/Mixtral-8x7B-Instruct-v0.1")
    try:
        r = requests.post(
            f"https://api-inference.huggingface.co/models/{model}",
            headers={"Authorization": f"Bearer {key}"},
            json={"inputs": f"{system}\n\n{user}", "parameters": {"max_new_tokens": 512, "temperature": 0.3}},
            timeout=60
        )
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list) and data and "generated_text" in data[0]:
            return data[0]["generated_text"]
        return json.dumps(data)[:2000]
    except Exception as e:
        return f"AI-fout (HF): {e}"

def chat_llm(system: str, user: str) -> str:
    prov = (os.getenv("LLM_PROVIDER") or "openai").lower().strip()
    if prov == "groq":   return _chat_groq(system, user)
    if prov == "gemini": return _chat_gemini(system, user)
    if prov == "hf":     return _chat_hf(system, user)
    return _chat_openai(system, user)

# ---- Public API ----
def chat_answer(user_msg: str, provider: str = "auto") -> Dict[str, Any]:
    tickers = list(dict.fromkeys(extract_tickers(user_msg)))[:5]
    news_items = get_news(tickers, limit_per=3, provider=provider) if tickers else []
    src_lines = []
    for it in news_items[:10]:
        title = it.get("title","")
        pub = it.get("publisher","")
        link = it.get("link","")
        t = it.get("ticker","")
        src_lines.append(f"- [{t}] {title} — {pub} ({link})")
    sources_block = "\n".join(src_lines) if src_lines else "Geen recente headlines gevonden."
    system = (
        "Je bent een educatieve beleggingscoach. Geen bindende koop/verkopen. "
        "Praat in scenario's; bespreek risico's, horizon en spreiding. "
        "Gebruik koppen alleen als context. Nederlands, kort en duidelijk."
    )
    prompt = (
        f"Vraag van gebruiker:\n{user_msg}\n\nContext (recente headlines):\n{sources_block}\n\n"
        "Lever: 1) korte samenvatting, 2) scenario's, 3) risico's, 4) wat te monitoren."
    )
    raw = chat_llm(system, prompt)
    safe, changed = no_advice(raw)
    return {"text": safe, "tickers": tickers, "sources": news_items, "guarded": changed}
