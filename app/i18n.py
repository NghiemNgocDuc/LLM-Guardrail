"""Internationalization — lazy-loaded JSON locale files, contextvar-based translation.

Usage anywhere in the codebase:
    from app.i18n import _t
    raise HTTPException(status_code=401, detail=_t("auth.token_missing"))

The language is set per-request by I18nMiddleware from the Accept-Language header.
Falls back to "en" if the locale file doesn't exist or the key is missing.
"""

import json
import os
import re
from contextvars import ContextVar
from pathlib import Path

_current_lang: ContextVar[str] = ContextVar("current_lang", default="en")
_locales: dict[str, dict[str, str]] = {}
_locales_dir = Path(__file__).resolve().parent / "locales"

# Only allow simple language tags — no slashes, dots, or path separators.
_VALID_LANG_RE = re.compile(r"^[a-z]{2}(?:-[a-z]{2})?$")


def _validate_lang(lang: str) -> str:
    """Return a safe language tag or fall back to ``"en"``."""
    if _VALID_LANG_RE.match(lang):
        return lang
    return "en"


def _load_locale(lang: str) -> dict[str, str]:
    lang = _validate_lang(lang)
    if lang in _locales:
        return _locales[lang]
    path = _locales_dir / f"{lang}.json"
    try:
        if not path.resolve().parent == _locales_dir.resolve():
            # Safety net: the resolved path must stay inside locales/.
            raise ValueError("path traversal detected")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        data = {}
    _locales[lang] = data
    return data


def _t(key: str, **kwargs) -> str:
    lang = _current_lang.get()
    table = _load_locale(lang)
    template = table.get(key)
    if template is None:
        table = _load_locale("en")
        template = table.get(key, key)
    return template.format(**kwargs) if kwargs else template


def _t_or(key: str, fallback: str, **kwargs) -> str:
    """Translate ``key``; if the key is missing from every locale, return ``fallback``."""
    lang = _current_lang.get()
    template = _load_locale(lang).get(key)
    if template is None:
        template = _load_locale("en").get(key)
    if template is None:
        template = fallback
    return template.format(**kwargs) if kwargs else template


def set_language(lang: str) -> None:
    _current_lang.set(normalize_lang(lang))


def normalize_lang(header: str) -> str:
    tag = header.split(",")[0].split(";")[0].strip().lower() if header else "en"
    if tag.startswith("zh"):
        return "zh"
    if tag.startswith("es"):
        return "es"
    if tag.startswith("fr"):
        return "fr"
    if tag.startswith("de"):
        return "de"
    if tag.startswith("ja"):
        return "ja"
    if tag.startswith("ko"):
        return "ko"
    return "en"
