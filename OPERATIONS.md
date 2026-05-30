# Operations Guide

## Backups

For Supabase-hosted Postgres, use Supabase's built-in backups for production projects when available. For self-managed Postgres, run regular `pg_dump` backups.

Manual backup:

```bash
pg_dump "$DATABASE_URL" > guardrails_backup.sql
```

Manual restore into a fresh database:

```bash
psql "$DATABASE_URL" < guardrails_backup.sql
alembic upgrade head
```

Recommended backup cadence for a public demo:

- daily database backup
- before every schema migration
- before rotating database credentials

## Migration Rollback

Alembic migrations run on container startup. Before rolling back:

1. Take a database backup.
2. Identify the current revision:

```bash
alembic current
```

3. Roll back one migration only if the migration is known to be reversible:

```bash
alembic downgrade -1
```

4. Redeploy the previous application image.

## Incident Checklist

If a key is exposed:

1. Revoke the exposed provider key or gateway key.
2. Create a replacement key.
3. Update the deployment environment variable.
4. Redeploy the app.
5. Check analytics for suspicious traffic.
6. Lower demo limits if needed.

If quota spikes:

1. Enable or tighten `DEMO_MODE`.
2. Lower `DEMO_MAX_OUTPUT_TOKENS`.
3. Lower `DEMO_RATE_LIMIT_RPD` and `DEMO_IP_RATE_LIMIT_RPD`.
4. Review `/analytics/dashboard` for blocked and rate-limited requests.

## Logs

The app emits JSON request logs with:

- `request_id`
- HTTP method and path
- status code
- latency
- client IP

The response also includes `X-Request-ID`, so user-reported failures can be matched to server logs.
