---
name: example-safe
description: Reference skill used by CI to verify the Skill Guard scanner runs on pull requests.
---

# Example safe skill

Use this folder as a template for real project skills.

## Rules

- Never embed API keys, database URLs, or production hostnames in skill text.
- Reference environment variables by name only (e.g. `DATABASE_URL`), not values.
- Do not paste customer PII into examples.
- Do not embed copy-pasteable destructive shell or SQL (recursive root deletes, DROP/TRUNCATE, pipe-to-shell installs, force git push).
  Describe safe alternatives in plain language instead of literal command examples.

## Workflow

1. Draft the skill locally.
2. Run `python scripts/scan_agent_skills.py` before opening a PR.
3. Fix any findings reported under `.cursor/skills/`.
