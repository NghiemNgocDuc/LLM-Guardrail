#!/usr/bin/env bash
# Refresh the analytics materialized views (see refresh_analytics_views.py).
# Safe to schedule from cron:
#   15 * * * *  cd /opt/guardrails && scripts/refresh_analytics_views.sh
# The flock guard prevents overlapping refreshes from stacking up.
set -euo pipefail

LOCKFILE="/tmp/refresh_analytics_views.lock"
exec 9>"$LOCKFILE"
flock -n 9 || { echo "Analytics view refresh already running — skipping"; exit 0; }

cd "$(dirname "$0")/.."

if [ -z "${DATABASE_URL:-}" ] && [ -f .env ]; then
  # shellcheck disable=SC1091
  source .env
fi

if [ -z "${DATABASE_URL:-}" ]; then
  echo "DATABASE_URL not set — skipping analytics view refresh" >&2
  exit 1
fi

if command -v venv312/bin/python &>/dev/null; then
  PY=venv312/bin/python
elif command -v venv/bin/python &>/dev/null; then
  PY=venv/bin/python
else
  PY=python
fi

exec "$PY" scripts/refresh_analytics_views.py
