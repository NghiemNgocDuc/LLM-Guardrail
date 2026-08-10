"""
Optional at-rest encryption for the full_prompt audit column.

When ENCRYPTION_KEY is set (Fernet key, `python -c "from cryptography.fernet
import Fernet; print(Fernet.generate_key().decode())"`), stored full prompts are
AES-GCM encrypted; the admin replay endpoint decrypts them on the fly. Without
the key, prompts are stored as plain text (previous behaviour) and this module
is a no-op passthrough.
"""
from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

_PREFIX = "enc:v1:"

_fernet: Fernet | None = None


def _client() -> Fernet | None:
    global _fernet
    if _fernet is None:
        key = get_settings().ENCRYPTION_KEY or ""
        if not key:
            return None
        try:
            _fernet = Fernet(key.encode())
        except (ValueError, TypeError):
            _fernet = None
    return _fernet


def encrypt_prompt(text: str) -> str:
    client = _client()
    if client is None:
        return text
    return _PREFIX + client.encrypt(text.encode()).decode()


def decrypt_prompt(text: str) -> str:
    if not text or not text.startswith(_PREFIX):
        return text
    client = _client()
    if client is None:
        return text
    try:
        return client.decrypt(text[len(_PREFIX):].encode()).decode()
    except (InvalidToken, ValueError):
        return text