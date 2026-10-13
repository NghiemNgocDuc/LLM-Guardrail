# Operations Guide

## UptimeRobot monitoring

Monitor the public app's `/health` endpoint. It accepts GET and HEAD without
authentication, returns **200** when the API and database respond, and **503**
when the database fails or the five-second health check times out. Responses
are not cached. Probes do not call LLM providers or consume gateway tokens.
Redis and provider health are available separately at `/health/detailed` and
`/health/breakers`; they are not part of this monitor.

### Dashboard setup

1. Create an HTTP(s) monitor in [UptimeRobot](https://dashboard.uptimerobot.com/).
2. Use `https://llm-guardrail.onrender.com/health`, with HTTP method **GET** (HEAD also works).
3. Set a five-minute interval and a 30-second request timeout.
4. Enable a verified alert contact for downtime and recovery notifications.
5. Leave SSL verification enabled; accept 200 as up and 503 as down.

The production monitor URL is `https://llm-guardrail.onrender.com/health`.
For another deployment, substitute its public hostname. The Render blueprint
also uses `/health` for its own
deployment health checks. For existing services, confirm that path in Render's
service settings after deploying these changes.

### Repeatable setup command

The script uses UptimeRobot's [documented v2 API](https://uptimerobot.com/api/legacy/).
Put an account API key with write access and your verified alert contact IDs in
the local `.env` (or export them as environment variables):

```env
UPTIMEROBOT_API_KEY=<account-api-key>
UPTIMEROBOT_ALERT_CONTACTS=123_0_0
```

Multiple contacts use `123_0_0-456_0_0`; the zeroes select immediate alerts
without repeated notifications. Keep this key out of frontend `VITE_*` values.
It is only needed when running the setup script, so the running app does not
need access to the UptimeRobot account.

From the repository root, using the project's Python environment:

```bash
python scripts/setup_uptimerobot.py --url https://llm-guardrail.onrender.com --dry-run
python scripts/setup_uptimerobot.py --url https://llm-guardrail.onrender.com
```

If `--url` is omitted, the script uses `PUBLIC_APP_URL` from the environment or
`.env`. Dry-run makes no network calls and needs no API key. Actual setup requires
alert contact IDs so the new monitor can send notifications. Re-running the
command reuses an existing HTTP monitor at the same URL and preserves its
settings; check its interval, method and alert contacts in the dashboard.
Paused monitors and duplicate HTTP monitors produce an error for manual review.

After deployment, check `curl -i https://llm-guardrail.onrender.com/health`, run setup,
and confirm the monitor is up and the intended contacts are selected.

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
