from app.models import APIKey
import re


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60]


def test_slugify_normalizes_org_name():
    assert _slugify("Acme, Inc. Platform!") == "acme-inc-platform"


def test_api_key_generation_has_gateway_prefix():
    raw_key = APIKey.generate_raw_key()

    assert raw_key.startswith("grg_")
    assert len(raw_key) > 20
