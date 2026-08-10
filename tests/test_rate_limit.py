import pytest
from fastapi import HTTPException

from app.middleware import rate_limit


def test_memory_rate_limit_raises_clear_error():
    key = "test-rate-limit-key"
    rate_limit._minute_windows.pop(key, None)
    rate_limit._day_windows.pop(key, None)

    rate_limit._check_memory_rate_limit(key, rpm=1, rpd=10)

    with pytest.raises(HTTPException) as exc:
        rate_limit._check_memory_rate_limit(key, rpm=1, rpd=10)

    assert exc.value.status_code == 429
    assert "Rate limit exceeded" in exc.value.detail
