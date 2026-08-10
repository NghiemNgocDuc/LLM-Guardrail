"""
guardrailctl — ops CLI for the LLM Guardrails Gateway.

Usage:
    python -m scripts.guardrailctl status
    python -m scripts.guardrailctl cost-anomaly [--days 14] [--mult 2.0] [--min-tokens 10000]

Subcommands:
    status         Print pipeline health: adapters, circuit breakers, and
                   optional features (response cache, webhook tracking,
                   at-rest prompt encryption).
    cost-anomaly   Scan RequestLog token usage per org per day and flag
                   orgs whose most recent day spiked above their own
                   baseline (median of the previous days *mult*).
"""
from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _settings():
    from app.config import get_settings
    return get_settings()


def _cmd_status(args):
    from app.config import get_settings
    from app.services.llm import _ADAPTERS

    settings = get_settings()
    print("guardrailctl status")
    print(f"  env            : {settings.APP_ENV} (debug={settings.DEBUG})")

    try:
        from app.services.llm.circuit_breaker import _breakers
        states = {name: br.state for name, br in _breakers.items()}
    except Exception:
        states = {}
    print(f"  adapters       : {', '.join(sorted(_ADAPTERS)) or '(none)'}")
    print(f"  default backend: {settings.DEFAULT_LLM_BACKEND} / {settings.DEFAULT_MODEL}")
    print(f"  failover chain : {settings.LLM_FAILOVER_BACKENDS.strip() or '(none configured)'}")
    print(f"  breakers       : {states or '(all closed / no traffic yet)'}")
    print(f"  cache          : RESPONSE_CACHE_ENABLED={settings.RESPONSE_CACHE_ENABLED}"
          f"{' +policy flag required' if settings.RESPONSE_CACHE_ENABLED else ''}")
    print(f"  webhook track  : redis={settings.RATE_LIMIT_REDIS_URL or '(memory fallback)'}")
    print(f"  prompt crypto  : ENCRYPTION_KEY={'set' if settings.ENCRYPTION_KEY else 'not set — plain at rest'}")


async def _cost_anomaly(args) -> int:
    from app.database import get_engine
    from app.models import RequestLog

    settings = _settings()
    if not settings.DATABASE_URL:
        print("error: DATABASE_URL is not configured; cannot query usage.", file=sys.stderr)
        return 2

    since = datetime.now(timezone.utc) - timedelta(days=args.days)
    engine = get_engine()
    day_col = func.date(RequestLog.created_at)
    async with AsyncSession(engine) as session:
        result = await session.execute(
            select(
                RequestLog.org_id,
                day_col.label("day"),
                func.sum(RequestLog.input_tokens + RequestLog.output_tokens).label("tokens"),
            )
            .where(RequestLog.status == "delivered", RequestLog.created_at >= since)
            .group_by(RequestLog.org_id, day_col)
            .order_by(day_col)
        )
        rows = result.all()

    per_org: dict[str, dict] = defaultdict(dict)
    for org_id, day, tokens in rows:
        per_org[org_id][day] = int(tokens or 0)

    today = datetime.now(timezone.utc).date()
    anomalies = []
    for org_id, daily in sorted(per_org.items()):
        if today not in daily:
            continue
        baseline = [t for d, t in daily.items() if d != today]
        if len(baseline) < 2:
            continue
        median = statistics.median(baseline)
        current = daily[today]
        threshold = max(median * args.mult, args.min_tokens)
        if current > threshold:
            anomalies.append((org_id, median, current, threshold, len(baseline)))

    if not anomalies:
        print("cost-anomaly: no spikes detected in the last "
              f"{args.days} days (median*{args.mult} or {args.min_tokens} tokens floor).")
        return 0

    print(f"cost-anomaly: {len(anomalies)} org(s) spiked above baseline "
          f"(median*{args.mult}, floor {args.min_tokens}):")
    print(f"  {'org_id':<38} {'baseline':>12} {'today':>12} {'threshold':>12} {'days':>5}")
    for org_id, median, current, threshold, days in anomalies:
        print(f"  {org_id:<38} {median:>12.0f} {current:>12.0f} {threshold:>12.0f} {days:>5}")
    return 1


def _cmd_cost_anomaly(args) -> int:
    return asyncio.run(_cost_anomaly(args))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="guardrailctl",
        description="Operations CLI for the LLM Guardrails Gateway.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="print pipeline health and feature flags")

    cost = sub.add_parser("cost-anomaly", help="flag orgs whose daily token spend spiked")
    cost.add_argument("--days", type=int, default=14, help="lookback window in days (default 14)")
    cost.add_argument("--mult", type=float, default=2.0, help="spike multiple over baseline median (default 2.0)")
    cost.add_argument("--min-tokens", type=int, default=10_000,
                      help="absolute floor in tokens before a spike counts (default 10000)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "status":
        _cmd_status(args)
        return 0
    if args.command == "cost-anomaly":
        return _cmd_cost_anomaly(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())