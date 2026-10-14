# Agent and skill logic

The hosted API enforces access to managed skill documents and stores review
decisions. An external agent must integrate the scan decision into its own
loading and execution flow.

## Authentication and workspace access

Dashboard skill endpoints use a signed-in session and its current workspace.
Managed skill writes require a workspace admin; members can read, scan, download,
and review their own rejections. The live endpoint
`GET /skills/live/{slug}` accepts a Bearer session or a gateway API key with
`skills:read`, sent through `X-Api-Key` or Bearer authorization. It requires
authentication for both wrapped and `?raw=true` responses. Missing skills return
404 within the authenticated workspace; there is no public or other-workspace
fallback.

Gateway keys must be active, unexpired, and owned by an active user who still
belongs to the key's workspace. A key remains bound to its workspace when its
owner switches workspaces. Send credentials in headers rather than embedding
them in downloaded Markdown or URLs.

| Action | Required gateway key scope |
| --- | --- |
| Live managed skill fetch | `skills:read` |
| Remote MCP `scan_skill` / `scan_repo` | `skills:read` |
| REST or remote MCP chat | `chat` |
| REST streaming chat | `chat` or `chat:stream` |

Legacy null scopes retain `chat` compatibility. An explicit `[]` does not grant
chat or skill access. MCP utility tools without a required scope remain
available to authenticated keys. A signed-in dashboard chat request selects a
valid key from the user's current workspace.

## Save, scan, and deliver

Managed skill saving supports advisory drafts. The dashboard checks conflicts
and requires an explicit choice before saving a flagged draft; clients can
request a server block on critical conflicts with `block_on_conflict=true`.
Saving, including an explicit save with conflicts, does not approve distribution.

Every managed download and live fetch verifies the stored source hash, builds
the response, and then scans its authored context before returning a document.
Wrapped delivery scans the source plus emitted name, description, and live URL;
raw delivery scans the source. Unapproved findings produce HTTP 422 with a
`rejection_id` and no skill document. Review that case and retry the same delivery.

`POST /skills/scan` returns both the raw scan (`safe`, `findings`, `risk_score`)
and the approval-aware decision (`blocked`, `agent_may_continue`,
`blocking_findings`, `overridden_findings`). A reviewed finding can leave
`safe=false` while `agent_may_continue=true`. Nonempty client-supplied overrides
are rejected; the hosted API does not load local CLI override files.

The scanner is heuristic. A clean result means its checks found no issue; it is
not proof that arbitrary instructions or commands are safe to execute. Finding
snippets and review evidence redact detected credentials before truncation.

## Exact approvals and review history

Hosted approvals belong to one user and workspace. Their identity includes the
filename, full scanned-content digest, reason code, check, severity, line number,
and redacted snippet. Matching a category or line alone cannot reuse a grant.
Managed delivery additionally binds the revision, authored metadata, update mode,
and raw/wrapped choice. Generated timestamps do not change that stable identity.

- **Allow once** grants one matching scan or delivery attempt. Consumption is
  committed before its response returns, including when other findings still
  block that attempt. Retrying after a lost response can require another review.
- **Always allow** persists only those exact reviewed identities. Editing the
  content or relevant delivery metadata cannot reuse the prior grant; remaining
  findings require another review.
- **Keep blocked** revokes prior grants for the exact identities in that case.

Review resolution is immutable: retrying the same action returns the recorded
result without granting twice; a different action on a resolved case returns
409. Repeated pending attempts with identical evidence reuse their pending case;
a later attempt after resolution can create a new case. Database row locks
serialize grant updates and consumption across workers.

Legacy broad hosted grants are ignored. Older cases without complete content
identity cannot be approved; re-scan or re-report them first. CLI-reported
digests are client-attested, while hosted scans derive digests on the server.
Repository-local CLI approvals remain a separate workflow.
The pre-push hook and CI use the canonical Python scanner. A prebuilt Go scanner
or `SKILL_GUARD_BIN` cannot replace that check; the standalone Go companion may
implement a different set of detections.
Push checks read committed skill blobs throughout the outgoing history, including
unsafe versions later reverted, and deduplicate identical blobs. Local working
files cannot replace that evidence. New branches check all reachable skill
history; Git failures, unreadable Markdown, and committed skill-file symlinks
block the check. An inherited unsafe skill can therefore block an unrelated
outgoing commit until explicitly reviewed in the separate local CLI workflow.

## Editing, versions, and integrity

Source bytes are preserved. Content changes increment `version` and create a
history entry. The `revision` digest also covers metadata and update mode, so a
metadata-only change invalidates a stale editor without incrementing the content
version. Updates with stale `expected_version` or `expected_revision` return 409;
the dashboard preserves the draft until the user explicitly reloads.

Delivery includes `X-Skill-Slug`, `X-Skill-Version`, `X-Skill-Update-Mode`,
`X-Skill-Revision`, `X-Skill-Content-SHA256` for the exact source, and
`X-Skill-Document-SHA256` for the complete returned document. The dashboard
verifies the download metadata and document digest before saving the file.
Responses use private, no-store caching. These hashes are integrity checksums,
not digital signatures or independent proof of origin; use authenticated HTTPS.

`overwrite` and `versioned` change filenames and installation guidance. The
downloaded Markdown does not fetch itself, replace local files, or select the
newest version automatically. The consumer must perform those steps explicitly.

## Agent and MCP boundaries

Scan responses and chat decision packets declare `runtime_enforced=false`.
Status labels such as `paused` describe the decision; they do not pause an
external process. The receiving integration must prevent flagged content from
loading, honor `agent_may_continue`, and apply local decision packets deliberately.
Pasting a packet does not create a hosted approval.

Remote MCP chat delegates to the canonical gateway with the authenticated
request, preserving workspace policy, billing, budgets, limits, and audit
behavior. It rejects client policy overrides. Remote tool calls validate input
and fail closed if their description poisoning check cannot run. Local stdio
tools are separate local utilities, not hosted workspace enforcement.

The automated checks exercise these contracts with isolated databases and
browser API fixtures. They do not establish that a production deployment has
rolled out, that PostgreSQL concurrency has been exercised under live load, or
that an unrelated external agent honors the integration contract.
