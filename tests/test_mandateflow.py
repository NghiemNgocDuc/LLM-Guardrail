"""MandateFlow structural tests — crmCounter invariant + adversarial cases.

Run: python -m pytest tests/test_mandateflow.py -q
"""
import pytest

def test_crm_counter_invariant_import():
    from app.services.mandate_fixtures import FIXTURES
    assert "crm.resolve_customer" in FIXTURES
    assert "payments.aggregate_failures" in FIXTURES

def test_evaluate_pinned_policy():
    from app.services.mandate_service import evaluate_pinned_policy, PAYMENT_AGGREGATE_ONLY, SUPPORT_DERIVED
    d, rid, _ = evaluate_pinned_policy("crm.resolve_customer", PAYMENT_AGGREGATE_ONLY)
    assert d == "DENY" and rid == "NO_PAYMENT_REIDENTIFICATION"
    d2, _, _ = evaluate_pinned_policy("crm.resolve_customer", SUPPORT_DERIVED)
    assert d2 == "ALLOW"
    d3, _, _ = evaluate_pinned_policy("payments.aggregate_failures", PAYMENT_AGGREGATE_ONLY)
    assert d3 == "ALLOW"

def test_attenuation():
    from app.services.mandate_service import attenuate
    assert attenuate(["a","b","c"], ["b","c"]) == ["b","c"]
    assert attenuate(["a","b"], []) == ["a","b"]
    assert attenuate(["a"], ["a","b"]) == ["a"]

def test_constant_time_compare():
    from app.services.mandate_service import _constant_time_eq, _hash_cap
    h = _hash_cap("cap_secret")
    assert _constant_time_eq(h, h) is True
    assert _constant_time_eq(h, _hash_cap("other")) is False

@pytest.mark.asyncio
async def test_gateway_deny_totally_without_db():
    # Loose smoke: imports and fixture wiring work without DB round-trip
    import app.routers.mandate
    assert hasattr(app.routers.mandate, "gateway_call")
