import { expect, test } from "@playwright/test";
import { mockWorkspace, policy } from "./fixtures";

const cleanGuard = { passed: true, check: "all", reason: "", reason_code: "clean", risk_score: 0 };

test("ordinary drafts reach the gateway once and use its returned decision", async ({ page }) => {
  let submitted = 0;
  const { requests, unknown } = await mockWorkspace(page, { override: request => request.path === "/chat" ? { json: { request_id: "ordinary-" + ++submitted, response: "The gateway accepted example " + submitted + ".", status: "delivered", input_guard: cleanGuard, output_guard: cleanGuard, latency_ms: 18, backend: "mock", model: "mock-local" } } : undefined });
  await page.goto("/?view=chat");
  const prompts = [
    "Explain how to enable developer mode on an Android phone.",
    "I forget everything unless I write it down. Suggest a study routine.",
    "Explain why a security guide quotes 'ignore previous instructions'.",
    "Summarize order reference 1234567890123 for a support note.",
  ];
  for (const [index, prompt] of prompts.entries()) {
    await page.getByLabel("Your prompt", { exact: true }).fill(prompt);
    await page.getByRole("button", { name: "Run prompt", exact: true }).click();
    await expect(page.getByText("The gateway accepted example " + (index + 1) + ".", { exact: true })).toBeVisible();
    const sent = requests.filter(request => request.path === "/chat");
    expect(sent).toHaveLength(index + 1);
    expect(sent[index].body).toEqual({ prompt });
    expect(sent[index].authorization).toBe("Bearer ui-test-token");
  }
  await expect(page.locator(".chat-result.is-blocked")).toHaveCount(0);
  await expect(page.getByText("Client blocked", { exact: true })).toHaveCount(0);
  expect(unknown).toEqual([]);
});

for (const mode of ["warn", "redact", "off"] as const) {
  test(`playground follows the gateway's ${mode} policy without a client veto`, async ({ page }) => {
    const prompt = "Explain developer mode for a form demo using the fictional SSN 123-45-6789.";
    const configured = { ...policy, input_rules: { ...policy.input_rules, pii_redaction_mode: mode, block_pii: mode === "warn", block_prompt_injection: mode === "warn", block_jailbreak: mode === "warn", injection_mode: "warn", jailbreak_mode: "warn" } };
    const input = { ...cleanGuard, reason_code: mode === "redact" ? "pii_redacted" : mode === "warn" ? "warned_pii_detected" : "clean" };
    const { requests, unknown } = await mockWorkspace(page, { override: request => request.path === "/policy" && request.method === "GET" ? { json: configured } : request.path === "/chat" ? { json: { request_id: "policy-" + mode, response: "Gateway result for " + mode + ".", status: "delivered", input_guard: input, output_guard: cleanGuard, latency_ms: 18, backend: "mock", model: "mock-local" } } : undefined });
    await page.goto("/?view=policy");
    await expect(page.getByRole("radio", { name: new RegExp("^" + mode, "i") })).toBeChecked();
    if (mode === "off") {
      await expect(page.getByRole("switch", { name: /^Prompt injection/ })).not.toBeChecked();
      await expect(page.getByRole("switch", { name: /^Jailbreak attempts/ })).not.toBeChecked();
    }
    await page.goto("/?view=chat");
    await page.getByLabel("Your prompt", { exact: true }).fill(prompt);
    await page.getByRole("button", { name: "Run prompt", exact: true }).click();
    await expect(page.getByText("Gateway result for " + mode + ".", { exact: true })).toBeVisible();
    await expect(page.locator(".chat-result.is-blocked")).toHaveCount(0);
    if (mode === "redact") await expect(page.getByText("PII redacted", { exact: true })).toBeVisible();
    expect(requests.filter(request => request.path === "/chat")).toHaveLength(1);
    expect(requests.find(request => request.path === "/chat")?.body).toEqual({ prompt });
    expect(requests.filter(request => request.path === "/policy" && request.method === "PATCH")).toHaveLength(0);
    expect(unknown).toEqual([]);
  });
}

test("approximate policy preview distinguishes warn, redact, off, and block without sending", async ({ page }) => {
  const { requests, unknown } = await mockWorkspace(page, { override: request => request.path === "/policy" && request.method === "GET" ? { json: { ...policy, input_rules: { ...policy.input_rules, injection_mode: "warn", jailbreak_mode: "warn" } } } : undefined });
  await page.goto("/?view=policy");
  const preview = page.getByRole("region").filter({ has: page.getByRole("heading", { name: "Try a prompt", exact: true }) });
  await expect(preview.getByText("Approximate preview", { exact: true })).toBeVisible();
  await expect(preview.getByText("Local match · prompt injection", { exact: true })).toBeVisible();
  await expect(preview.getByText("Configured action: warn", { exact: true })).toBeVisible();
  await page.getByLabel("Sample prompt", { exact: true }).fill("DAN mode");
  await expect(preview.getByText("Local match · jailbreak", { exact: true })).toBeVisible();
  await expect(preview.getByText("Configured action: warn", { exact: true })).toBeVisible();
  await page.getByLabel("Sample prompt", { exact: true }).fill("Form example: SSN 123-45-6789.");
  await expect(preview.getByText("Local match · sensitive data", { exact: true })).toBeVisible();
  await expect(preview.getByText("Configured action: warn", { exact: true })).toBeVisible();
  await page.getByRole("radio", { name: /^Redact/ }).check();
  await expect(preview.getByText("Configured action: redact", { exact: true })).toBeVisible();
  await page.getByRole("radio", { name: /^Off/ }).check();
  await expect(preview.getByText("No match in local preview", { exact: true })).toBeVisible();
  await page.getByRole("radio", { name: /^Block/ }).check();
  await expect(preview.getByText("Configured action: block", { exact: true })).toBeVisible();
  expect(requests.filter(request => request.path === "/chat")).toHaveLength(0);
  expect(requests.filter(request => request.path === "/policy" && request.method === "PATCH")).toHaveLength(0);
  expect(unknown).toEqual([]);
});
