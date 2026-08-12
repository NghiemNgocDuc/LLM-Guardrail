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

## Nix Quickstart (Linux/macOS)

A reproducible dev shell is provided by [`flake.nix`](flake.nix) — versions
pinned to match CI and `docker-compose.yml` (Python 3.12, Node 22, Go
1.22.12, Rust stable, OPA 1.18.2, Postgres 16 / Redis 7 clients, maturin).
The first run records the nixpkgs pin in `flake.lock` — commit it:

```bash
nix develop                 # first run: creates flake.lock + .venv, installs Python deps
. .venv/bin/activate        # already active inside the shell
python -m pytest -q         # backend tests
npm ci && npm run dev       # frontend
```

> Windows: `nix develop` requires WSL2 or a Linux machine — the manual
> fallback below works everywhere else.

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

# Blocked requests that users later disputed (positive feedback or an admin
# always-allow override) — grouped by fired rule to spot likely false positives
curl -X GET "http://localhost:8080/analytics/false-positive-candidates?days=7&limit=50" \
  -H "Authorization: Bearer <access_token>"

# Org audit export (admins): paginated request logs with the owning user's
# email. Raw prompts, passwords, and key hashes are never exported.
curl -X GET "http://localhost:8080/org/export?days=30&page=1&page_size=100" \
  -H "Authorization: Bearer <access_token>"

# Rotate the HMAC secret used to sign guardrail webhooks (shown exactly once)
curl -X POST "http://localhost:8080/org/rotate-webhook-secret" \
  -H "Authorization: Bearer <access_token>"
```

Webhooks: when the org policy has a `webhook_secret` (set via the endpoint
above), every `guardrail_fired` webhook is signed with HMAC-SHA256 over
`"{timestamp}.{body}"` and delivered with:

```
X-Guardrail-Signature: v1,<hex digest>
X-Guardrail-Timestamp: <unix seconds>
```

Verify in the receiver before trusting the event; unsigned submissions are an
indication the sender isn't under your org's secret.

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

It prefers the compiled Go binary when present and falls back to Python:

```bash
cd cli/guardrail-scan && make build   # optional: install into ~/go/bin with: make install
```

The Go binary is a drop-in reimplementation of `scripts/scan_agent_skills.py`
(same flags, same output, same exit codes, same `.cursor/skill-guard-*.json`
files) with no runtime dependencies — see [cli/guardrail-scan/README.md](cli/guardrail-scan/README.md).
`make release` cross-compiles static binaries for macOS/Linux/Windows (amd64+arm64).

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
| `litellm` | provider keys (optional backend, `pip install litellm`) |
| `mock` | none; test-only backend |

### Failover

When a backend fails (timeout / 5xx), the gateway tries fallbacks in order:

1. per-org policy `compliance_rules.llm_fallbacks` (e.g. `["openai/gpt-4o"]`),
2. the global `LLM_FAILOVER_BACKENDS` list (comma-separated, e.g. `openai,gemini`).

Each backend is individually circuit-broken; `/health/breakers` reports per-backend state.

### Optional features

| Feature | How to enable |
| --- | --- |
| Response cache (exact-hash) | `RESPONSE_CACHE_ENABLED=true` **and** per-policy `output_rules.response_cache` |
| External output validators | Per-policy `output_rules.external_validators` (guardrails-ai-style: `ValidLength`, `RegexMatch`, `DenyList`, `AllowList`, `RequiredFields`, `CompetitorDetector`) |
| At-rest prompt encryption | Set `ENCRYPTION_KEY` (Fernet) — `full_prompt` audit rows are AES-GCM encrypted; admin replay decrypts on the fly |
| Webhook delivery tracking | `RATE_LIMIT_REDIS_URL` (Redis ring buffer, in-memory fallback) — see `GET /admin/webhook-deliveries` |
| SSE keepalive | Always on — `/chat/stream` sends `{"type":"ping"}` during long generations |

### guardrailctl (ops CLI)

```bash
python scripts/guardrailctl.py status         # adapters, breakers, feature flags
python scripts/guardrailctl.py cost-anomaly   # flag org daily token-spend spikes
```

### Tests

```bash
python -m pytest -q                        # full suite
GOLDEN_UPDATE=1 python -m pytest tests/test_golden.py -q   # regenerate golden verdicts
```

Golden verdict fixtures (`tests/golden/cases.json`) pin input/output guardrail outcomes; CI runs them in a dedicated job.

### Guardrail engine (Rust)

The regex checks in `guardrails/` run through a compiled Rust extension
(`guardrail_core`, a PyO3 module built with [maturin](https://www.maturin.rs)).
The `regex` crate guarantees linear-time matching, so pathological inputs that
could stall the Python `re` engine are safe. The extension is fail-open: any
import or runtime error falls back to the original pure-Python implementation,
so the app runs fine on machines without a Rust toolchain.

Select the engine with `GUARDRAIL_ENGINE` (default `rust`; the Docker images
build and install the extension automatically):

```env
GUARDRAIL_ENGINE=rust      # compiled extension when importable, else Python
# GUARDRAIL_ENGINE=python  # always use the Python implementation
```

Build and install locally:

```bash
pip install -r requirements-dev.txt
pip install maturin             # wheel builder (not in requirements-dev.txt)
maturin build --release --interpreter python --out wheels
pip install wheels/*.whl
cargo test --release                  # Rust unit tests (working-directory: guardrail_core)
```

Engine-parity tests run twice per module — once per engine — via the
`engine_mode` fixture (`tests/conftest.py`), and CI exercises both in the
`rust-engine-tests` job.

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
