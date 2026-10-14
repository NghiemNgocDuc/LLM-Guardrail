import { expect, test } from "@playwright/test";
import { mockWorkspace } from "./fixtures";

test("settings section links scroll within the workspace without changing the page", async ({ page }) => {
  await mockWorkspace(page);
  await page.goto("/?view=settings");
  await page.getByRole("navigation", { name: "Settings sections" }).getByRole("link", { name: "Password", exact: true }).click();
  await expect(page).toHaveURL(/view=settings#settings-password$/);
  await expect.poll(() => page.locator("main").evaluate(main => main.scrollTop)).toBeGreaterThan(100);
  await expect(page.getByRole("heading", { name: "Make this workspace yours.", exact: true })).toHaveCount(1);
});

test("playground confirmation keeps keyboard focus, supports Escape and respects reduced motion", async ({ page }) => {
  await mockWorkspace(page);
  await page.addInitScript(() => localStorage.setItem("guardrails_chat_history", JSON.stringify([{ prompt: "Unsafe example", result: { clientBlocked: true, reason: "Stopped by local policy" }, ts: Date.now() }])));
  await page.goto("/?view=chat");
  const trigger = page.getByRole("button", { name: "Clear history", exact: true });
  await trigger.click();
  const dialog = page.getByRole("dialog", { name: "Clear conversation history?", exact: true });
  await expect(dialog).toBeVisible();
  for (let index = 0; index < 6; index++) {
    await page.keyboard.press("Tab");
    expect(await page.evaluate(() => Boolean(document.activeElement?.closest("dialog[open]")))).toBe(true);
  }
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(trigger).toBeFocused();
  await expect(page.locator(".chat-result")).toHaveCount(1);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await trigger.click();
  expect(await dialog.evaluate(element => getComputedStyle(element).animationName)).toBe("none");
  await dialog.getByRole("button", { name: "Clear history", exact: true }).click();
  await expect(page.locator(".chat-result")).toHaveCount(0);
  expect(await page.evaluate(() => localStorage.getItem("guardrails_chat_history"))).toBeNull();
});

test("documentation tabs, measured evidence, downloads, and feedback work", async ({ page }) => {
  const mocks = await mockWorkspace(page);
  await page.goto("/?view=about");
  await page.getByRole("tab", { name: "Quickstart", exact: true }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("tab", { name: "Gateway API" })).toBeFocused();
  await expect(page.getByRole("tabpanel")).toContainText("/auth/login");
  await page.getByRole("tab", { name: "Evidence & benchmarks" }).click();
  await expect(page.getByText("Leak recall", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Run combined benchmark", exact: true }).click();
  await expect(page.getByRole("tabpanel")).toContainText('"macro_f1": 0.94');
  const downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export evidence PDF" }).click();
  expect((await downloaded).suggestedFilename()).toBe("guardrail-evidence-pack.pdf");
  await page.getByLabel("Your feedback", { exact: true }).fill("Please make the audit export configurable.");
  await page.getByRole("button", { name: "Send feedback", exact: true }).click();
  await expect(page.getByText("Your feedback was sent.", { exact: false })).toBeVisible();
  expect(mocks.requests.find(item => item.path === "/feedback")?.body).toMatchObject({ category: "general", message: expect.any(String) });
  expect(mocks.unknown).toEqual([]);
});

test("MandateFlow verifies actual denial, retry, receipts, revocation and timings", async ({ page }) => {
  const mocks = await mockWorkspace(page);
  await page.goto("/?view=mandate");
  await page.getByRole("button", { name: "Run 10-call demo" }).click();
  await expect(page.getByText("Demo complete.", { exact: false })).toBeVisible();
  await expect(page.getByText("Revoked capability rejected with HTTP 401", { exact: true })).toBeVisible();
  expect(mocks.requests.filter(item => item.path === "/gateway/call")).toHaveLength(12);
  expect(mocks.requests.find(item => item.path === "/mandate")?.body.scopes).toHaveLength(5);
  await page.getByRole("button", { name: "Run benchmark", exact: true }).click();
  await expect(page.getByText("Measured Go / Python speedup: 2.10×.", { exact: true })).toBeVisible();
  expect(mocks.unknown).toEqual([]);
});

test("MandateFlow never labels a provider error as successful revocation", async ({ page }) => {
  let revoked = false;
  await mockWorkspace(page, { override: request => {
    if (request.path.endsWith("/revoke")) revoked = true;
    if (request.path === "/gateway/call" && revoked) return { status: 503, json: { detail: "Gateway unavailable" } };
  } });
  await page.goto("/?view=mandate");
  await page.getByRole("button", { name: "Run 10-call demo" }).click();
  await expect(page.getByRole("alert")).toContainText("Gateway unavailable");
  await expect(page.getByText("Demo complete.", { exact: false })).toHaveCount(0);
});
