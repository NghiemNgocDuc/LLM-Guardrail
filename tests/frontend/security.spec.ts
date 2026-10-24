import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { createHash } from "node:crypto";
import { key, mockWorkspace, policy, skill } from "./fixtures";

const completeKey = { ...key, total_requests: 24, total_blocked: 2 };
const finding = { finding_key: "finding-ui-1", category: "secrets", severity: "critical", check: "hardcoded_credential", reason: "Credential in agent instructions", reason_code: "secret_detected", explanation: "Remove the credential from agent instructions.", line_number: 2, snippet: "credential = [REDACTED]", risk_score: 90, allowed_by_override: false };
const rejection = { id: "rejection-ui-1", filename: "unsafe.md", source: "api_scan", status: "pending", findings: [finding], rejection_summary: "Rejected access: credential detected", content_preview: "# Unsafe skill", created_at: "2026-10-13T12:00:00Z", resolved_at: null as string | null, resolved_action: null as string | null, resolver_note: null as string | null };
const conflict = { has_conflict: true, blocked_by_policy: true, summary: "Skill conflicts with API-key leak protection", conflicts: [{ type: "credential_exposure", severity: "critical", reason: "This instruction asks for credentials.", reason_code: "secret_detected", evidence: "Share the credentials.", conflicting_skill_slug: "baseline", remediation: "Remove the credential instruction.", line_number: 2 }] };

async function mockKeys(page: Page) {
  let keys = [{ ...completeKey }];
  return mockWorkspace(page, { override: request => {
    if (request.path === "/api-keys" && request.method === "GET") return { json: keys };
    if (request.path === "/api-keys" && request.method === "POST") {
      const created = { ...completeKey, ...request.body, id: "key-ui-new", key_prefix: "grg_test", total_requests: 0, total_blocked: 0 };
      keys.push(created); return { json: { ...created, raw_key: "grg_ui_test_only_key_value" } };
    }
    if (request.path.startsWith("/api-keys/") && request.method === "DELETE") { keys = keys.map(item => item.id === request.path.split("/").at(-1) ? { ...item, is_active: false } : item); return { status: 204, body: "" }; }
  } });
}

