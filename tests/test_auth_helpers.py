from app.models import APIKey
from app.routers.auth import _slugify


def test_slugify_normalizes_org_name():
    assert _slugify("Acme, Inc. Platform!") == "acme-inc-platform"


def test_api_key_generation_has_gateway_prefix():
    raw_key = APIKey.generate_raw_key()

    assert raw_key.startswith("grg_")
    assert len(raw_key) > 20
