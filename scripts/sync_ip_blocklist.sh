#!/usr/bin/env bash
# Sync the app's IP blocklist into the nftables set (see sync_ip_blocklist.py).
# Safe to schedule from cron (self-hosted Linux hosts only — the Render/Fly
# deploy target has no host nftables):
#   5 * * * *  cd /opt/guardrails && scripts/sync_ip_blocklist.sh
# The flock guard prevents overlapping syncs from stacking up.
set -euo pipefail

LOCKFILE="/tmp/sync_ip_blocklist.lock"
exec 9>"$LOCKFILE"
flock -n 9 || { echo "IP blocklist sync already running — skipping"; exit 0; }

cd "$(dirname "$0")/.."

if [ -z "${DATABASE_URL:-}" ] && [ -f .env ]; then
  # shellcheck disable=SC1091
  source .env
fi

if [ -z "${DATABASE_URL:-}" ] && [ -z "${RATE_LIMIT_REDIS_URL:-}" ]; then
  echo "DATABASE_URL and RATE_LIMIT_REDIS_URL both unset — nothing to sync" >&2
  exit 1
fi

if command -v venv312/bin/python &>/dev/null; then
  PY=venv312/bin/python
elif command -v venv/bin/python &>/dev/null; then
  PY=venv/bin/python
else
  PY=python
fi

exec "$PY" scripts/sync_ip_blocklist.py "$@"
