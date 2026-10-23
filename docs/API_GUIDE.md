# API and agent integrations

[Back to the project overview](../README.md). Run commands from the repository root.

Sign up and create an organization (complete email verification if configured):

```bash
curl -X POST http://localhost:8080/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"<choose-a-strong-password>","full_name":"Alex Example","org_name":"Acme"}'
```

Log in:

```bash
curl -X POST http://localhost:8080/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"<choose-a-strong-password>"}'
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

Returns `safe`, `risk_score`, and per-line `findings` (secrets, PII, DB URLs,
environment exposure, internal paths, and destructive shell/SQL commands).
`safe` describes the raw scan. Use `blocked` and `agent_may_continue` for the
decision after explicit server approvals; `runtime_enforced` is `false`, so the
integrating agent must honor that decision before loading the content.

### Managed skills and review

In **Skill Guard**, workspace admins can create and edit managed drafts. Saving
a draft does not approve it for agent use: every download and live fetch runs a
delivery scan, including authored metadata in wrapped Markdown. Blocked delivery
returns HTTP 422 and a review-queue ID without returning the skill document.

The review queue offers **Allow once**, **Always allow**, and **Keep blocked**.
Hosted approvals belong to the reviewing user and workspace and match the exact
content and findings. Delivery approvals also bind the revision, metadata,
download mode, and raw/wrapped choice. Allow once is consumed by a matching
scan or delivery attempt; changed content cannot reuse the previous approval.
Client-supplied overrides and repository-local CLI override files cannot bypass
hosted scans.

`GET /skills/live/{slug}` requires a signed-in Bearer session or a gateway key
with `skills:read`; it only reads that authenticated workspace. Send credentials
in headers. Downloaded Markdown contains installation guidance and a live URL,
but the consumer must fetch, install, and select versions explicitly.

See [agent and skill logic](SKILL_LOGIC.md) for the API contract,
concurrency rules, integrity headers, and integration limits.

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

Install once per clone to check skill content before pushing to GitHub:

```bash
./scripts/install-git-hooks.sh
```

Windows:

```powershell
.\scripts\install-git-hooks.ps1
```

The **pre-push** hook reads committed Markdown under `.cursor/skills/` from the
outgoing commit trees. Local edits cannot hide unsafe committed content, and a
later revert cannot hide an unsafe intermediate version. Identical blobs are
checked once. New branches conservatively check their reachable skill history;
missing Git objects or unreadable skills block the push until they can be checked.

The hook requires the canonical Python scanner, `scripts/scan_agent_skills.py`.
It can use the compatible Rust acceleration path when installed. A prebuilt Go
binary or `SKILL_GUARD_BIN` does not replace the canonical pre-push check.

The standalone Go companion has no Python runtime dependency. Its independent
implementation can differ from the canonical scanner; use Python for the current
checks. Build instructions are in [cli/guardrail-scan/README.md](../cli/guardrail-scan/README.md).

### GitHub (pull requests and pushes)

[`.github/workflows/scan-agent-skills.yml`](../.github/workflows/scan-agent-skills.yml) runs on:

- Every pull request to `main`
- Every **push** that changes `.cursor/skills/**` (any branch) — backup if someone skips the local hook

The CI skill check also uses the canonical Python scanner.

Scan manually anytime:

```bash
python scripts/scan_agent_skills.py
python scripts/scan_agent_skills.py --git-range origin/main..HEAD
```

See [.githooks/README.md](../.githooks/README.md) for details.

Client examples:

- [Python](../examples/python_client.py)
- [JavaScript](../examples/javascript_client.mjs)

SDK helpers are documented in [SDK.md](../SDK.md).

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

Remote `chat` calls use the same workspace policy, billing, budgets, limits,
and audit path as `POST /chat`; client policy overrides are rejected.
`scan_skill` and `scan_repo` require `skills:read`. Explicit empty key scopes
grant neither chat nor skill access; legacy null scopes retain chat access.
Authenticated MCP utility tools without a required scope remain available.
Local stdio mode is a separate integration and does not authenticate a hosted
workspace. See [agent and skill logic](SKILL_LOGIC.md).
