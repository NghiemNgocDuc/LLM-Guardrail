# OSS Replacements — Drop All External APIs

> Checked `.env.example` + `docker-compose.yml` + `requirements.txt` + `app/config.py`. 14 env vars require external SaaS — every one has a 1-line OSS/self-host swap below.

| Env var(s) | Current SaaS (needs API key) | Purpose | OSS/self-host clone — drop-in | How to switch |
|---|---|---|---|---|
| `GROQ_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `OPENAI_COMPATIBLE_API_KEY` + `*_BASE_URL` | Groq / OpenAI / Anthropic / Gemini | LLM inference | **Ollama + vLLM + LiteLLM** (all already vendored) — `OLLAMA_BASE_URL=http://ollama:11434` `DEFAULT_LLM_BACKEND=ollama` `DEFAULT_MODEL=phi3` or `llama3.1:8b` — zero API. LiteLLM’s `litellm.py` already routes `ollama/` prefix. For prod keep `LLM_FAILOVER_BACKENDS=ollama` | Remove 5 keys, set `DEFAULT_LLM_BACKEND=ollama`, run `ollama` container (see below) |
| `PINECONE_API_KEY`, `PINECONE_ENVIRONMENT`, `PINECONE_INDEX_NAME` | Pinecone (vector DB) | Semantic guard + conversation/memory recall | **pgvector** (Postgres extension — *zero new container*) **or** **Qdrant** (`qdrant/qdrant:latest`). `app/services/vectorstore.py` already abstracts `_index()` — swap to `pgvector` table `memories_embedding VECTOR(384)` or Qdrant `memories` collection. Both speak cosine 384. | `PINECONE_API_KEY=` (empty → vectorstore no-ops), `pip install pgvector`, `CREATE EXTENSION vector`, set `VECTOR_BACKEND=pgvector` |
| `CLERK_SECRET_KEY`, `CLERK_JWKS_URL`, `CLERK_JWT_KEY`, `CLERK_WEBHOOK_SECRET` | Clerk | Auth (signup/login/JWT) | **Authentik** / **Supertokens** / **Ory Kratos + Keto** / **Supabase Auth** (all OSS, JWT+JWKS, HMAC webhooks). Or keep local fallback: `app/deps.py` already supports local `SECRET_KEY` JWT (`create_access_token`) + `BILLING_UNLIMITED_EMAILS` — just set `CLERK_*=` empty and rely on `SECRET_KEY` 32-char, `REQUIRE_EMAIL_VERIFICATION=false` for intranet. Easiest: **Keycloak** (Docker `quay.io/keycloak/keycloak`) — swap `CLERK_JWKS_URL` → `KEYCLOAK_JWKS_URL` | Unset Clerk vars, set `SECRET_KEY=$(openssl rand -hex 32)` or deploy Keycloak |
| `STRIPE_*` (4 vars + price IDs) | Stripe | Billing/checkout | **Lago** (OSS billing, `getlago/lago`), **Kill Bill**, or trivial: `BILLING_ENABLED=false` + `FREE_SIGNUP_TOKENS=100000` — wallet `token_wallet.py` works without Stripe (dev path `stripe_configured()==False` instantly credits). For OSS SaaS, run Lago (`lago` container) or keep wallet-only | `STRIPE_SECRET_KEY=` empty → dev instant-credit, or point to Lago `LAGO_API_URL` |
| `POSTHOG_API_KEY`, `POSTHOG_HOST`, `PRODUCTBRIDGE_API_KEY` | PostHog + ProductBridge | Analytics, feature flags, NPS | **PostHog self-hosted** (`posthog/posthog:latest`) — *same API, same SDK* — just `POSTHOG_HOST=http://posthog:8001`. Or **Plausible** / **Matomo**. `posthog` pip dep stays, only host changes | `POSTHOG_HOST=http://posthog:3000` keep same `POSTHOG_API_KEY` (self-host project key) |
| `SENTRY_DSN` | Sentry SaaS | Error tracking | **GlitchTip** (`glitchtip/glitchtip`) or **self-hosted Sentry** (`getsentry/self-hosted`) or **SigNoz** — wire-compatible DSN, only `SENTRY_DSN=http://glitchtip:8080/...` changes. Or `SENTRY_DSN=` empty → no-op (already `if settings.SENTRY_DSN:` guard) | `SENTRY_DSN=http://glitchtip:9000/1` or blank |
| `SMTP_*`, `RESEND_API_KEY`, `RESEND_FROM` | SMTP / Resend | Transactional email (invite, reset) | **Postal** (`postalserver/postal`) / **Mailpit** (dev) / **Listmonk** — `SMTP_HOST=postal`, `SMTP_PORT=25`. `app/services/email.py` already abstracts Resend→SMTP fallback | `SMTP_HOST=postal` + `SMTP_FROM=noreply@local` |
| `RATE_LIMIT_REDIS_URL` (optional) | Upstash Redis SaaS | Rate limit, cache, bans | Already self-hosted Redis in `docker-compose.yml` (`redis:7-alpine`) — `RATE_LIMIT_REDIS_URL=redis://:pass@redis:6379/0` — no change needed |
| `SECRET_KEY`, `DATABASE_URL`, `OPA_URL` | — | Secrets, DB, policy engine | Already OSS: `SECRET_KEY` local, `postgres:16-alpine`, `openpolicyagent/opa:1.18.2` — keep |

### Zero-API `.env` (copy-paste)

```ini
APP_ENV=production
DATABASE_URL=postgresql+asyncpg://postgres:strongpass@db:5432/guardrails
SECRET_KEY= # 32+ chars: openssl rand -hex 32
POSTGRES_PASSWORD=strongpass
DEFAULT_LLM_BACKEND=ollama
OLLAMA_BASE_URL=http://ollama:11434
DEFAULT_MODEL=phi3
# vector — pgvector, no external key
PINECONE_API_KEY=
BILLING_ENABLED=true
FREE_SIGNUP_TOKENS=100000
# auth — local JWT, no Clerk
CLERK_SECRET_KEY=
# analytics self-hosted
POSTHOG_HOST=http://posthog:3000
POSTHOG_API_KEY=phc_selfhost_xxx
SENTRY_DSN=
RATE_LIMIT_REDIS_URL=redis://:pass@redis:6379/0
OPA_URL=http://opa:8181
VECTOR_BACKEND=pgvector
```

### Minimal `docker-compose.override.yml` to kill all SaaS

```yaml
services:
  ollama:
    image: ollama/ollama:latest
    volumes: [ollama:/root/.ollama]
    ports: ["11434:11434"]
  qdrant: # or omit and use pgvector
    image: qdrant/qdrant:latest
    volumes: [qdrant:/qdrant/storage]
  posthog:
    image: posthog/posthog:latest
  glitchtip:
    image: glitchtip/glitchtip:latest
  keycloak:
    image: quay.io/keycloak/keycloak:latest
    environment:
      KEYCLOAK_ADMIN: admin
      KEYCLOAK_ADMIN_PASSWORD: admin
volumes: { ollama:, qdrant: }
```

All app code stays — only env changes. `requirements.txt` already lists no hard `pinecone`/`clerk-sdk` pin; the 4 vendors are soft-imported (`try: import pinecone`).

> After swap, `POSTHOG_API_KEY`, `SENTRY_DSN`, `GROQ_API_KEY`, `OPENAI_API_KEY`, `CLERK_*`, `STRIPE_*`, `PINECONE_*` can all be blank and the gateway boots (`APP_ENV=production` gate only checks `SECRET_KEY` + `POSTGRES` + `REDIS`).
