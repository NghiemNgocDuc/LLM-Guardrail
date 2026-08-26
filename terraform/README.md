# Terraform — Render deployment (Infrastructure as Code)

Terraform provisioning for the production topology documented in
[`DEPLOYMENT.md`](../DEPLOYMENT.md): a single fullstack web/API service on
Render, backed by Supabase Postgres and Upstash Redis.

```text
terraform/
├── main.tf                    # providers + module wiring + service environment
├── variables.tf               # every variable; secrets are sensitive = true
├── outputs.tf
├── backend.tf                 # Terraform Cloud remote state (org not committed)
├── terraform.tfvars.example   # copy to terraform.tfvars (gitignored)
└── modules/
    ├── database/              # Supabase Postgres — external (no official provider)
    ├── cache/                 # Upstash Redis — provisioned here
    └── api/                   # Render web service (Dockerfile.fullstack)
```

## How the services map

`docker-compose.yml` runs four images; the documented hosted shape
(`render.yaml`, `fly.toml`, DEPLOYMENT.md "Recommended shape") runs one
fullstack container. The mapping:

| docker-compose | DEPLOYMENT.md | Terraform | Notes |
|---|---|---|---|
| `db` (postgres:16) | Supabase Postgres | `modules/database` | **External.** No official Supabase provider exists, so the project is created in the Supabase dashboard (DEPLOYMENT.md §Supabase Postgres) and its pooler URL is passed in as the sensitive `supabase_database_url` variable. The module validates the `postgresql+asyncpg://` scheme the app requires. |
| `redis` (redis:7) | Upstash Redis | `modules/cache` | **Provisioned.** Official `upstash/upstash` provider creates the database; the module builds `RATE_LIMIT_REDIS_URL` in the documented `rediss://` form. |
| `api` (FastAPI :8000) | Render web service | `modules/api` | One `render_web_service` (runtime `docker`, `Dockerfile.fullstack`), which also serves the built frontend — it plays the compose `api` **and** `web` roles (SECURITY.md: the `web`/fullstack image is the public entrypoint). |
| `web` (nginx, public) | (part of fullstack) |  same service | No separate static site is provisioned — DEPLOYMENT.md's "separate frontend/backend" shape is the documented alternative and stays manual (see "Not covered"). |

## Environment variables

Every key wired into the service is an `app/config.py` `Settings` field name
(or a `Dockerfile.fullstack` ARG) — nothing invented. The full set mirrors
`render.yaml`'s envVars plus the DEPLOYMENT.md SMTP and demo-mode sections:

- **Always set:** `APP_ENV=production`, `DEBUG=false`, `LOG_LEVEL`, `PORT=8000`,
  `ALLOWED_ORIGINS`, `PUBLIC_APP_URL` (both computed from the service URL),
  `DATABASE_URL` and/or `POSTGRES_*`, `RATE_LIMIT_REDIS_URL`, `SECRET_KEY`,
  `DEFAULT_LLM_BACKEND`, `DEFAULT_MODEL`, `BILLING_ENABLED`, `FREE_SIGNUP_TOKENS`.
- **Set only when a non-empty variable is supplied:** provider API keys
  (`GROQ_*`, `OPENAI_*`, `ANTHROPIC_*`, `GEMINI_*`), `PINECONE_*`, `CLERK_*`,
  `STRIPE_*`, `BILLING_UNLIMITED_EMAILS`, `SMTP_*` (+ `REQUIRE_EMAIL_VERIFICATION`),
  `LLM_FAILOVER_BACKENDS`, and the `DEMO_*` block when `demo_mode = true`.

## Providers

| Provider | Source | Maturity |
|---|---|---|
| Render | `render-oss/render` | Official — maintained by Render (`tier: partner` on the registry). v1.9.x, framework-based. |
| Upstash | `upstash/upstash` | Official — maintained by Upstash. v2.x. |

`terraform init` pins exact versions in the committed `.terraform.lock.hcl`.

## Remote state — Terraform Cloud

