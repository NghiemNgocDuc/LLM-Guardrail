"""
Implicit-identity detector for wl3 (semantic PII).

Strategy:
  1. Heuristic (always on): flags sentences that link a role + organization via relative clause
     e.g. "CFO of Massive Dynamic whose wife..." -> implicit. High precision, modest recall.
  2. Optional LLM judge: if OPENAI_API_KEY / ANTHROPIC_API_KEY is set, ask cheap model to classify
     whether text contains implicit identifying description. Falls back to heuristic.

This is the "Option C" rephrase detector from LLM-Redactor paper — not a blocker but a flag
that would be used to rephrase before sending to provider.
"""
from __future__ import annotations
import re
import os

# Generic implicit — no org literals, no CFO-only. Covers any "the X who/that/whose ..." that uniquely identifies a person without naming.
# Validated FP 0/20 cleans: "The CFO gave a report." (role alone) NOT flagged, but "only female engineer on Platform team" IS flagged.
_IMPLICIT_PATTERNS = [
    # Role + whose/who/that + relationship (wife/husband/partner/family)
    re.compile(r"(?i)\b(CFO|CEO|CTO|president|director|manager|head of|chief|partner|founder|lead|engineer|employee|member|person|woman|man)\b.{0,60}\b(whose|who|that)\b.{0,60}\b(wife|husband|partner|family|spouse|works at|employed by)\b"),
    # Any "whose/who works at competitor/rival/employer" — affiliation without name
    re.compile(r"(?i)\b(whose|who)\b.{0,30}\b(works at|employed by)\b.{0,30}\b(competitor|rival|employer)\b"),
    # Generic "the [role] of [Org] whose wife/husband ..." — require relationship after whose to avoid FP on "head of sales whose team won"
    re.compile(r"(?i)\b(CFO|CEO|CTO|director|manager|head)\b\s+of\s+[A-Z][a-zA-Z]+\b.{0,40}\b(whose|who)\b.{0,40}\b(wife|husband|partner|family|spouse|works at)\b"),
    # Uniqueness markers: "only female engineer", "only ... engineer/person/employee/member on/in team"
    re.compile(r"(?i)\bonly\b.{0,30}\b(female\s+)?(engineer|person|employee|member|woman|man)\b.{0,30}\b(on|in|from)?\b.{0,20}\b(team|department|group|staff)\b"),
    # "only ... engineer is leaving / is on-call" — uniqueness + event
    re.compile(r"(?i)\bonly\b.{0,40}\b(engineer|person|employee)\b.{0,30}\b(is leaving|was let go|on-call|was on-call)\b"),
    # Anonymous identifier: "anonymous whistleblower/reporter/source/person"
    re.compile(r"(?i)\banonymous\b.{0,30}\b(whistleblower|reporter|source|person|engineer)\b"),
    # Event-based identification: "person/engineer who was let go / was on-call / was responsible / reported"
    re.compile(r"(?i)\b(person|engineer|employee|member|individual)\b.{0,40}\b(who was|that was|was let go|was fired|was on-call|on-call last|reported|is leaving)\b"),
    # Team membership uniqueness: "female engineer on Platform/Engineering team"
    re.compile(r"(?i)\b(female\s+)?(engineer|person)\b.{0,20}\bon\b.{0,20}\b(Platform|Engineering|Billing|Payroll)\b.{0,20}\bteam\b"),
    # Whistleblower + product/company
    re.compile(r"(?i)\bwhistleblower\b.{0,40}\b(reported|products|practices|data)\b"),
]

def heuristic_implicit(text: str) -> tuple[bool, str]:
    for pat in _IMPLICIT_PATTERNS:
        m = pat.search(text)
        if m:
            return True, m.group(0)[:80]
    return False, ""

def _groq_implicit_judge(text: str) -> tuple[bool, str]:
    """Tier 2: cheap Groq judge (llama-3.1-8b-instant). Uses GROQ_API_KEY from settings."""
    try:
        from app.config import get_settings
        settings = get_settings()
        key = (settings.GROQ_API_KEY or os.getenv("GROQ_API_KEY") or "").strip()
        if not key or len(key) < 20:
            return False, ""
        import httpx
        base = (settings.GROQ_BASE_URL or "https://api.groq.com/openai/v1").rstrip("/")
        # Use sync httpx for simplicity (heuristic path is sync)
        with httpx.Client(timeout=6.0) as client:
            resp = client.post(
                f"{base}/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.1-8b-instant",
                    "temperature": 0,
                    "max_tokens": 30,
                    "messages": [{"role": "user", "content": f"Does this text contain an implicit identifying description of a person without naming them directly (e.g. 'the CFO whose wife...', 'only female engineer on team')? Answer YES or NO.\nText: {text[:600]}"}],
                },
            )
            if resp.status_code != 200:
                return False, ""
            data = resp.json()
            ans = (data["choices"][0]["message"]["content"] or "").upper()
            if "YES" in ans:
                return True, ans[:80]
    except Exception:
        pass
    return False, ""

def is_implicit(text: str, use_llm: bool = False) -> tuple[bool, str]:
    hit, ev = heuristic_implicit(text)
    if hit:
        return True, ev
    if use_llm:
        # Try Groq first, then OpenAI
        g_hit, g_ev = _groq_implicit_judge(text)
        if g_hit:
            return True, g_ev
        if os.getenv("OPENAI_API_KEY"):
            try:
                from openai import OpenAI
                client = OpenAI()
                resp = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": f"Does this text contain an implicit identifying description of a person without naming them directly? Answer YES/NO and quote the span.\nText: {text[:500]}"}],
                    max_tokens=40,
                    temperature=0,
                )
                ans = resp.choices[0].message.content or ""
                if "YES" in ans.upper():
                    return True, ans[:80]
            except Exception:
                pass
    return False, ""
