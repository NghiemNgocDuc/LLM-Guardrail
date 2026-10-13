# Deploying to Render with Supabase and Upstash

This project can be deployed to Render (web services) with Supabase Postgres and Upstash Redis for production state.

Steps

1. Create Supabase project
   - Create a Supabase project and database.
   - Copy the Postgres connection string (postgresql://...) and set it as `DATABASE_URL`.

2. Create Upstash Redis
   - Create a Redis database in Upstash and copy the connection URL.
   - Set as `RATE_LIMIT_REDIS_URL`.

3. Create the Render web service
   - Connect your GitHub repo to Render.
   - The current `render.yaml` defines one Docker web service using `Dockerfile.fullstack`.
   - That image builds the React dashboard and serves it from the FastAPI app on the same port.
   - For the existing deployment, use `https://llm-guardrail.onrender.com` as `PUBLIC_APP_URL` and `ALLOWED_ORIGINS`.
   - For a new service, substitute its assigned public hostname in both settings.
   - Set the health check path to `/health`.

4. Set environment variables in Render
   - For the web service, set these env vars (as secrets):
     - `DATABASE_URL` (Supabase connection)
     - `RATE_LIMIT_REDIS_URL` (Upstash URL)
     - `SECRET_KEY` (strong secret)
     - Any provider API keys (e.g., `GROQ_API_KEY`, `OPENAI_API_KEY`)
   - Set `DEFAULT_LLM_BACKEND` and `DEFAULT_MODEL` to match the provider key you configure.
   - Set frontend `VITE_*` values in the service environment. Render passes them to the matching `ARG` declarations in `Dockerfile.fullstack`; rebuild and deploy to update the bundled frontend.

5. Configure GitHub Actions
   - In your GitHub repository, add secrets:
     - `RENDER_API_KEY` — render service API key (optional, for trigger deploys)
     - `RENDER_SERVICE_ID` — the Render web service ID (optional)

6. Push to `main` to trigger CI
   - The workflow `.github/workflows/deploy-to-render.yml` publishes a backend Docker image to GHCR and optionally triggers a Render deploy when both secrets are present.
   - The Render service builds `Dockerfile.fullstack` from the repository; the GHCR backend image is a separate artifact.
   - If Render auto-deploy is already enabled, the API trigger is optional.

Notes

- The CI uses GitHub Container Registry (GHCR) to push images; you can change to Docker Hub or skip pushing if Render builds from repo directly.
- For automatic database provisioning you can use Supabase CLI / Terraform; this guide assumes manual creation.
- Ensure you do not commit any production secrets to the repository.

## UptimeRobot

Monitor `https://llm-guardrail.onrender.com/health` with a five-minute HTTP(s)
check. The endpoint returns 200 when the API and database respond, and 503
when the database check fails or times out. See
[OPERATIONS.md](OPERATIONS.md#uptimerobot-monitoring) for dashboard setup or
`scripts/setup_uptimerobot.py`. Account credentials belong in your local setup
environment; the running Render app does not need the UptimeRobot API key.

## Supabase connection string (important)

Use Supabase's **Transaction pooler** URI (port `6543`) for Render. The app disables prepared-statement caching for PgBouncer compatibility.

Set `DATABASE_URL` like:

```env
DATABASE_URL=postgresql+asyncpg://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres?ssl=require
```

Also set:

```env
APP_ENV=production
DEBUG=false
```

If you still see `DuplicatePreparedStatementError`, redeploy after pulling the latest code (Alembic migrations and the API must both use the same asyncpg connect settings).

## Troubleshooting

| Error | Fix |
| --- | --- |
| `DuplicatePreparedStatementError` / `prepared statement "__asyncpg_stmt_1__" already exists` | Use pooler port `6543`, ensure `DATABASE_URL` uses `postgresql+asyncpg://`, redeploy latest image |
| `DATABASE_URL must use postgresql+asyncpg` | Set `APP_ENV=production` and use the asyncpg scheme (or paste `postgres://` / `postgresql://` — the app normalizes it) |
| Redis TLS errors | Use Upstash `rediss://` URL for `RATE_LIMIT_REDIS_URL` |
