# Deployment Guide

This app is safest to run as a public demo with:

- one hosted web/API service
- Supabase Postgres for durable data
- Upstash Redis for shared rate limiting
- provider keys stored only as host-side environment variables

References:

- Supabase Postgres connection strings: https://supabase.com/docs/reference/postgres/connection-strings
- Upstash Redis getting started: https://upstash.com/docs/redis/overall/getstarted
- Render environment variables: https://render.com/docs/configure-environment-variables
- Koyeb environment variables: https://www.koyeb.com/docs/build-and-deploy/environment-variables

## Supabase Postgres

1. Create a Supabase project.
2. Open **Project Settings -> Database -> Connection string**.
3. Prefer the pooler connection string for hosted app platforms.
4. Replace `[YOUR-PASSWORD]` with the database password.
5. Convert the SQLAlchemy scheme to asyncpg:

```env
DATABASE_URL=postgresql+asyncpg://postgres.<project-ref>:<password>@<pooler-host>:6543/postgres
```

If Supabase gives a URL with `sslmode=require`, use `ssl=require` for asyncpg:

```env
DATABASE_URL=postgresql+asyncpg://postgres.<project-ref>:<password>@<pooler-host>:6543/postgres?ssl=require
```

The app sets `statement_cache_size=0` and `prepared_statement_cache_size=0` on every asyncpg connection so PgBouncer (Supabase pooler) does not raise `DuplicatePreparedStatementError`. You do not need to add those to the URL manually.

Do not commit this value. Store it only in your hosting provider's secret/env settings.

## Upstash Redis

1. Create an Upstash Redis database.
2. Copy the Redis connection URL.
3. Set it as:

```env
RATE_LIMIT_REDIS_URL=rediss://:<password>@<host>:<port>
```

Use the TLS `rediss://` URL when Upstash provides one. The app accepts both `redis://` and `rediss://`.

## Email (signup confirmation and password reset)

Configure SMTP so new users must confirm email before login.

```env
PUBLIC_APP_URL=https://your-render-service.onrender.com
REQUIRE_EMAIL_VERIFICATION=true
SMTP_HOST=smtp.resend.com
SMTP_PORT=587
SMTP_USER=resend
SMTP_PASSWORD=<your-smtp-password>
SMTP_FROM=LLM Guardrail <onboarding@yourdomain.com>
SMTP_USE_TLS=true
```

Works with Resend, SendGrid, Gmail SMTP, Amazon SES, and similar providers.

In development, if SMTP is not configured, verification is skipped and links are printed in API logs.

## Required Runtime Env Vars

Set these in Render or Koyeb, not in GitHub:

```env
APP_ENV=production
DEBUG=false
SECRET_KEY=<long-random-secret>
PUBLIC_APP_URL=https://your-render-service.onrender.com
DATABASE_URL=postgresql+asyncpg://...
RATE_LIMIT_REDIS_URL=redis://...
SMTP_HOST=...
SMTP_FROM=...
SMTP_USER=...
SMTP_PASSWORD=...

DEFAULT_LLM_BACKEND=groq
DEFAULT_MODEL=openai/gpt-oss-20b
GROQ_API_KEY=<your-groq-key>
GROQ_BASE_URL=https://api.groq.com/openai/v1

ALLOWED_ORIGINS=https://<your-public-domain>
```

Use a generated secret for `SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Render

Recommended shape:

1. Create a new Web Service from the GitHub repository.
2. Choose Docker deployment.
3. Use `Dockerfile.fullstack` for a single public demo service.
4. Add the runtime env vars from this guide.
5. Deploy.

If you want to keep separate frontend/backend services instead:

- deploy the API on Render and host the frontend separately as a static site with `VITE_API_BASE_URL=https://<api-service>`
- keep using Docker Compose on a VPS or platform that supports Compose directly

## Koyeb

Recommended shape:

1. Create an app from the GitHub repository.
2. Use Dockerfile-based deployment with `Dockerfile.fullstack`.
3. Add the runtime env vars as Koyeb secrets/environment variables.
4. Set the public port to `8000` for the API container.
5. Deploy.

As with Render, the current repo has a separate frontend image. For a single public demo, either deploy the frontend separately with `VITE_API_BASE_URL` pointing at the API, or add a single-container deployment target later.

## Public Demo Rate Limits

Enable demo mode before sharing a public link that uses your Groq quota:

```env
DEMO_MODE=true
DEMO_RATE_LIMIT_RPM=5
DEMO_RATE_LIMIT_RPD=25
DEMO_IP_RATE_LIMIT_RPM=20
DEMO_IP_RATE_LIMIT_RPD=100
DEMO_MAX_PROMPT_CHARS=2000
DEMO_MAX_OUTPUT_TOKENS=1024
```

For a fixed shared demo account:

```env
DEMO_DISABLE_SIGNUPS=true
```

Suggested public-demo starting point:

- `DEMO_RATE_LIMIT_RPM=3`
- `DEMO_RATE_LIMIT_RPD=20`
- `DEMO_IP_RATE_LIMIT_RPM=10`
- `DEMO_IP_RATE_LIMIT_RPD=50`
- `DEMO_MAX_OUTPUT_TOKENS=1024` (lower to save Groq quota on a public demo)

Raise those only after watching usage and cost.

## Key Rotation

Rotate provider keys immediately if they are exposed or if you are switching environments.

Groq or other provider key:

1. Create a new key in the provider dashboard.
2. Update `GROQ_API_KEY` or the relevant provider env var in the host dashboard.
3. Redeploy/restart the app.
4. Confirm `/health` returns `{"status":"ok"}`.
5. Revoke the old provider key.

App `SECRET_KEY`:

1. Generate a new value.
2. Update `SECRET_KEY` in the host dashboard.
3. Redeploy/restart the app.
4. Ask users to log in again.

Database password:

1. Rotate the password in Supabase.
2. Update `DATABASE_URL`.
3. Redeploy/restart the app.
4. Verify migrations and `/health`.

Gateway API keys:

1. Create a new gateway API key in the dashboard.
2. Update client apps to use the new key.
3. Delete or deactivate the old key.

## Post-Deploy Checks

Run these checks after every deploy:

```bash
curl https://<your-domain>/health
curl https://<your-domain>/docs
```

Then sign in, create a gateway API key, and call:

```bash
curl -X POST https://<your-domain>/chat \
  -H "X-Api-Key: grg_..." \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Say hello","max_tokens":32}'
```

Do not paste provider API keys into the browser. Provider keys belong only in server-side environment variables.
