"""
Token pack catalog for AI Guardrails gateway usage.

Set STRIPE_PRICE_<SLUG> env vars to use pre-created Stripe Prices; otherwise Checkout
uses inline price_data from price_cents.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TokenPlan:
    slug: str
    name: str
    tokens: int
    price_cents: int
    currency: str = "usd"
    description: str = ""
    popular: bool = False
    stripe_price_env: str = ""  # e.g. STRIPE_PRICE_STARTER


TOKEN_PLANS: tuple[TokenPlan, ...] = (
    TokenPlan(
        slug="starter",
        name="Starter",
        tokens=500_000,
        price_cents=900,
        description="~500K gateway tokens — try production traffic.",
    ),
    TokenPlan(
        slug="growth",
        name="Growth",
        tokens=2_000_000,
        price_cents=2900,
        description="2M tokens for teams shipping agents + LLM flows.",
        popular=True,
    ),
    TokenPlan(
        slug="scale",
        name="Scale",
        tokens=10_000_000,
        price_cents=9900,
        description="10M tokens with guardrails at volume.",
    ),
    TokenPlan(
        slug="enterprise",
        name="Enterprise",
        tokens=50_000_000,
        price_cents=39900,
        description="Large packs — contact support for custom SLAs.",
    ),
)


def plan_by_slug(slug: str) -> TokenPlan | None:
    return next((p for p in TOKEN_PLANS if p.slug == slug), None)
