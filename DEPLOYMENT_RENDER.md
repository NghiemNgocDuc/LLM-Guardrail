# Deploying to Render with Supabase and Upstash

This project can be deployed to Render (web services) with Supabase Postgres and Upstash Redis for production state.

Steps

1. Create Supabase project
   - Create a Supabase project and database.
   - Copy the Postgres connection string (postgresql://...) and set it as `DATABASE_URL`.

2. Create Upstash Redis
   - Create a Redis database in Upstash and copy the connection URL.
   - Set as `RATE_LIMIT_REDIS_URL`.

3. Create Render services
   - Connect your GitHub repo to Render.
   - Render will recognize `render.yaml` and propose creating two services:
     - `llm-guardrail-api` (uses `Dockerfile`)
     - `llm-guardrail-web` (uses `Dockerfile.frontend`)

4. Set environment variables in Render
   - For the API service, set these env vars (as secrets):
     - `DATABASE_URL` (Supabase connection)
     - `RATE_LIMIT_REDIS_URL` (Upstash URL)
     - `SECRET_KEY` (strong secret)
     - Any provider API keys (e.g., `GROQ_API_KEY`, `OPENAI_API_KEY`)

5. Configure GitHub Actions
   - In your GitHub repository, add secrets:
     - `RENDER_API_KEY` — render service API key (optional, for trigger deploys)
     - `RENDER_SERVICE_ID` — the Render API service ID for the API service (optional)

6. Push to `main` to trigger CI
   - The workflow `.github/workflows/deploy-to-render.yml` builds the API Docker image and triggers a Render deploy via API.

Notes

- The CI uses GitHub Container Registry (GHCR) to push images; you can change to Docker Hub or skip pushing if Render builds from repo directly.
- For automatic database provisioning you can use Supabase CLI / Terraform; this guide assumes manual creation.
- Ensure you do not commit any production secrets to the repository.

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
