#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
TIMESTAMP=$(date -u +"%Y%m%dT%H%M%SZ")
RETENTION_DAYS="${RETENTION_DAYS:-30}"

mkdir -p "$BACKUP_DIR"

# ── PostgreSQL ────────────────────────────────────────────────────────────────
if command -v pg_dump &>/dev/null; then
  DB_URL="${DATABASE_URL:-}"
  if [ -n "$DB_URL" ]; then
    echo "Backing up PostgreSQL..."
    pg_dump "$DB_URL" --no-owner --no-acl | gzip > "$BACKUP_DIR/db_$TIMESTAMP.sql.gz"
    echo "  -> $BACKUP_DIR/db_$TIMESTAMP.sql.gz ($(du -h "$BACKUP_DIR/db_$TIMESTAMP.sql.gz" | cut -f1))"
  else
    echo "DATABASE_URL not set — skipping DB backup"
  fi
else
  echo "pg_dump not installed — skipping DB backup"
fi

# ── .env (redacted — strip secrets) ───────────────────────────────────────────
if [ -f .env ]; then
  sed 's/=.*/=REDACTED/' .env > "$BACKUP_DIR/env_$TIMESTAMP.txt"
  echo "  -> .env structure backed up (secrets redacted)"
fi

# ── Cleanup old backups ───────────────────────────────────────────────────────
find "$BACKUP_DIR" -name "db_*.sql.gz" -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "env_*.txt" -mtime +$RETENTION_DAYS -delete

echo "Backup complete (retention: $RETENTION_DAYS days)"
