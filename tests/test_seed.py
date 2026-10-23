"""Development credentials must not create a predictable production account."""
import asyncio

import pytest

import seed


def test_seed_refuses_production_before_opening_database(monkeypatch):
    monkeypatch.setattr(seed.get_settings(), "APP_ENV", "production")
    monkeypatch.setattr(seed, "get_sessionmaker", lambda: pytest.fail("Production seed opened a database"))
    with pytest.raises(RuntimeError, match="only be created in development"):
        asyncio.run(seed.seed())


def test_seed_gateway_key_is_generated_and_not_shared():
    assert seed.SEED_RAW_KEY.startswith("grg_")
    assert len(seed.SEED_RAW_KEY) >= 40
    assert seed.SEED_RAW_KEY != seed.APIKey.generate_raw_key()
