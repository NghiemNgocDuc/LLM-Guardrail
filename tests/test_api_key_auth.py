import pytest
from fastapi import HTTPException

from app.deps import (
    MIN_GATEWAY_KEY_LENGTH,
    normalize_gateway_api_key,
    validate_gateway_api_key_format,
)
from app.models import APIKey


def test_normalize_gateway_api_key_strips_whitespace():
    raw = APIKey.generate_raw_key()
    assert normalize_gateway_api_key("  " + raw + "  ") == raw


def test_validate_gateway_api_key_rejects_provider_keys():
    with pytest.raises(HTTPException) as exc:
        validate_gateway_api_key_format("gsk_" + "a" * 40)
    assert "grg_" in exc.value.detail


def test_validate_gateway_api_key_rejects_prefix_only():
    prefix = APIKey.generate_raw_key()[:12]
    assert len(prefix) < MIN_GATEWAY_KEY_LENGTH
    with pytest.raises(HTTPException) as exc:
        validate_gateway_api_key_format(prefix)
    assert "incomplete" in exc.value.detail.lower()
