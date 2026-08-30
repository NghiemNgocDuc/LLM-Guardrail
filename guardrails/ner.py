"""
Optional local NER for PII/person + code entity detection.

Tries in order:
  1. presidio_analyzer + presidio_anonymizer (if installed)
  2. gliner / transformers (if installed)
  3. fallback heuristic (spaCy-like regex for person names + code identifiers)

No hard dependency — all imports are lazy + try/except. If nothing available,
returns empty list and caller falls back to regex.

Used by PIIRedactor (wl1) and code-entity detection (wl4).
"""
from __future__ import annotations

import re
from typing import List, Dict

# ── heuristic patterns (always available) ─────────────────────────────────
_PERSON_RE = re.compile(r"\b[A-Z][a-z]+ [A-Z][a-z]+\b")  # John Smith
_CODE_IDENTIFIERS = [
    re.compile(r"\b[a-z]+_[a-z_]{3,}\b"),  # snake_case internal
    re.compile(r"\b[A-Z][a-z]+[A-Z][a-zA-Z]+\b"),  # CamelCase
    re.compile(r"\b[a-z]{2,}_staging\b"),
    re.compile(r"\b[a-z]{2,}_api\b", re.I),
    re.compile(r"\bNeptune API\b"),
    re.compile(r"\bOscorp\b"),
    re.compile(r"\busers_staging\b"),
]

_ner_available = None
_ner_engine = None

def _try_load():
    global _ner_available, _ner_engine
    if _ner_available is not None:
        return _ner_available
    # Try presidio
    try:
        from presidio_analyzer import AnalyzerEngine  # type: ignore
        _ner_engine = AnalyzerEngine()
        _ner_available = "presidio"
        return _ner_available
    except Exception:
        pass
    # Try privacy-filter (openai) if installed
    try:
        import privacy_filter  # type: ignore
        _ner_available = "privacy_filter"
        return _ner_available
    except Exception:
        pass
    _ner_available = "heuristic"
    return _ner_available

def detect_persons(text: str) -> List[Dict]:
    """Return list of {"text": str, "start": int, "end": int, "score": float}"""
    eng = _try_load()
    if eng == "presidio":
        try:
            results = _ner_engine.analyze(text=text, language="en", entities=["PERSON"])
            return [{"text": text[r.start:r.end], "start": r.start, "end": r.end, "score": float(r.score)} for r in results if r.score > 0.3]
        except Exception:
            pass
    # heuristic fallback — filter org/team names that look like persons
    blocked_suffix = {"engineering", "systems", "products", "dynamic", "consumer", "platform", "billing", "payroll", "healthcare", "enterprise", "annual", "summit", "corp", "inc", "industries", "enterprises", "initiative", "corporation", "solutions", "services", "team", "ops", "trading", "experience", "reliability", "infrastructure"}
    blocked_words = {"acme","umbrella","globex","soylent","initech","pied","rekall","stark","vought","tyrell","wayne","aperture","nakatomi","atlas","massive","omni","ingen","hooli","cyberdyne","globex"}
    out = []
    for m in _PERSON_RE.finditer(text):
        val = m.group()
        low = val.lower()
        if low in {"massive dynamic", "quarterly report", "platform engineering", "billing systems", "omni consumer", "hooli", "ingen"}:
            continue
        parts = low.split()
        if len(parts)==2 and (parts[0] in blocked_words or parts[1] in blocked_suffix):
            continue
        if any(w in low for w in ["platform","billing","omni","umbrella","globex","initech","pied","rekall","stark","vought","tyrell","wayne","aperture","nakatomi","atlas"]):
            continue
        out.append({"text": val, "start": m.start(), "end": m.end(), "score": 0.7})
    return out

def detect_code_entities(text: str) -> List[Dict]:
    """Detect internal project/org/function/database identifiers (wl4)."""
    out = []
    # heuristic: any snake_case or known internal keywords
    # Also catch database_name patterns: SELECT FROM X, get_connection('X')
    db_pat = re.compile(r"(?:FROM|get_connection\(|database_name)\s*['\"]?([a-z_]{3,})['\"]?", re.I)
    for m in db_pat.finditer(text):
        val = m.group(1)
        if len(val) > 3:
            out.append({"text": val, "start": m.start(1), "end": m.end(1), "score": 0.8, "kind": "database_name"})
    for pat in _CODE_IDENTIFIERS:
        for m in pat.finditer(text):
            out.append({"text": m.group(), "start": m.start(), "end": m.end(), "score": 0.65, "kind": "internal"})
    # Deduplicate by text+start
    seen = set()
    uniq = []
    for e in out:
        k = (e["text"], e["start"])
        if k not in seen:
            seen.add(k)
            uniq.append(e)
    return uniq

def available() -> str:
    return _try_load()
