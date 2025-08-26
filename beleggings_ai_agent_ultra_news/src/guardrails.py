from __future__ import annotations
from typing import Tuple, Dict, Any
import re, json
from datetime import datetime
from pathlib import Path

FORBIDDEN = [
    r"\bkoop\b", r"\bverk(o|oo)p\b", r"\bmoet je kopen\b", r"\bgarantie\b",
    r"\bsnel rijk\b", r"\bzeker weten\b"
]

DISCLAIMER = (
    "⚠️ Dit is algemene, educatieve informatie en **geen persoonlijk beleggingsadvies**. "
    "Maak je eigen keuzes of raadpleeg een vergunninghoudend adviseur."
)

def no_advice(text: str) -> Tuple[str, bool]:
    lowered = text.lower()
    changed = any(re.search(pat, lowered) for pat in FORBIDDEN)
    if not changed:
        return text, False
    # Soft rewrite to scenario phrasing
    text = re.sub(r"(?i)koop", "overweeg-scenario", text)
    text = re.sub(r"(?i)verkoop", "overweeg-scenario", text)
    text = re.sub(r"(?i)moet je kopen", "zou je kunnen onderzoeken", text)
    text = re.sub(r"(?i)garantie", "geen garantie", text)
    text = re.sub(r"(?i)snel rijk", "risico op verlies blijft bestaan", text)
    if DISCLAIMER not in text:
        text = f"{DISCLAIMER}\n\n{text}"
    return text, True

def audit_log(event: str, payload: Dict[str, Any], path: Path = Path('data/audit.log')) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = {"ts": datetime.utcnow().isoformat() + "Z", "event": event, "payload": payload}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")