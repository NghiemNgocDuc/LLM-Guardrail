# Security Policy

## Secrets

Never commit `.env` or provider API keys. The repository includes `.env.example` only.

Required production secrets:

- `SECRET_KEY`
- `POSTGRES_PASSWORD`
- `GROQ_API_KEY` or the key for your selected LLM backend

Rotate any secret that has been pasted into logs, screenshots, chat, or a public repository.

## Deployment

Use the Docker `web` service as the public entrypoint. Keep `api`, `db`, and `redis` private.

Production startup fails if required secrets, Postgres, Redis, or the configured Groq key are missing.

## Reporting Issues

Report security issues privately to the repository owner. Do not open public issues with exploit details or secrets.
