# LLM Guardrails Gateway

Production-ready Docker stack for a multi-tenant LLM safety gateway with:

- FastAPI API gateway
- React dashboard
- PostgreSQL audit log
- Redis-backed rate limiting
- Per-organization guardrail policy
- Groq/OpenAI-compatible LLM backend support

## Docker Quickstart

Create `.env` from the example and fill in real secrets:

```bash
cp .env.example .env
```

Required production values:

```env
SECRET_KEY=<long-random-secret>
GROQ_API_KEY=<your-groq-key>
POSTGRES_PASSWORD=<strong-db-password>
```

Start the stack:

```bash
docker compose up -d --build
```

Open:

- Dashboard: http://localhost:8080
- API docs: http://localhost:8080/docs
- Health: http://localhost:8080/health

## Services

| Service | Purpose |
| --- | --- |
| `web` | Nginx static frontend and API reverse proxy |
| `api` | FastAPI gateway; runs Alembic migrations on startup |
| `db` | PostgreSQL 16 |
| `redis` | Shared rate-limit store for API workers |

Scale API workers:

```bash
docker compose up -d --scale api=3
```

The public entrypoint is `web` on port `8080`. Keep `api`, `db`, and `redis` private.

## API Flow

Sign up and create an organization:

```bash
curl -X POST http://localhost:8080/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"you@co.com","password":"secret123","full_name":"Duc","org_name":"Acme"}'
```

Log in:

```bash
curl -X POST http://localhost:8080/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"you@co.com","password":"secret123"}'
```

Create a gateway API key:

```bash
curl -X POST http://localhost:8080/api-keys \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"name":"my-app-key"}'
```

Call the gateway:

```bash
curl -X POST http://localhost:8080/chat \
  -H "X-Api-Key: grg_..." \
  -H "Content-Type: application/json" \
  -d '{"prompt":"What is the capital of France?"}'
```

## Configuration

Set `DEFAULT_LLM_BACKEND` globally or `llm_backend` per organization policy.

| Backend value | Required env vars |
| --- | --- |
| `groq` | `GROQ_API_KEY` |
| `openai` | `OPENAI_API_KEY` |
| `anthropic` | `ANTHROPIC_API_KEY` |
| `gemini` | `GEMINI_API_KEY` |
| `ollama` | `OLLAMA_BASE_URL` |
| `openai_compatible` | `OPENAI_COMPATIBLE_BASE_URL`, `OPENAI_COMPATIBLE_API_KEY` |
| `mock` | none; test-only backend |

Groq default base URL:

```env
GROQ_BASE_URL=https://api.groq.com/openai/v1
```

## Migrations

The API container runs migrations automatically on startup:

```bash
alembic upgrade head
```

For model changes, generate a migration locally:

```bash
alembic revision --autogenerate -m "describe change"
```

## Production Notes

- Rotate any API keys that were exposed during development.
- Use strong `SECRET_KEY` and `POSTGRES_PASSWORD` values.
- Put TLS in front of `web` for public deployment.
- Keep `.env` out of source control.
- Use `docker compose logs -f api web` for operational debugging.

## Public Demo Mode

Enable demo mode when hosting a public link that uses your provider quota:

```env
DEMO_MODE=true
DEMO_RATE_LIMIT_RPM=5
DEMO_RATE_LIMIT_RPD=25
DEMO_IP_RATE_LIMIT_RPM=20
DEMO_IP_RATE_LIMIT_RPD=100
DEMO_MAX_PROMPT_CHARS=2000
DEMO_MAX_OUTPUT_TOKENS=256
```

Demo mode adds stricter per-API-key and per-IP limits on top of organization limits, rejects oversized prompts, and rejects requests asking for too many output tokens before calling the LLM. To run a fixed shared demo account, create the account yourself and set:

```env
DEMO_DISABLE_SIGNUPS=true
```
