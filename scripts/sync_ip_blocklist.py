#!/usr/bin/env python
"""Sync the app's IP blocklist into an nftables set (self-hosted Linux hosts).

Sources — this is where the app actually keeps blocklist state:

1. Authoritative (PostgreSQL): per-org ``compliance_rules["blocked_ips"]`` in
   ``org_policies``, checked on every /chat request (app/routers/chat.py).
   The sync unions every org's list — nftables cannot be org-scoped, so the
   firewall drops anything any org blocked.

2. Derived (Redis): ``abuse:violations:{ip}`` counters from
   app/middleware/abuse_protection.py (TTL 1h). There is no explicit Redis
   blocklist set — the counters ARE the blocklist signal. IPs whose violation
   count reaches ``--threshold`` (default 3) are firewall-dropped too.

Mechanics: the script renders a full ruleset — ``flush set`` then ``add
element`` for every IP — and applies it with a single ``nft -f``. Because the
set is rebuilt from scratch each run, stale entries (expired TTLs, unblocked
IPs) disappear automatically. IPv4 only: the set is ``type ipv4_addr``;
IPv6 addresses from either source are skipped (logged in --verbose).

Deployment honesty: Render/Fly (the production target) are managed platforms
without host nftables access — this is for self-hosted Linux hosts only:

    5 * * * *  cd /opt/guardrails && scripts/sync_ip_blocklist.sh

The .sh wrapper flock-guards against concurrent runs. One-time bootstrap:

    sudo nft -f scripts/blocklist.nft
"""
import argparse
import asyncio
import ipaddress
import os
import subprocess
import sys
import tempfile

TABLE = "inet guardrails"
SET = "blocklist"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--threshold",
        type=int,
        default=int(os.environ.get("NFTABLES_VIOLATION_THRESHOLD", "3")),
        help="Redis violation count at which an IP is dropped (default 3)",
    )
    parser.add_argument(
        "--nft-binary", default="nft", help="nftables binary (default: nft)"
    )
    parser.add_argument("--dry-run", action="store_true", help="render + print, don't run nft")
    parser.add_argument("--verbose", action="store_true", help="log skipped/invalid IPs")
    return parser.parse_args(argv)


def build_blocklist(explicit: list[str], violations: dict[str, int], threshold: int) -> list[str]:
    """Union of explicit blocked_ips and Redis repeat offenders, validated to
    IPv4, deduped, sorted. Invalid entries and IPv6 addresses are skipped."""
    candidates = list(explicit)
    candidates += [ip for ip, count in violations.items() if count >= threshold]

    seen: set[str] = set()
    result: list[str] = []
    for raw in candidates:
        ip = str(raw).strip()
        if not ip:
            continue
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if addr.version != 4:
            continue
        if ip in seen:
            continue
        seen.add(ip)
        result.append(ip)
    return sorted(result)


def render_ruleset(ips: list[str]) -> str:
    """Full-rebuild ruleset: flush the set, then add every current IP."""
    lines = [f"flush set {TABLE} {SET}"]
    if ips:
        lines.append(f"add element {TABLE} {SET} {{ {', '.join(ips)} }}")
    return "\n".join(lines) + "\n"


async def fetch_db_blocked_ips(database_url: str) -> list[str]:
    """Every org's compliance_rules.blocked_ips (JSONB array) from org_policies."""
    if not database_url:
        return []
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as conn:
            rows = (await conn.execute(text(
                "SELECT compliance_rules->'blocked_ips' AS ips "
                "FROM org_policies WHERE compliance_rules ? 'blocked_ips'"
            ))).fetchall()
    finally:
        await engine.dispose()

    ips: list[str] = []
    for (value,) in rows:
        if value:
            ips.extend(str(ip) for ip in value)
    return ips


async def fetch_redis_violations(redis_url: str) -> dict[str, int]:
    """abuse:violations:{ip} counters — the derived blocklist signal."""
    if not redis_url:
        return {}
    from redis.asyncio import Redis

    client = Redis.from_url(redis_url, decode_responses=True)
    try:
        violations: dict[str, int] = {}
        async for key in client.scan_iter(match="abuse:violations:*", count=1000):
            ip = key.split(":", 2)[2]
            raw = await client.get(key)
            if raw:
                violations[ip] = int(raw)
        return violations
    finally:
        await client.aclose()


async def gather_ips(database_url: str, redis_url: str, threshold: int) -> list[str]:
    explicit, violations = await asyncio.gather(
        fetch_db_blocked_ips(database_url), fetch_redis_violations(redis_url)
    )
    return build_blocklist(explicit, violations, threshold)


def apply_ruleset(ruleset: str, nft_binary: str, dry_run: bool) -> None:
    if dry_run:
        print(ruleset, end="")
        return
    with tempfile.NamedTemporaryFile("w", suffix=".nft", delete=False) as f:
        f.write(ruleset)
        path = f.name
    try:
        subprocess.run(
            [nft_binary, "-f", path], check=True, capture_output=True, text=True
        )
    finally:
        os.unlink(path)


def main() -> int:
    args = parse_args()
    ips = asyncio.run(gather_ips(
        os.environ.get("DATABASE_URL", ""),
        os.environ.get("RATE_LIMIT_REDIS_URL", ""),
        args.threshold,
    ))
    if args.verbose:
        print(f"sync_ip_blocklist: {len(ips)} IPv4 addresses to apply "
              f"(threshold={args.threshold})", file=sys.stderr)
    apply_ruleset(render_ruleset(ips), args.nft_binary, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
