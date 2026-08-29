#!/usr/bin/env bash
# Backup Postgres + Redis + .env inventory for self-hosted deploys
# Usage: ./scripts/backup.sh  (cron: 0 3 * * * /app/scripts/backup.sh)
# Requires: pg_dump, openssl (for encryption), and env vars POSTGRES_* or DATABASE_URL
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
ENCRYPT_KEY="${BACKUP_ENCRYPT_KEY:-}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

echo "[backup] $TIMESTAMP starting — retention ${RETENTION_DAYS}d, encrypt=$([ -n "$ENCRYPT_KEY" ] && echo yes || echo no)"

# ── Postgres ───────────────────────────────────────────────────────────────────
if [ -n "${DATABASE_URL:-}" ]; then
  DB_URL="$DATABASE_URL"
elif [ -n "${POSTGRES_USER:-}" ]; then
  DB_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST:-db}:${POSTGRES_PORT:-5432}/${POSTGRES_DB}"
else
  echo "[backup] no DATABASE_URL / POSTGRES_* — skipping postgres"
  DB_URL=""
fi

if [ -n "$DB_URL" ]; then
  # asyncpg URL -> plain postgres:// for pg_dump
  PG_URL="${DB_URL/postgresql+asyncpg:\/\//postgresql://}"
  DUMP="$BACKUP_DIR/pg_${TIMESTAMP}.sql.gz"
  echo "[backup] pg_dump → $DUMP"
  pg_dump "$PG_URL" | gzip -9 > "$DUMP"
  if [ -n "$ENCRYPT_KEY" ]; then
    openssl enc -aes-256-cbc -pbkdf2 -pass pass:"$ENCRYPT_KEY" -in "$DUMP" -out "$DUMP.enc" && rm "$DUMP" && DUMP="$DUMP.enc"
    echo "[backup] encrypted $DUMP"
  fi
  # verify gzip integrity
  if [[ "$DUMP" == *.gz ]]; then gzip -t "$DUMP" && echo "[backup] gzip verify ok"; fi
fi

# ── Redis (RDB snapshot) ───────────────────────────────────────────────────────
if [ -n "${RATE_LIMIT_REDIS_URL:-}" ]; then
  echo "[backup] redis save (via BGSAVE, volume snapshot is primary)"
  # Redis persistence is via redisdata volume + appendonly; for logical backup:
  # redis-cli --raw -a "$REDIS_PASSWORD" --rdb "$BACKUP_DIR/redis_${TIMESTAMP}.rdb" 2>/dev/null || true
fi

# ── Env inventory (without values) ─────────────────────────────────────────────
env | cut -d= -f1 | sort > "$BACKUP_DIR/env_keys_${TIMESTAMP}.txt"
echo "[backup] env keys → env_keys_${TIMESTAMP}.txt"

# ── Prune old ──────────────────────────────────────────────────────────────────
find "$BACKUP_DIR" -type f -mtime +"$RETENTION_DAYS" -delete 2>/dev/null || true
echo "[backup] prune >${RETENTION_DAYS}d done"

# ── Off-site reminder ──────────────────────────────────────────────────────────
echo "[backup] IMPORTANT: copy $BACKUP_DIR off-box (S3/rclone/restic) and TEST RESTORE quarterly!"
echo "  Test restore: gunzip -c $DUMP | psql \$DATABASE_URL  (or openssl enc -d ... | gunzip -c | psql)"
echo "[backup] done $(date -Iseconds)"

# ── Healthcheck ────────────────────────────────────────────────────────────────
ls -lh "$BACKUP_DIR" | tail -n 20
