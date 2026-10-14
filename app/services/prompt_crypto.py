"""
At-rest encryption for the optional full_prompt audit column.

When ENCRYPTION_KEY is set (Fernet key, `python -c "from cryptography.fernet
import Fernet; print(Fernet.generate_key().decode())"`), stored full prompts are
encrypted with Fernet's authenticated AES-CBC format; the admin replay endpoint
decrypts them on the fly. Without a key, full prompts are omitted from storage.
Malformed configured keys fail closed instead of storing plaintext.
"""
from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

_PREFIX = "enc:v1:"

_fernet: Fernet | None = None
_fernet_key: str | None = None


class PromptEncryptionError(ValueError):
    """Encryption is configured incorrectly or encrypted evidence is unreadable."""


def _client() -> Fernet | None:
    global _fernet, _fernet_key
    key = get_settings().ENCRYPTION_KEY or ""
    if not key:
        _fernet = None
        _fernet_key = None
        return None
    if _fernet is None or _fernet_key != key:
        try:
            _fernet = Fernet(key.encode())
        except (ValueError, TypeError):
            _fernet = None
            _fernet_key = None
            raise PromptEncryptionError("ENCRYPTION_KEY must be a valid Fernet key") from None
        _fernet_key = key
    return _fernet


def encrypt_prompt(text: str) -> str | None:
    client = _client()
    if client is None:
        return None
    return _PREFIX + client.encrypt(text.encode()).decode()


def decrypt_prompt(text: str) -> str:
    if not text or not text.startswith(_PREFIX):
        return text
    client = _client()
    if client is None:
        raise PromptEncryptionError("The encryption key is required to read encrypted audit evidence")
    try:
        return client.decrypt(text[len(_PREFIX):].encode()).decode()
    except (InvalidToken, ValueError):
        raise PromptEncryptionError("Encrypted audit evidence could not be decrypted") from None
