# AI Guardrails Platform

Production-ready Docker stack for a multi-tenant **LLM safety gateway** and **agent skill leak scanner** with:

- FastAPI API gateway
- React dashboard
- PostgreSQL audit log
- Redis-backed rate limiting
- Per-organization guardrail policy
- Groq/OpenAI-compatible LLM backend support
- Agent skill / instruction scanner (`POST /skills/scan`) for Cursor skills, MCP rules, and system prompts

**Live demo:** [https://llm-guardrail.onrender.com](https://llm-guardrail.onrender.com)

## Architecture

```text
Client app or dashboard
        |
        v
FastAPI Guardrail Gateway
  | auth + API keys
  | rate limits + demo limits
  | input guardrails
  | provider routing
  | output guardrails
        |
        v
Groq / OpenAI / Anthropic / Gemini / Ollama

PostgreSQL stores users, policies, API keys, and audit logs.
Redis stores shared rate-limit windows.
```

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

For hosted deployment with Supabase, Upstash, Render, or Koyeb, see [DEPLOYMENT.md](DEPLOYMENT.md).

Single-container cloud deploys can use `Dockerfile.fullstack`, which builds the React dashboard and serves it from FastAPI on the same port.

Live demo checklist: [LIVE_DEMO.md](LIVE_DEMO.md)
Operations and backup guide: [OPERATIONS.md](OPERATIONS.md)
Screenshot guide: [docs/SCREENSHOTS.md](docs/SCREENSHOTS.md)

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

Scan an agent skill or instruction file before publishing (dashboard: **Skill Guard**):

```bash
curl -X POST http://localhost:8080/skills/scan \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"content":"---\nname: my-skill\n---\nDo not embed secrets here.","filename":"SKILL.md"}'
```

Returns `safe`, `risk_score`, and per-line `findings` (secrets, PII, DB URLs, env assignments, internal paths, destructive shell/SQL commands).

### Dashboard utilities

Policy change previews, replay, and blocked-rule analytics (all dashboard-authenticated, all read-only):

```bash
# Compare two policy blobs field by field (no DB write) — admin policy tooling
curl -X POST http://localhost:8080/policy/diff \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"policy_a": {"input_rules": {"block_jailbreak": true}}, "policy_b": {"input_rules": {"block_jailbreak": false}}}'

# Dry-run a stored request against the CURRENT org policy (no LLM call, no tokens deducted)
curl -X POST http://localhost:8080/admin/replay/<request_id> \
  -H "Authorization: Bearer <access_token>"

# Most frequent blocked-request rules in the last 7 days, with latest occurrence each
curl -X GET "http://localhost:8080/analytics/top-blocked-reasons?days=7&limit=10" \
  -H "Authorization: Bearer <access_token>"
```

### Before `git push` (local hook)

Install once per clone so sensitive or destructive skill content cannot be pushed to GitHub:

```bash
./scripts/install-git-hooks.sh
```

Windows:

```powershell
.\scripts\install-git-hooks.ps1
```

The **pre-push** hook scans only `.cursor/skills/` files in the commits you are pushing. If the push does not touch that folder, it skips instantly.

### GitHub (pull requests and pushes)

[`.github/workflows/scan-agent-skills.yml`](.github/workflows/scan-agent-skills.yml) runs on:

- Every pull request to `main`
- Every **push** that changes `.cursor/skills/**` (any branch) — backup if someone skips the local hook

Scan manually anytime:

```bash
python scripts/scan_agent_skills.py
python scripts/scan_agent_skills.py --git-range origin/main..HEAD
```

See [.githooks/README.md](.githooks/README.md) for details.

Client examples:

- [Python](examples/python_client.py)
- [JavaScript](examples/javascript_client.mjs)

SDK helpers are documented in [SDK.md](SDK.md).

### MCP server tools

The MCP server (`GET /mcp/sse`, JSON-RPC over SSE, authenticated with a `grg_` gateway API key) exposes 8 tools:

| Tool | Purpose |
| --- | --- |
| `scan_skill` | Scan one skill / instruction file for secrets, PII, and destructive commands |
| `scan_repo` | Scan a batch of files in one call (JSON array of `{filename, content}`), returns per-file results plus an aggregate summary |
| `check_input` | Check a prompt against input guardrails (secrets, PII, injection, jailbreak) |
| `check_output` | Check an LLM response against output guardrails (leaks, toxicity, topics, schema) |
| `chat` | Route a prompt through the full guardrail gateway (requires a key with the `chat` scope) |
| `redact_pii` | Redact PII from text with reversible placeholders |
| `get_default_policy` | Return the default guardrail policy configuration |
| `explain_policy` | Explain what a JSON guardrail policy actually enforces (no LLM call) |

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

## Token billing (publish for paying users)

Gateway `/chat` usage is metered in **tokens** (LLM input + output). Each new user gets a free wallet (`FREE_SIGNUP_TOKENS`, default 10,000). When balance is low, the API returns **402** with a link to buy more.

| Plan | Tokens | Price (USD) |
| --- | --- | --- |
| Starter | 500K | $9 |
| Growth | 2M | $29 |
| Scale | 10M | $99 |
| Enterprise | 50M | $399 |

Dashboard: **Billing** in the sidebar — balance, buy packs, purchase history.

### Stripe setup

1. Create a [Stripe](https://stripe.com) account and add to `.env`:

```env
BILLING_ENABLED=true
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PUBLISHABLE_KEY=pk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
```

2. Stripe Dashboard → **Webhooks** → add endpoint `https://YOUR_DOMAIN/billing/webhook` with event `checkout.session.completed`.

3. Run migration: `alembic upgrade head` (adds `token_wallets` and `token_purchases`).

4. Optional: create Products/Prices in Stripe and set `STRIPE_PRICE_STARTER`, `STRIPE_PRICE_GROWTH`, etc.

**Development:** without Stripe keys, **Buy tokens** still credits the pack instantly for local testing.

Disable metering entirely: `BILLING_ENABLED=false`.

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
DEMO_MAX_OUTPUT_TOKENS=2048
```

Demo mode adds stricter per-API-key and per-IP limits on top of organization limits, rejects oversized prompts, and rejects requests asking for too many output tokens before calling the LLM. To run a fixed shared demo account, create the account yourself and set:

```env
DEMO_DISABLE_SIGNUPS=true
```
