import { expect, test } from "@playwright/test";
import { mockWorkspace } from "./fixtures";

test.skip(!process.env.PW_PRIVATE_MODE, "Run with playwright.private.config.ts and PW_PRIVATE_MODE=1");

test("private playground keeps blocked and delivered content only in this tab", async ({ page }) => {
  const workspace = await mockWorkspace(page);
  const telemetry: string[] = [];
  page.on("request", request => { if (/posthog|sentry|telemetry\.example|fonts\.googleapis|fonts\.gstatic/i.test(new URL(request.url()).hostname)) telemetry.push(request.url()); });
  const legacy = JSON.stringify([{ prompt: "Old private project codename Moonlight", result: { error: "Older stored run" }, ts: 1 }]);
  await page.addInitScript(value => localStorage.setItem("guardrails_chat_history", value), legacy);
  await page.goto("/?view=chat", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "LLM Playground", exact: true })).toBeVisible();
  await expect(page.getByText("Old private project codename Moonlight", { exact: true })).toHaveCount(0);
  await expect(page.getByText(/Conversation history stays in this tab/)).toBeVisible();
  await page.getByLabel("Your prompt", { exact: true }).fill("Private client record: SSN 123-45-6789");
  await page.getByRole("button", { name: "Test blocked prompt", exact: true }).click();
  await expect(page.getByText("Client blocked", { exact: true })).toBeVisible();
  expect(workspace.requests.some(request => request.path === "/chat")).toBe(false);
  await page.getByLabel("Your prompt", { exact: true }).fill("Explain local model hosting.");
  await page.getByRole("button", { name: "Run prompt", exact: true }).click();
  await expect(page.locator(".chat-run-number")).toHaveCount(2);
  expect(await page.evaluate(() => localStorage.getItem("guardrails_chat_history"))).toBe(legacy);
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "LLM Playground", exact: true })).toBeVisible();
  await expect(page.locator(".chat-run-number")).toHaveCount(0);
  await page.getByRole("button", { name: "Clear history", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Clear history", exact: true }).click();
  expect(await page.evaluate(() => localStorage.getItem("guardrails_chat_history"))).toBeNull();
  expect(telemetry).toEqual([]);
});

test("private policy editor disables external routing and full prompt storage", async ({ page }) => {
  const workspace = await mockWorkspace(page);
  await page.goto("/?view=policy", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "Policies", exact: true })).toBeVisible();
  await expect(page.getByText(/Private mode uses the server's local model/)).toBeVisible();
  await expect(page.getByLabel("Backend", { exact: true })).toBeDisabled();
  const options = await page.locator("#policy-backend option").evaluateAll(elements => elements.map(element => (element as HTMLOptionElement).value));
  expect(options).toEqual(["", "ollama"]);
  await expect(page.getByLabel("Model identifier", { exact: true })).toBeDisabled();
  await expect(page.getByRole("switch", { name: /Full prompt logging/ })).not.toBeChecked();
  await expect(page.getByRole("switch", { name: /Full prompt logging/ })).toBeDisabled();
  await expect(page.getByLabel("Webhook URL", { exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Save changes", exact: true }).first().click();
  await expect(page.getByText("Policy saved. New requests will use the updated configuration.", { exact: true })).toBeVisible();
  const saved = workspace.requests.find(request => request.path === "/policy" && request.method === "PATCH")!.body;
  expect(saved.llm_backend).toBeNull();
  expect(saved.llm_model).toBeNull();
  expect(saved.compliance_rules.full_prompt_logging).toBe(false);
  expect(saved.compliance_rules.webhook_url).toBe("");
});
