# Security policy

## Credentials and configuration

Keep `.env`, provider credentials, raw gateway keys, database passwords, and
signing keys out of Git, screenshots, and shared logs. The tracked example
environments contain configuration names and empty values.

Production requires a strong `SECRET_KEY`, PostgreSQL, Redis, explicit allowed
origins, an HTTPS application URL, and credentials for the chosen hosted model
provider. Configure `REDIS_PASSWORD` for Compose and a separate `SECRET_KEY_BASE`
when running the Phoenix live feed. Provider keys belong on the API server;
applications authenticate with scoped gateway keys.

Local JWT sessions and Clerk RSA signatures use PyJWT with explicitly allowed
algorithms. The Clerk verification path accepts a configured PEM public key or
JWKS. Local sessions retain the configured signing key and expiry behavior.

## Guardrail boundaries

The gateway has several layers of credential detection and redaction:

- Input checks can reject detected credentials and environment-disclosure probes.
- Output checks detect credential leakage in model responses.
- Audit handling scrubs detected credentials before storing prompt previews and
  retained prompts; optional full-prompt storage supports Fernet encryption.
- Logging filters, error handling, and response middleware scrub detected values.
- Skill findings redact credentials and personal data before shortening excerpts.

These are heuristic controls, not a guarantee that every sensitive value will
be detected. Standard SSE streaming can deliver tokens before the final output
check. [Private mode](docs/PRIVATE_SELF_HOSTING.md) buffers model output until
checks pass, uses local inference, and omits raw blocked content from audits.
External agents must enforce skill scan decisions in their own loading flow.
See the [skill logic contract](docs/SKILL_LOGIC.md).

Rotate any credential exposed in source, logs, screenshots, chat, or a public
repository. A redacted preview does not revoke the original credential.

## Deployment and dependency checks

Use TLS at the public ingress. Keep database, Redis, model inference, gRPC, and
other internal service ports private. See [deployment](DEPLOYMENT.md) and
[hardening](docs/SECURITY_HARDENING.md).

Check dependencies after installation and whenever changing pinned versions:

```bash
npm audit --audit-level=high
python -m pip install pip-audit
python -m pip_audit -r requirements.txt
```

CI also runs dependency checks and the canonical committed-skill scanner.
An audit reports known advisories at the time it runs; passing does not prove
that the application has no vulnerabilities.

`python scripts/check_repository_secrets.py` checks tracked files for common
credential formats without printing their values. Intentional examples in
`scripts/secret-scan-allowlist.json` are approved by an exact normalized file
digest. Any edit invalidates the approval. Review all findings before updating
a digest; do not add real credentials to this allowlist.

## Reporting issues

Report security issues privately to the repository owner. Include the affected
version, reproduction steps, and impact. Do not publish credentials or exploit
details in a public issue.
