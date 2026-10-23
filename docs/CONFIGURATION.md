# Configuration and operations

[Back to the project overview](../README.md). Run commands from the repository root.

Set `DEFAULT_LLM_BACKEND` globally or `llm_backend` per organization policy.

| Backend value | Required env vars |
| --- | --- |
| `groq` | `GROQ_API_KEY` |
| `openai` | `OPENAI_API_KEY` |
| `anthropic` | `ANTHROPIC_API_KEY` |
| `gemini` | `GEMINI_API_KEY` |
| `xai` / `grok` | `XAI_API_KEY` (or `GROK_API_KEY`) |
| `ollama` | `OLLAMA_BASE_URL` |
| `openai_compatible` | `OPENAI_COMPATIBLE_BASE_URL`, `OPENAI_COMPATIBLE_API_KEY` |
| `litellm` | provider keys (optional backend, `pip install litellm`) |
| `mock` | none; test-only backend |

## Failover

When a backend fails (timeout / 5xx), the gateway tries fallbacks in order:

1. per-org policy `compliance_rules.llm_fallbacks` (e.g. `["openai/gpt-4o"]`),
2. the global `LLM_FAILOVER_BACKENDS` list (comma-separated, e.g. `openai,gemini`).

Each backend is individually circuit-broken; `/health/breakers` reports per-backend state.

## Optional features

| Feature | How to enable |
| --- | --- |
| Response cache (exact-hash) | `RESPONSE_CACHE_ENABLED=true` **and** per-policy `output_rules.response_cache` |
| External output validators | Per-policy `output_rules.external_validators` (guardrails-ai-style: `ValidLength`, `RegexMatch`, `DenyList`, `AllowList`, `RequiredFields`, `CompetitorDetector`) |
| At-rest prompt encryption | Set `ENCRYPTION_KEY` (Fernet) — full prompts are encrypted before storage; admin replay decrypts on the fly |
| Webhook delivery tracking | `RATE_LIMIT_REDIS_URL` (Redis ring buffer, in-memory fallback) — see `GET /admin/webhook-deliveries` |
| SSE keepalive | Always on — `/chat/stream` sends `{"type":"ping"}` during long generations |

## guardrailctl (ops CLI)

```bash
python scripts/guardrailctl.py status         # adapters, breakers, feature flags
python scripts/guardrailctl.py cost-anomaly   # flag org daily token-spend spikes
```

## Tests

```bash
python -m pytest -q                        # full suite
python -m pytest tests/test_uptimerobot.py -q  # health and monitor setup
GOLDEN_UPDATE=1 python -m pytest tests/test_golden.py -q   # regenerate golden verdicts
npm run typecheck
npm run build
```

The frontend uses a shared design system across every view, with light/dark
themes, responsive navigation, keyboard-friendly dialogs, and reduced-motion
support. The login preview keeps its word-by-word LLM output. See the
[frontend design notes](FRONTEND_DESIGN.md) for components and research.

Frontend browser checks use isolated API fixtures to verify authentication,
every workspace view, and key, policy, skill, memory, account, team, billing,
analytics, log, health, export, and provenance workflows:

```bash
npx playwright install chromium
npm run test:frontend
```

They run at desktop and 375px mobile widths, with automated accessibility checks
in both themes. Tests never make real purchases or modify live accounts.
On Windows with Edge already
installed, set `$env:PW_CHANNEL="msedge"` in PowerShell to use it instead of
downloading Chromium. Preview screenshots and failure traces are written to
the ignored `test-results/` directory.

Golden verdict fixtures (`tests/golden/cases.json`) pin input/output guardrail outcomes; CI runs them in a dedicated job.

## Guardrail engine (Rust)

The regex checks in `guardrails/` run through a compiled Rust extension
(`guardrail_core`, a PyO3 module built with [maturin](https://www.maturin.rs)).
The `regex` crate guarantees linear-time matching, so pathological inputs that
could stall the Python `re` engine are safe. An extension import or runtime
error falls back to the pure-Python implementation,
so the app runs fine on machines without a Rust toolchain.

Select the engine with `GUARDRAIL_ENGINE` (default `rust`). The current Docker
images do not build the extension; they use the Python fallback unless you add
the compiled extension to the image:

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
