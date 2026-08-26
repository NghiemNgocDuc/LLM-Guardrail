# Security Policy

## Secrets

Never commit `.env` or provider API keys. The repository includes `.env.example` only.

Required production secrets:

- `SECRET_KEY`
- `POSTGRES_PASSWORD`
- `GROQ_API_KEY` or the key for your selected LLM backend

**Groq / provider key guarantee — no leakage path:**

Provider keys (`GROQ_API_KEY=gsk_…`, `OPENAI_API_KEY=sk-…`, `ANTHROPIC_API_KEY=sk-ant-…`) are
*server-only* and never leave the gateway:

1. **Not in the frontend** — No endpoint returns `GROQ_API_KEY` (grep `app/routers` — zero hits).
   Billing `/config` exposes only `STRIPE_PUBLISHABLE_KEY`. Frontend `src/utils/api.ts` validates
   `grg_`-only gateway keys and rejects `gsk_`/`sk-` pasted into the browser with an explicit
   warning (“Provider keys must stay server-side as env”).
2. **Input blocked** — `guardrails/input.py` blocks any prompt containing `gsk_…`/`sk-…`/`AKIA…`
   and blocks env-exfiltration probes (`what is GROQ_API_KEY?`, `print(os.environ)`, `process.env`).
3. **Output blocked** — `guardrails/output.py` blocks any LLM response containing a provider key
   (regex + verbatim `settings.GROQ_API_KEY` match).
4. **Storage scrubbed** — `app/routers/chat.py:_log_request` scrubs `prompt_preview`, `input_block_reason`,
   `output_block_reason` and `full_prompt` (pre-encrypt) via `scrub_text`.
5. **Logs scrubbed** — `main.py:SecretScrubFilter` + `JSONFormatter` and
   `app/middleware/request_logging.py` scrub every log line; `Sentry before_send` scrubs
   exceptions/breadcrumbs.
6. **Egress scrubbed** — `app/middleware/secret_scrub.py:SecretScrubMiddleware` is the last line of
   defense: any JSON response that somehow contains `gsk_…`/`grg_…` is redacted to
   `[REDACTED:SECRET]` before it hits the wire.
7. **Central redaction** — `app/utils/secret_redaction.py` is the single source of truth
   (regexes + verbatim configured key). `contains_secret` / `scrub_text` used everywhere.

Rotate any secret that has been pasted into logs, screenshots, chat, or a public repository.

## Deployment

Use the Docker `web` service as the public entrypoint. Keep `api`, `db`, and `redis` private.

Production startup fails if required secrets, Postgres, Redis, or the configured Groq key are missing.

## Reporting Issues

Report security issues privately to the repository owner. Do not open public issues with exploit details or secrets.
