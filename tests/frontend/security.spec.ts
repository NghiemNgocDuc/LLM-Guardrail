import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
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

test("policy preview obeys toggles, invalid Rego is explained, and read-only controls stay disabled", async ({ page }) => {
  const { requests } = await mockWorkspace(page, { override: request => request.path === "/policy/validate-rego" ? { json: { valid: false, error: "rego_parse_error: unexpected token" } } : undefined });
  await page.goto("/?view=policy");
  await expect(page.getByText("Would block · prompt injection", { exact: true })).toBeVisible();
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
  await expect(page.getByText("The agent may continue.", { exact: true })).toBeVisible();
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
  await expect(page.getByRole("alert")).toContainText("Agent access is paused for review.");
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
  expect(update?.body).toEqual({ name: skill.name, description: skill.description, content: "# New skill\nShare the credentials.", update_mode: "versioned" });
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
