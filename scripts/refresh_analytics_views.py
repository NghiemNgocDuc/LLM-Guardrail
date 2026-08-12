#!/usr/bin/env python
"""Refresh the analytics materialized views (mv_blocked_reasons_daily,
mv_false_positive_candidates_daily) with REFRESH MATERIALIZED VIEW CONCURRENTLY.

The views back GET /analytics/top-blocked-reasons and
GET /analytics/false-positive-candidates. They are read-only snapshots: the
endpoints' data is as fresh as the last refresh. Schedule this on a cron-like
timer (e.g. hourly or every 15 minutes, depending on request volume):

    15 * * * *  cd /opt/guardrails && scripts/refresh_analytics_views.sh

The .sh wrapper guards against concurrent runs (REFRESH ... CONCURRENTLY
requires exclusive-in-waiters semantics; overlapping runs would queue).

Staleness window: with an hourly schedule, the dashboard can lag live data by
up to 1 hour + the refresh duration. REFRESH ... CONCURRENTLY does not lock
reads, so the refresh itself adds no downtime.
"""
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings

VIEWS = [
    "mv_blocked_reasons_daily",
    "mv_false_positive_candidates_daily",
]


async def refresh_all(database_url: str | None = None) -> dict[str, int]:
    """Refresh every analytics view. Returns {view_name: rows_updated}. """
    engine = create_async_engine(database_url or get_settings().DATABASE_URL)
    counts: dict[str, int] = {}
    async with engine.begin() as conn:
        for view in VIEWS:
            result = await conn.execute(text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view}"))
            counts[view] = result.rowcount if result.rowcount is not None else -1
    await engine.dispose()
    return counts


def main() -> None:
    counts = asyncio.run(refresh_all())
    for view, updated in counts.items():
        print(f"{view}: refreshed ({updated} rows changed)")


if __name__ == "__main__":
    main()
