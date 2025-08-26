# src/chat.py (patched)
from __future__ import annotations
from typing import List, Dict, Any, Tuple
import os, re, json, requests

from .guardrails import no_advice
from .news import get_news

# ---- Simple ticker extractor ----
_TICKER_RE = re.compile(r"\b[A-Z]{1,5}(?:\.[A-Z]{1,3})?\b")
_IGNORE = {"AND","THE","FOR","WITH","THIS","THAT"}

def extract_tickers(text: str) -> List[str]:
    found = _TICKER_RE.findall(text.upper())
    return [t for t in found if t not in _IGNORE]

# ---- Providers ----
def _chat_openai(system: str, user: str) -> str:
    """
    OpenAI SDK v1.x
    Requires: openai>=1.0.0  (pip install openai)
    Env: OPENAI_API_KEY
    """
    try:
        from openai import OpenAI  # type: ignore
    except Exception as e:
        return f"OpenAI client niet geïnstalleerd: {e}"
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return "OPENAI_API_KEY ontbreekt."
    try:
        client = OpenAI(api_key=key)
        resp = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL","gpt-4o-mini"),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.2")),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "600")),
        )
        return resp.choices[0].message.content or ""
    except Exception as e:
        return f"AI-fout (OpenAI): {e}"

def _chat_groq(system: str, user: str) -> str:
    """
    Lightweight HTTP call; avoids extra deps.
    Env: GROQ_API_KEY
    """
    key = os.getenv("GROQ_API_KEY")
    if not key:
        return "GROQ_API_KEY ontbreekt."
    model = os.getenv("GROQ_MODEL","llama-3.1-70b-versatile")
    url = "https://api.groq.com/openai/v1/chat/completions"
    try:
        r = requests.post(url, headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }, json={
            "model": model,
            "messages": [
                {"role":"system","content":system},
                {"role":"user","content":user},
            ],
            "temperature": float(os.getenv("LLM_TEMPERATURE", "0.2")),
            "max_tokens": int(os.getenv("LLM_MAX_TOKENS", "600")),
        }, timeout=30)
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"AI-fout (Groq): {e}"

def _chat_gemini(system: str, user: str) -> str:
    """
    Simple HTTP call to Gemini (generative-language) to avoid adding google sdk.
    Env: GEMINI_API_KEY
    """
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        return "GEMINI_API_KEY ontbreekt."
    model = os.getenv("GEMINI_MODEL","gemini-1.5-pro")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    body = {
        "contents":[
            {"role":"user","parts":[{"text": f"SYSTEM:\n{system}"}]},
            {"role":"user","parts":[{"text": user}]}
        ]
    }
    try:
        r = requests.post(url, json=body, timeout=30)
        r.raise_for_status()
        data = r.json()
        candidates = data.get("candidates",[])
        if candidates and "content" in candidates[0]:
            parts = candidates[0]["content"].get("parts",[])
            text = "".join([p.get("text","") for p in parts])
            return text
        return json.dumps(data)[:1500]
    except Exception as e:
        return f"AI-fout (Gemini): {e}"

def _chat_hf(system: str, user: str) -> str:
    """
    Hugging Face Inference API (text-generation)
    Env: HF_API_KEY, HF_MODEL
    """
    key = os.getenv("HF_API_KEY")
    if not key:
        return "HF_API_KEY ontbreekt."
    model = os.getenv("HF_MODEL","HuggingFaceH4/zephyr-7b-beta")
    url = f"https://api-inference.huggingface.co/models/{model}"
    headers={"Authorization": f"Bearer {key}"}
    prompt = f"SYSTEM:\n{system}\n\nUSER:\n{user}\n\nASSISTANT:"
    try:
        r = requests.post(url, headers=headers, json={"inputs": prompt, "parameters": {"max_new_tokens": 600, "temperature": 0.2}}, timeout=60)
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
    news_items = get_news(tickers=tickers, limit_per=8, provider="auto")
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
