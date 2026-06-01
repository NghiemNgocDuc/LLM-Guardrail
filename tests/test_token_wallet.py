from app.billing.plans import TOKEN_PLANS, plan_by_slug
from app.services.token_wallet import estimate_request_tokens


def test_plans_catalog():
    assert len(TOKEN_PLANS) >= 3
    growth = plan_by_slug("growth")
    assert growth is not None
    assert growth.tokens == 2_000_000


def test_estimate_request_tokens():
    est = estimate_request_tokens("a" * 400, 256)
    assert est >= 256