State lives in Terraform Cloud (`backend "remote"`, workspace
`llm-guardrails-production`), chosen because this project has no other cloud
storage to host an S3-compatible bucket. Benefits: encrypted state, state
locking, free tier, and a natural home for CI-driven `terraform plan` later.

The organization is intentionally not committed:

```bash
terraform login                       # one-time TFC token
terraform init -backend-config="organization=YOUR-ORG"
```

Local `terraform validate` / CI use `terraform init -backend=false` and need no
token (they only download providers).

## Apply from scratch

Prerequisites:

- Terraform ≥ 1.3 (CI pins 1.9.x; `terraform fmt -check` and `terraform validate` run on every PR touching `terraform/`)
- Render account + API key (`render_api_key`) + owner/team ID (`render_owner_id`, from the dashboard "Owner ID" setting)
- Upstash account + API key (`upstash_api_key`, `upstash_email`)
- A Supabase project with its pooler connection string (DEPLOYMENT.md §Supabase Postgres)
- A Terraform Cloud account/organization (or edit `backend.tf` to point elsewhere)

Steps:

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars    # fill in real values (never commit)

# SECRET_KEY (DEPLOYMENT.md):
python -c "import secrets; print(secrets.token_urlsafe(48))"

terraform init -backend-config="organization=YOUR-ORG"
terraform plan -out=tfplan
terraform apply tfplan
```

What you get:

- `llm-guardrails` Render web service (Docker build of `Dockerfile.fullstack`,
  health check `/health`, auto-deploy on `main`, plan `starter` by default)
  — public at `https://<service_name>.onrender.com`
- `llm-guardrails-redis` Upstash Redis database (TLS), wired as
  `RATE_LIMIT_REDIS_URL` (`rediss://`)
- Supabase connection wired as `DATABASE_URL` / `POSTGRES_*` (created manually)

Then run the DEPLOYMENT.md **Post-Deploy Checks**:

```bash
curl https://<service_name>.onrender.com/health
curl https://<service_name>.onrender.com/docs
```

Verify migrations ran (the container's entrypoint applies them), then sign in,
create a gateway API key, and call `/chat` per DEPLOYMENT.md.

## What this does NOT cover (yet)

Deliberately manual, matching what DEPLOYMENT.md leaves manual:

- **Supabase project creation** — no official provider; pooler URL is an input variable. Rotate its password per DEPLOYMENT.md §Key Rotation.
- **VITE_* Docker build args** (`VITE_API_BASE_URL`, `VITE_CLERK_PUBLISHABLE_KEY`, `VITE_POSTHOG_API_KEY`, `VITE_POSTHOG_HOST`, `VITE_SENTRY_DSN`) — the official Render provider cannot pass Docker build args (verified against v1.9.1 schema: `runtime_source.docker` exposes `dockerfile_path`/`context` only). Set them in the Render dashboard under the service's build settings.
- **Custom domains / TLS** — the default `*.onrender.com` domain is used; attaching a custom domain stays a Render dashboard step (the provider supports `custom_domains` if you want to add it later).
- **Stripe webhook endpoints** — the webhook URL is `https://<service>/stripe/webhook`; registering it in the Stripe dashboard is manual.
- **Koyeb / Fly.io / VPS+Compose** — the alternative DEPLOYMENT.md targets stay manual; this configuration targets Render (the documented recommended shape). `fly.toml` and `docker-compose.yml` remain untouched.
- **Frontend split deploy** (DEPLOYMENT.md "separate frontend/backend" shape) — not provisioned; `render_static_site` exists in the provider if you want to add it.

## Updating

Change a variable, then `terraform plan` → `terraform apply`. Secrets are
redacted in plan/apply output because every secret variable is declared
`sensitive = true`. Provider keys are **not** stored by Terraform — they exist
only in `.tfvars`/`TF_VAR_*` and are sent to Render/Upstash, which store them
encrypted server-side (same trust boundary as setting them in the dashboards).

Rotate keys using DEPLOYMENT.md §Key Rotation, then re-apply with the new
values.