test("API keys create only selected scopes and dismiss the one-time value", async ({ page }) => {
  const { requests, unknown } = await mockKeys(page);
  await page.goto("/?view=keys");
  await expect(page.getByRole("heading", { name: "API keys", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Create key", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Create an API key" });
  await dialog.getByRole("textbox", { name: "Key name", exact: true }).fill("Read-only CI");
  await dialog.getByLabel("Expiration date (optional)", { exact: true }).fill("2027-01-01");
  await dialog.getByRole("checkbox", { name: /^chat\s+Send/ }).uncheck();
  await dialog.getByRole("checkbox", { name: /^logs:read/ }).check();
  await dialog.getByRole("checkbox", { name: /^analytics/ }).check();
  await dialog.getByRole("button", { name: "Create key", exact: true }).click();
  await expect(dialog).not.toBeVisible();
  await expect(page.getByText("grg_ui_test_only_key_value", { exact: true })).toBeVisible();
  const created = requests.find(request => request.path === "/api-keys" && request.method === "POST");
  expect(created?.body).toEqual({ name: "Read-only CI", scopes: ["logs:read", "analytics"], expires_at: "2027-01-01" });
  expect(created?.authorization).toBe("Bearer ui-test-token");
  await expect(page.getByRole("row").filter({ hasText: "Read-only CI" })).toContainText("logs:read");
  await page.getByRole("button", { name: "Dismiss", exact: true }).click();
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(page.getByText("grg_ui_test_only_key_value", { exact: true })).toHaveCount(0);
  expect(unknown).toEqual([]);
});

test("API key revocation cancels without mutation and confirms exactly once", async ({ page }) => {
  const { requests, unknown } = await mockKeys(page);
  await page.goto("/?view=keys");
  const row = page.getByRole("row").filter({ hasText: key.name });
  await row.getByRole("button", { name: "Revoke", exact: true }).click();
  let dialog = page.getByRole("dialog", { name: `Revoke ${key.name}?`, exact: true });
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(dialog).not.toBeVisible();
  expect(requests.filter(request => request.method === "DELETE")).toHaveLength(0);
  await row.getByRole("button", { name: "Revoke", exact: true }).click();
  dialog = page.getByRole("dialog", { name: `Revoke ${key.name}?`, exact: true });
  await dialog.getByRole("button", { name: "Revoke key", exact: true }).click();
  await expect(row).toContainText("Revoked");
  await expect(row.getByRole("button", { name: "Revoke", exact: true })).toHaveCount(0);
  expect(requests.filter(request => request.path === `/api-keys/${key.id}` && request.method === "DELETE")).toHaveLength(1);
  expect(unknown).toEqual([]);
});

test("policy editing validates Rego and saves only writable fields while preserving nested rules", async ({ page }) => {
  const { requests, unknown } = await mockWorkspace(page);
  await page.goto("/?view=policy");
  await expect(page.getByRole("radio", { name: /^Warn / })).toBeChecked();
  await page.getByRole("switch", { name: /^Prompt injection/ }).uncheck();
  await page.getByRole("textbox", { name: "Injection keywords", exact: true }).fill("first pattern\n\nsecond pattern");
  await expect(page.getByRole("textbox", { name: "Injection keywords", exact: true })).toHaveValue("first pattern\n\nsecond pattern");
  await page.getByRole("textbox", { name: "Custom topic", exact: true }).fill("crypto advice");
  await page.getByRole("button", { name: "Add topic", exact: true }).click();
  const rego = "package guardrails.custom\ndefault allow := true";
  await page.getByRole("textbox", { name: "Rego source", exact: true }).fill(rego);
  await page.getByRole("button", { name: "Validate rule", exact: true }).click();
  await expect(page.getByText("Rule compiles successfully. Save changes to apply it.")).toBeVisible();
  expect(requests.find(request => request.path === "/policy/validate-rego")?.body).toEqual({ rego });
  await page.getByRole("button", { name: "Save changes", exact: true }).first().click();
  await expect(page.getByText("Policy saved. New requests will use the updated configuration.")).toBeVisible();
  const patch = requests.find(request => request.path === "/policy" && request.method === "PATCH");
  expect(patch?.body).not.toHaveProperty("org_id");
  expect(patch?.body).not.toHaveProperty("version");
  expect(patch?.body).not.toHaveProperty("updated_at");
  expect(patch?.body.input_rules).toMatchObject({ ...policy.input_rules, block_prompt_injection: false, injection_keywords: ["first pattern", "second pattern"] });
  expect(patch?.body.output_rules).toEqual(policy.output_rules);
  expect(patch?.body.compliance_rules.custom_retained_field).toBe("keep-me");
  expect(patch?.body.topic_policy.blocked_topics).toEqual(["medical advice", "crypto advice"]);
  expect(patch?.body.custom_rule_rego).toBe(rego);
  expect(patch?.body.llm_backend).toBe(policy.llm_backend);
  expect(patch?.body.rate_limit_rpd).toBe(policy.rate_limit_rpd);
  await page.getByRole("button", { name: "Restore defaults", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Restore default policy?" });
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(dialog).not.toBeVisible();
  expect(requests.filter(request => request.path === "/policy/reset")).toHaveLength(0);
  expect(unknown).toEqual([]);
});

test("policy preview obeys toggles and reports invalid Rego without saving", async ({ page }) => {
  const { requests } = await mockWorkspace(page, { override: request => request.path === "/policy/validate-rego" ? { json: { valid: false, error: "rego_parse_error: unexpected token" } } : undefined });
  await page.goto("/?view=policy");
  await expect(page.getByText("Local match · prompt injection", { exact: true })).toBeVisible();
  await page.getByRole("switch", { name: /^Prompt injection/ }).uncheck();
  await expect(page.getByText("No match in local preview", { exact: true })).toBeVisible();
  await page.getByRole("textbox", { name: "Rego source", exact: true }).fill("invalid rule");
  await page.getByRole("button", { name: "Validate rule", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("rego_parse_error");
  expect(requests.filter(request => request.path === "/policy" && request.method === "PATCH")).toHaveLength(0);
});

test("Skill Guard paste scan submits content and shows a clean decision", async ({ page }) => {
  const { requests, unknown } = await mockWorkspace(page);
  await page.goto("/?view=skills");
  const content = "# Documentation helper\nSummarize public documentation without credentials.";
  await page.getByRole("textbox", { name: "Skill or instruction content", exact: true }).fill(content);
  await page.getByRole("button", { name: "Scan skill", exact: true }).click();
  await expect(page.getByText("This scan allows the content.", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "No findings", exact: true })).toBeVisible();
  expect(requests.find(request => request.path === "/skills/scan")?.body).toEqual({ content, filename: "SKILL.md" });
  expect(unknown).toEqual([]);
});

test("Skill Guard file scan shows blocking evidence and opens its reported rejection", async ({ page }) => {
  let scanned = false;
  const content = "# Unsafe skill\ncredential = unsafe-example";
  const { requests, unknown } = await mockWorkspace(page, { override: request => {
    if (request.path === "/skills/scan") { scanned = true; return { json: { safe: false, risk_score: 90, findings: [finding], line_count: 2, char_count: content.length, filename: request.body.filename, blocked: true, agent_may_continue: false, agent_status: "paused", blocking_findings: [finding], overridden_findings: [], rejection_id: rejection.id, rejection_summary: rejection.rejection_summary } }; }
    if (request.path.startsWith("/skills/rejections?")) return { json: scanned ? [rejection] : [] };
  } });
  await page.goto("/?view=skills");
  await page.getByLabel("Upload a skill file", { exact: true }).setInputFiles({ name: "unsafe.md", mimeType: "text/markdown", buffer: Buffer.from(content) });
  await expect(page.getByRole("textbox", { name: "Filename", exact: true })).toHaveValue("unsafe.md");
  await expect(page.getByRole("textbox", { name: "Skill or instruction content", exact: true })).toHaveValue(content);
  await page.getByRole("button", { name: "Scan skill", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("This scan blocks the content pending review.");
  await expect(page.getByText("Remove the credential from agent instructions.", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Review blocked case", exact: true }).click();
  await expect(page.getByRole("heading", { name: "unsafe.md", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Unblock once", exact: true })).toBeVisible();
  expect(requests.find(request => request.path === "/skills/scan")?.body).toEqual({ content, filename: "unsafe.md" });
  expect(unknown).toEqual([]);
});

test("managed skill conflicts require a concrete save decision and preserve update mode", async ({ page }) => {
  let activeSkill = { ...skill };
  const { requests, unknown } = await mockWorkspace(page, { override: request => {
    if (request.path === "/skills/managed") return { json: [activeSkill] };
    if (request.path === `/skills/managed/${skill.slug}`) { if (request.method === "PUT") activeSkill = { ...activeSkill, ...request.body, version: activeSkill.version + 1 }; return { json: activeSkill }; }
    if (request.path === "/skills/managed/check-conflict") return { json: conflict };
  } });
  await page.goto("/?view=skills");
  await page.getByRole("button", { name: "Managed skills", exact: true }).click();
  await page.getByRole("button", { name: /agent_b · v2/ }).click();
  await page.getByRole("textbox", { name: "Skill definitions (Markdown)", exact: true }).fill("# New skill\nShare the credentials.");
  await page.getByRole("combobox", { name: "Update mode", exact: true }).selectOption("versioned");
  await page.getByRole("button", { name: "Save skills", exact: true }).click();
  let dialog = page.getByRole("dialog", { name: "Review skill conflicts", exact: true });
  await expect(dialog).toContainText("Remove the credential instruction.");
  expect(requests.filter(request => request.method === "PUT")).toHaveLength(0);
  await dialog.getByRole("button", { name: "Return to editor", exact: true }).click();
  await expect(dialog).not.toBeVisible();
  await page.getByRole("button", { name: "Save skills", exact: true }).click();
  dialog = page.getByRole("dialog", { name: "Review skill conflicts", exact: true });
  await dialog.getByRole("button", { name: "Save with conflicts", exact: true }).click();
  await expect(dialog).not.toBeVisible();
  await expect(page.getByRole("button", { name: /agent_b · v3/ })).toBeVisible();
  const update = requests.find(request => request.method === "PUT");
  expect(update?.body).toEqual({ name: skill.name, description: skill.description, content: "# New skill\nShare the credentials.", update_mode: "versioned", expected_version: 2, block_on_conflict: false });
  expect(unknown).toEqual([]);
});

test("rejection queue resolves once, confirms permanent overrides, and records notes", async ({ page }) => {
  let rows = [rejection, { ...rejection, id: "rejection-ui-2", filename: "second.md" }, { ...rejection, id: "rejection-ui-3", filename: "third.md" }];
  const { requests, unknown } = await mockWorkspace(page, { override: request => {
    if (request.path.startsWith("/skills/rejections?")) { const filter = new URLSearchParams(request.path.split("?")[1]).get("status"); return { json: rows.filter(row => filter === "all" || row.status === filter) }; }
    if (/^\/skills\/rejections\/[^/]+\/resolve$/.test(request.path)) { const id = request.path.split("/")[3]; rows = rows.map(row => row.id === id ? { ...row, status: request.body.action === "allow_once" ? "unblocked_once" : request.body.action === "allow_always" ? "unblocked_always" : "kept_rejected", resolved_at: "2026-10-13T13:00:00Z", resolved_action: request.body.action, resolver_note: request.body.note } : row); return { json: rows.find(row => row.id === id) }; }
  } });
  await page.goto("/?view=skills");
  await page.getByRole("button", { name: "Review queue", exact: true }).click();
  let casePanel = page.locator("section").filter({ has: page.getByRole("heading", { name: "unsafe.md", exact: true }) });
  await casePanel.getByRole("textbox", { name: "Resolution note (optional)", exact: true }).fill("Approved for this isolated test.");
  await casePanel.getByRole("button", { name: "Unblock once", exact: true }).click();
  await expect(page.getByRole("heading", { name: "unsafe.md", exact: true })).toHaveCount(0);
  casePanel = page.locator("section").filter({ has: page.getByRole("heading", { name: "second.md", exact: true }) });
  await casePanel.getByRole("button", { name: "Always allow", exact: true }).click();
  let dialog = page.getByRole("dialog", { name: "Always allow these findings?", exact: true });
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(dialog).not.toBeVisible();
  expect(requests.filter(request => request.body?.action === "allow_always")).toHaveLength(0);
  await casePanel.getByRole("button", { name: "Always allow", exact: true }).click();
  dialog = page.getByRole("dialog", { name: "Always allow these findings?", exact: true });
  await dialog.getByRole("button", { name: "Always allow", exact: true }).click();
  await expect(page.getByRole("heading", { name: "second.md", exact: true })).toHaveCount(0);
  casePanel = page.locator("section").filter({ has: page.getByRole("heading", { name: "third.md", exact: true }) });
  await casePanel.getByRole("button", { name: "Keep rejected", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Nothing waiting for review", exact: true })).toBeVisible();
  const resolutions = requests.filter(request => request.path.endsWith("/resolve"));
  expect(resolutions.map(request => request.body.action)).toEqual(["allow_once", "allow_always", "keep_rejected"]);
  expect(resolutions[0].body.note).toBe("Approved for this isolated test.");
  await page.getByRole("button", { name: "All cases", exact: true }).click();
  await expect(page.getByRole("heading", { name: "unsafe.md", exact: true })).toBeVisible();
  await expect(page.getByText("Allowed once", { exact: true })).toHaveCount(2);
  expect(unknown).toEqual([]);
});

test("non-admin members can scan and read managed skills but cannot edit or save them", async ({ page }) => {
  const { requests } = await mockWorkspace(page, { admin: false });
  await page.goto("/?view=skills");
  await expect(page.getByText("Managed skill definitions are read-only.", { exact: false })).toBeVisible();
  await page.getByRole("textbox", { name: "Skill or instruction content", exact: true }).fill("# Safe public documentation");
  await page.getByRole("button", { name: "Scan skill", exact: true }).click();
  await expect(page.getByText("This scan allows the content.", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Managed skills", exact: true }).click();
  await page.getByRole("button", { name: /agent_b · v2/ }).click();
  await expect(page.getByRole("textbox", { name: "Skill definitions (Markdown)", exact: true })).toHaveValue(skill.content);
  await expect(page.getByRole("textbox", { name: "Skill definitions (Markdown)", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Save skills", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Add agent", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Delete skill", exact: true })).toHaveCount(0);
  expect(requests.filter(request => request.path.startsWith("/skills/managed") && ["PUT", "POST", "DELETE"].includes(request.method))).toEqual([]);
});

test("failed managed conflict precheck stops writes and preserves the exact draft", async ({ page }) => {
  const { requests } = await mockWorkspace(page, { override: request => request.path === "/skills/managed/check-conflict" ? { status: 503, json: { detail: "Conflict evaluator unavailable" } } : undefined });
  await page.goto("/?view=skills");
  await page.getByRole("button", { name: "Managed skills", exact: true }).click();
  await page.getByRole("button", { name: /agent_b · v2/ }).click();
  const editor = page.getByRole("textbox", { name: "Skill definitions (Markdown)", exact: true });
  await editor.fill("# Edited draft\nNever expose credentials.");
  await page.getByRole("button", { name: "Save skills", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("The conflict check failed. Nothing was saved.");
  await expect(editor).toHaveValue("# Edited draft\nNever expose credentials.");
  expect(requests.filter(request => request.method === "PUT" || request.path === "/skills/managed" && request.method === "POST")).toHaveLength(0);
});

test("a failed full-content read never enables saving the truncated preview", async ({ page }) => {
  let available = false;
  const { requests } = await mockWorkspace(page, { override: request => request.path === `/skills/managed/${skill.slug}` ? available ? { json: skill } : { status: 503, json: { detail: "Full skill content unavailable" } } : undefined });
  await page.goto("/?view=skills");
  await page.getByRole("button", { name: "Managed skills", exact: true }).click();
  await page.getByRole("button", { name: /agent_b · v2/ }).click();
  await expect(page.getByRole("alert")).toContainText("Full skill content unavailable");
  await expect(page.getByRole("button", { name: "Save skills", exact: true })).toHaveCount(0);
  await expect(page.getByRole("textbox", { name: "Skill definitions (Markdown)", exact: true })).toHaveCount(0);
  expect(requests.filter(request => request.method === "PUT")).toHaveLength(0);
  available = true;
  await page.getByRole("button", { name: "Retry loading complete skill", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "Skill definitions (Markdown)", exact: true })).toHaveValue(skill.content);
  await expect(page.getByRole("button", { name: "Save skills", exact: true })).toBeEnabled();
});

test("new and default managed drafts survive agent selection and workspace refresh", async ({ page }) => {
  await mockWorkspace(page, { empty: true });
  await page.goto("/?view=skills");
  await page.getByRole("button", { name: "Managed skills", exact: true }).click();
  await page.getByRole("textbox", { name: "New agent slug", exact: true }).fill("support_agent");
  await page.getByRole("button", { name: "Add agent", exact: true }).click();
  const editor = page.getByRole("textbox", { name: "Skill definitions (Markdown)", exact: true });
  await editor.fill("# Unsaved support draft\nCustom safe instruction.");
  await page.getByRole("textbox", { name: "Agent name", exact: true }).fill("Support draft");
  await page.getByRole("button", { name: /agent_b · draft/ }).click();
  await expect(editor).not.toHaveValue("# Unsaved support draft\nCustom safe instruction.");
  await page.getByRole("button", { name: /support_agent · draft/ }).click();
  await expect(editor).toHaveValue("# Unsaved support draft\nCustom safe instruction.");
  await expect(page.getByRole("textbox", { name: "Agent name", exact: true })).toHaveValue("Support draft");
  await page.getByRole("button", { name: "Refresh workspace", exact: true }).click();
  await expect(page.getByRole("button", { name: "Refresh workspace", exact: true })).toBeEnabled();
  await expect(editor).toHaveValue("# Unsaved support draft\nCustom safe instruction.");
});

test("stale rejection responses cannot replace a newer selected filter", async ({ page }) => {
  let releaseAll: (value: { json: unknown }) => void = () => {};
  const all = new Promise<{ json: unknown }>(resolve => { releaseAll = resolve; });
  const { requests } = await mockWorkspace(page, { override: request => {
    if (request.path === "/skills/rejections?status=all") return all;
    if (request.path === "/skills/rejections?status=pending") return { json: [rejection] };
  } });
  await page.goto("/?view=skills");
  await page.getByRole("button", { name: "Review queue", exact: true }).click();
  await expect(page.getByRole("heading", { name: "unsafe.md", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "All cases", exact: true }).click();
  await expect.poll(() => requests.some(request => request.path === "/skills/rejections?status=all")).toBe(true);
  await page.getByRole("button", { name: "Awaiting review", exact: true }).click();
  await expect(page.getByRole("heading", { name: "unsafe.md", exact: true })).toBeVisible();
  const finished = page.waitForResponse(response => response.url().endsWith("/skills/rejections?status=all"));
  releaseAll({ json: [{ ...rejection, id: "old-filter-row", filename: "stale-all.md", status: "kept_rejected" }] });
  await finished;
  await expect(page.getByRole("heading", { name: "unsafe.md", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "stale-all.md", exact: true })).toHaveCount(0);
});

test("managed stale-write rejection preserves the draft until an explicit reload", async ({ page }) => {
  const revision = "a".repeat(64);
  let activeSkill = { ...skill, revision };
  const { requests } = await mockWorkspace(page, { override: request => {
    if (request.path === "/skills/managed") return { json: [activeSkill] };
    if (request.path === `/skills/managed/${skill.slug}`) {
      if (request.method === "PUT") { activeSkill = { ...activeSkill, version: 3, revision: "b".repeat(64), content: "# New server version" }; return { status: 409, json: { detail: "Skill changed since you loaded it. Reload before saving." } }; }
      return { json: activeSkill };
    }
  } });
  await page.goto("/?view=skills");
  await page.getByRole("button", { name: "Managed skills", exact: true }).click();
  await page.getByRole("button", { name: /agent_b · v2/ }).click();
  const editor = page.getByRole("textbox", { name: "Skill definitions (Markdown)", exact: true });
  await editor.fill("# My unsaved revision");
  await page.getByRole("button", { name: "Save skills", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Skill changed since you loaded it.");
  await expect(editor).toHaveValue("# My unsaved revision");
  const update = requests.find(request => request.method === "PUT");
  expect(update?.body).toMatchObject({ expected_version: 2, expected_revision: revision, content: "# My unsaved revision", block_on_conflict: true });
  await page.getByRole("button", { name: "Reload saved skill", exact: true }).click();
  let dialog = page.getByRole("dialog", { name: "Reload the saved skill?", exact: true });
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(dialog).not.toBeVisible();
  await expect(editor).toHaveValue("# My unsaved revision");
  await page.getByRole("button", { name: "Reload saved skill", exact: true }).click();
  dialog = page.getByRole("dialog", { name: "Reload the saved skill?", exact: true });
  await dialog.getByRole("button", { name: "Reload saved skill", exact: true }).click();
  await expect(editor).toHaveValue("# New server version");
});

async function mockedDownload(page: Page, mode: "overwrite" | "versioned", options: { status?: number; corrupt?: boolean; version?: number } = {}) {
  await mockWorkspace(page);
  const version = options.version || skill.version;
  const document = `---\nname: ${JSON.stringify(skill.slug)}\nversion: ${version}\nfull_hash: ${JSON.stringify(skill.full_hash)}\nmanaged_by: llm-guardrails\nupdate_mode: ${mode}\n---\n\n# Verified skill document\n`;
  const digest = createHash("sha256").update(document).digest("hex");
  await page.route("**/skills/managed/*/download?*", route => route.fulfill({ status: options.status || 200, headers: { "access-control-allow-origin": "*", "access-control-expose-headers": "Content-Disposition,X-Skill-Slug,X-Skill-Version,X-Skill-Content-SHA256,X-Skill-Document-SHA256,X-Skill-Update-Mode", "content-disposition": `attachment; filename="${skill.slug}${mode === "versioned" ? `.v${version}` : ""}.md"`, "x-skill-slug": skill.slug, "x-skill-version": String(version), "x-skill-content-sha256": skill.full_hash, "x-skill-document-sha256": options.corrupt ? "0".repeat(64) : digest, "x-skill-update-mode": mode }, contentType: options.status ? "application/json" : "text/markdown; charset=utf-8", body: options.status ? JSON.stringify({ detail: "Download authorization denied" }) : document }));
  await page.goto("/?view=skills");
  await page.getByRole("button", { name: "Managed skills", exact: true }).click();
  await page.getByRole("button", { name: /agent_b · v2/ }).click();
  await page.getByRole("combobox", { name: "Download behavior", exact: true }).selectOption(mode);
  return document;
}

test("skill download rejects HTTP and HTML errors without public fallback", async ({ page }) => {
  let downloads = 0, liveFetches = 0;
  page.on("download", () => { downloads += 1; });
  page.on("request", request => { if (request.url().includes("/skills/live/")) liveFetches += 1; });
  await mockedDownload(page, "overwrite", { status: 403 });
  await page.getByRole("button", { name: "Download Markdown", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Download authorization denied");
  expect(downloads).toBe(0); expect(liveFetches).toBe(0);
  await page.unroute("**/skills/managed/*/download?*");
  await page.route("**/skills/managed/*/download?*", route => route.fulfill({ status: 200, contentType: "text/html", body: "<html>Upstream gateway error</html>", headers: { "access-control-allow-origin": "*" } }));
  await page.getByRole("button", { name: "Download Markdown", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("did not return a Markdown skill file");
  expect(downloads).toBe(0);
});

test("skill versioned download verifies exact response bytes and authoritative version", async ({ page }) => {
  const expectedDocument = await mockedDownload(page, "versioned", { version: 3 });
  const downloadEvent = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download Markdown", exact: true }).click();
  const download = await downloadEvent;
  expect(download.suggestedFilename()).toBe("agent_b.v3.md");
  const stream = await download.createReadStream();
  expect(stream).not.toBeNull();
  const chunks: Buffer[] = [];
  for await (const chunk of stream!) chunks.push(Buffer.from(chunk));
  expect(Buffer.concat(chunks).toString("utf8")).toBe(expectedDocument);
  await expect(page.getByText("Downloaded agent_b.v3.md.", { exact: false })).toBeVisible();
});

test("skill checksum mismatch never creates a download", async ({ page }) => {
  let downloads = 0;
  page.on("download", () => { downloads += 1; });
  await mockedDownload(page, "overwrite", { corrupt: true });
  await page.getByRole("button", { name: "Download Markdown", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("failed its integrity check");
  expect(downloads).toBe(0);
});

test("a policy-blocked download opens its exact review case and retries only after approval", async ({ page }) => {
  let approved = false, downloadChecks = 0;
  const downloadCase = { ...rejection, filename: `${skill.slug}.md` };
  const { requests } = await mockWorkspace(page, { override: request => {
    if (request.path.startsWith("/skills/rejections?")) return { json: approved ? [] : [downloadCase] };
    if (request.path === `/skills/rejections/${rejection.id}/resolve`) { approved = true; return { json: { ...downloadCase, status: "unblocked_once", resolved_at: "2026-10-13T13:00:00Z", resolved_action: "allow_once", resolver_note: request.body.note } }; }
  } });
  const document = `---\nname: ${JSON.stringify(skill.slug)}\nversion: ${skill.version}\nfull_hash: ${JSON.stringify(skill.full_hash)}\nmanaged_by: llm-guardrails\nupdate_mode: overwrite\n---\n\n# Approved skill\n`;
  await page.route("**/skills/managed/*/download?*", route => {
    downloadChecks += 1;
    const cors = { "access-control-allow-origin": "*", "access-control-expose-headers": "Content-Disposition,X-Skill-Slug,X-Skill-Version,X-Skill-Content-SHA256,X-Skill-Document-SHA256,X-Skill-Update-Mode" };
    if (!approved) return route.fulfill({ status: 422, headers: cors, json: { detail: { message: "Skill delivery blocked by canonical scan", rejection_id: rejection.id } } });
    return route.fulfill({ status: 200, contentType: "text/markdown; charset=utf-8", body: document, headers: { ...cors, "content-disposition": `attachment; filename="${skill.slug}.md"`, "x-skill-slug": skill.slug, "x-skill-version": String(skill.version), "x-skill-content-sha256": skill.full_hash, "x-skill-document-sha256": createHash("sha256").update(document).digest("hex"), "x-skill-update-mode": "overwrite" } });
  });
  await page.goto("/?view=skills");
  await page.getByRole("button", { name: "Managed skills", exact: true }).click();
  await page.getByRole("button", { name: /agent_b · v2/ }).click();
  await page.getByRole("button", { name: "Download Markdown", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Review the blocked case before retrying this download.");
  await page.getByRole("button", { name: "Review blocked download", exact: true }).click();
  await expect(page.getByRole("heading", { name: "agent_b.md", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Unblock once", exact: true }).click();
  await expect(page.getByText("One-time approval saved for the next matching scan or download. No agent runtime was resumed.", { exact: true })).toBeVisible();
  expect(downloadChecks).toBe(1);
  expect(requests.filter(request => request.path.endsWith("/resolve"))).toHaveLength(1);
  await page.getByRole("button", { name: "Managed skills", exact: true }).click();
  const completed = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download Markdown", exact: true }).click();
  expect((await completed).suggestedFilename()).toBe("agent_b.md");
  expect(downloadChecks).toBe(2);
});

test("resolving a scan clears its stale decision and a one-time approval requires a new matching scan", async ({ page }) => {
  let approved = false, scans = 0, currentCase = rejection;
  const { requests } = await mockWorkspace(page, { override: request => {
    if (request.path === "/skills/scan") {
      scans += 1;
      const allowed = approved;
      approved = false;
      if (!allowed) currentCase = { ...rejection, id: scans === 1 ? rejection.id : "rejection-ui-new" };
      return { json: { safe: false, risk_score: 90, filename: request.body.filename, findings: [{ ...finding, allowed_by_override: allowed }], line_count: 2, char_count: request.body.content.length, blocked: !allowed, agent_may_continue: allowed, agent_status: allowed ? "ok" : "paused", rejection_id: allowed ? null : currentCase.id, rejection_summary: allowed ? "" : rejection.rejection_summary, blocking_findings: allowed ? [] : [finding], overridden_findings: allowed ? [{ ...finding, allowed_by_override: true }] : [] } };
    }
    if (request.path.startsWith("/skills/rejections?")) return { json: currentCase.status === "pending" ? [currentCase] : [] };
    if (request.path.endsWith("/resolve")) { approved = true; currentCase = { ...currentCase, status: "unblocked_once", resolved_action: "allow_once", resolved_at: "2026-10-13T13:00:00Z" }; return { json: currentCase }; }
  } });
  await page.goto("/?view=skills");
  await page.getByRole("textbox", { name: "Skill or instruction content", exact: true }).fill("# Unsafe skill\ncredential = unsafe-example");
  await page.getByRole("button", { name: "Scan skill", exact: true }).click();
  await page.getByRole("button", { name: "Review blocked case", exact: true }).click();
  await page.getByRole("button", { name: "Unblock once", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Nothing waiting for review", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Scan a skill", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Ready when you are", exact: true })).toBeVisible();
  expect(scans).toBe(1);
  await page.getByRole("button", { name: "Scan skill", exact: true }).click();
  await expect(page.getByText("This scan allows the content.", { exact: true })).toBeVisible();
  await expect(page.getByText("Allowed by override", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Scan skill", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("This scan blocks the content pending review.");
  expect(requests.filter(request => request.path === "/skills/scan")).toHaveLength(3);
});
