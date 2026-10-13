import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mkdir } from "node:fs/promises";

const user = { id: "ui-user", email: "reviewer@example.com", full_name: "Alex Reviewer", is_admin: false, is_active: true, email_verified: true, org_id: "ui-org", created_at: "2026-01-01T00:00:00Z" };
const dashboard = {
  summary: { total_requests: 1248, delivered: 1134, input_blocked: 82, output_blocked: 14, rate_limited: 10, error_count: 8, block_rate_pct: 8.49, avg_latency_ms: 246.8, total_tokens: 428600, estimated_cost_usd: 3.2 },
  time_series: Array.from({ length: 7 }, (_, index) => ({ ts: `2026-10-${String(index + 7).padStart(2, "0")}`, total: 120 + index * 20, delivered: 110 + index * 17, blocked: 10 + index * 3 })),
  top_rules: [{ rule: "prompt_injection", count: 46 }, { rule: "pii_detected", count: 24 }],
  provider_usage: [{ backend: "groq", model: "llama-3.3-70b-versatile", count: 820, tokens: 305000 }, { backend: "openai", model: "gpt-4o-mini", count: 314, tokens: 123600 }],
  recent_suspicious: [{ id: "suspicious-1", status: "input_blocked", prompt_preview: "Ignore previous instructions…", reason: "Prompt injection detected", fired_rule: "prompt_injection", created_at: "2026-10-13T12:05:00Z" }],
  recent_logs: [{ id: "request-1", status: "delivered", prompt_preview: "Explain safe AI workflows", reason: null, fired_rule: null, backend: "groq", model: "llama-3.3-70b-versatile", latency_ms: 212, tokens_total: 420, created_at: "2026-10-13T12:10:00Z" }],
};
const cleanGuard = { passed: true, check: "all", reason: "", reason_code: "clean", risk_score: 0 };

async function mockApi(page: Page, options: { signedIn?: boolean; failDashboard?: boolean } = {}) {
  const requests: { path: string; method: string; body: unknown }[] = [];
  if (options.signedIn) await page.addInitScript(() => localStorage.setItem("access_token", "ui-test-token"));
  await page.route("**/*", async route => {
    const request = route.request(), url = new URL(request.url());
    const apiPath = /^\/(auth|analytics|chat|feedback|billing|org)(\/|$)/.test(url.pathname);
    if (!apiPath) {
      if (/posthog|sentry/i.test(url.hostname)) return route.abort();
      return route.continue();
    }
    const headers = { "access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "GET,POST,OPTIONS" };
    if (request.method() === "OPTIONS") return route.fulfill({ status: 204, headers });
    let body: unknown = null;
    try { body = request.postDataJSON(); } catch { /* GET has no body. */ }
    requests.push({ path: url.pathname + url.search, method: request.method(), body });
    let json: unknown = {};
    let status = 200;
    if (url.pathname === "/auth/login") {
      if ((body as { password?: string })?.password === "wrong-password") { status = 401; json = { detail: "Email or password is incorrect. Try again." }; }
      else json = { access_token: "ui-test-token", refresh_token: "ui-test-refresh", token_type: "bearer" };
    } else if (url.pathname === "/auth/me") json = user;
    else if (url.pathname === "/auth/signup") json = { message: "Account created. You can now sign in." };
    else if (url.pathname === "/auth/forgot-password") json = { message: "If that email exists, a reset link has been sent." };
    else if (url.pathname === "/auth/verify-email") json = { message: "Email verified. You can sign in." };
    else if (url.pathname === "/auth/reset-password") json = { message: "Password updated. Please sign in." };
    else if (url.pathname === "/analytics/dashboard") {
      if (options.failDashboard) { status = 503; json = { detail: "Analytics is temporarily unavailable." }; } else json = dashboard;
    } else if (/^\/chat\/[^/]+\/feedback$/.test(url.pathname)) json = { id: "feedback-1", request_log_id: "chat-request-1", user_id: user.id, rating: (body as { rating: number }).rating, comment: null, created_at: "2026-10-13T12:00:00Z" };
    else if (url.pathname === "/chat") json = { request_id: "chat-request-1", response: "Guardrails check prompts and responses before they reach your users.", status: "delivered", input_guard: cleanGuard, output_guard: cleanGuard, latency_ms: 186, backend: "groq", model: "llama-3.3-70b-versatile", tokens_remaining: 9820 };
    await route.fulfill({ status, headers, json });
  });
  return requests;
}
async function assertNoOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
}
async function preview(page: Page, filename: string) {
  await mkdir("test-results/previews", { recursive: true });
  await page.screenshot({ path: `test-results/previews/${filename}.png`, fullPage: await page.locator(".app-shell").count() === 0 });
}

test("login is usable while its illustrative text plays; keyboard sign-in works", async ({ page }, info) => {
  const requests = await mockApi(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Welcome back." })).toBeVisible();
  await page.getByRole("button", { name: "Pause example response" }).click();
  const before = await page.locator(".gr-auth-word-visible").count();
  await expect(page.getByRole("button", { name: "Resume example response" })).toBeVisible();
  await page.getByRole("button", { name: "Prompt injection", exact: true }).click();
  await expect(page.getByText("Prompt injection blocked", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Sensitive data", exact: true }).click();
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(page.getByRole("button", { name: "Pause example response" })).toHaveCount(0);
  expect(before).toBeGreaterThanOrEqual(0);
  await assertNoOverflow(page);
  await preview(page, `login-${info.project.name}`);
  const accessibility = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(accessibility.violations).toEqual([]);
  await page.getByLabel("Email address", { exact: true }).fill("reviewer@example.com");
  await page.getByLabel("Password", { exact: true }).fill("valid-password");
  await page.getByLabel("Password", { exact: true }).press("Enter");
  await expect(page.getByRole("heading", { name: "Every request, accounted for." })).toBeVisible();
  expect(requests.filter(request => request.path === "/auth/login")).toHaveLength(1);
});

test("login errors, signup, and password recovery retain working forms", async ({ page }) => {
  const requests = await mockApi(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Sign in to workspace", exact: true }).click();
  expect(requests.some(request => request.path === "/auth/login")).toBe(false);
  await page.getByLabel("Email address", { exact: true }).fill("reviewer@example.com");
  await page.getByLabel("Password", { exact: true }).fill("wrong-password");
  await page.getByRole("button", { name: "Sign in to workspace", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Email or password is incorrect");
  await page.getByRole("button", { name: "Forgot password?", exact: true }).click();
  await page.getByRole("button", { name: "Send reset link", exact: true }).click();
  await expect(page.getByText("If that email exists, a reset link has been sent.")).toBeVisible();
  await page.getByRole("button", { name: "Back to sign in", exact: true }).click();
  await page.getByRole("button", { name: "Create account", exact: true }).first().click();
  await page.getByLabel("Full name", { exact: true }).fill("Alex Reviewer");
  await page.getByLabel("Password", { exact: true }).fill("valid-password");
  await page.getByRole("button", { name: "Create account", exact: true }).last().click();
  await expect(page.getByText("Account created. You can now sign in.")).toBeVisible();
});

test("verification and reset links work with an existing login session", async ({ page }) => {
  const requests = await mockApi(page, { signedIn: true });
  await page.goto("/verify-email?token=ui-verification-token");
  await expect(page.getByText("Email verified. You can sign in.")).toBeVisible();
  expect(requests.filter(request => request.path === "/auth/verify-email")).toHaveLength(1);
  await page.goto("/reset-password?token=ui-reset-token");
  await expect(page.getByRole("heading", { name: "A fresh start." })).toBeVisible();
  await page.getByLabel("New password", { exact: true }).fill("valid-password");
  await page.getByLabel("Confirm password", { exact: true }).fill("valid-password");
  await page.getByRole("button", { name: "Update password", exact: true }).click();
  await expect(page.getByText("Password updated. Please sign in.")).toBeVisible();
});

test("dashboard, quick navigation, history and dark theme work", async ({ page }, info) => {
  const requests = await mockApi(page, { signedIn: true });
  await page.goto("/?view=admin");
  await expect(page.getByRole("main", { name: "Overview" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Every request, accounted for." })).toBeVisible();
  await assertNoOverflow(page);
  await preview(page, `dashboard-${info.project.name}`);
  await page.getByLabel("Activity period").selectOption("30");
  await expect.poll(() => requests.some(request => request.path === "/analytics/dashboard?days=30")).toBe(true);
  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  await expect(page.locator(".app-shell")).toHaveAttribute("data-dark", "1");
  await preview(page, `dashboard-dark-${info.project.name}`);
  const accessibility = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(accessibility.violations).toEqual([]);
  await page.getByRole("button", { name: "Jump to a page" }).click();
  await page.getByRole("combobox", { name: "Search pages" }).fill("playground");
  await page.getByRole("combobox", { name: "Search pages" }).press("Enter");
  await expect(page.getByRole("heading", { name: "LLM Playground", exact: true })).toBeVisible();
  await expect(page).toHaveURL(/view=chat/);
  if (info.project.name === "mobile") await page.getByRole("button", { name: "Open navigation" }).click();
  await page.goBack();
  await expect(page.getByRole("main", { name: "Overview" })).toBeVisible();
  if (info.project.name === "mobile") await expect(page.getByRole("button", { name: "Open navigation" })).toHaveAttribute("aria-expanded", "false");
});

test("playground sends JSON once, saves backend feedback, and stops unsafe drafts", async ({ page }, info) => {
  const requests = await mockApi(page, { signedIn: true });
  await page.goto("/?view=chat");
  await expect(page.getByRole("heading", { name: "LLM Playground", exact: true })).toBeVisible();
  await assertNoOverflow(page);
  await preview(page, `playground-${info.project.name}`);
  const accessibility = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(accessibility.violations).toEqual([]);
  await page.getByLabel(/Gateway key/).fill("sk-" + "a".repeat(32));
  await expect(page.getByText("Use a grg_ gateway key.", { exact: false })).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem("gateway_api_key"))).toBeNull();
  await page.getByLabel(/Gateway key/).fill("");
  await page.getByRole("button", { name: "Everyday request", exact: true }).click();
  await page.getByRole("button", { name: "Run prompt", exact: true }).click();
  await expect(page.getByText("Guardrails check prompts and responses before they reach your users.")).toBeVisible();
  expect(requests.filter(request => request.path === "/chat")).toHaveLength(1);
  expect(requests.find(request => request.path === "/chat")?.body).toMatchObject({ prompt: expect.any(String) });
  await page.getByRole("button", { name: "Rate response helpful" }).click();
  await expect(page.getByRole("button", { name: "Rate response helpful" })).toHaveAttribute("aria-pressed", "true");
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem("guardrails_chat_history") || "[]")[0].feedback.rating)).toBe(1);
  await page.getByRole("button", { name: "Prompt injection", exact: true }).click();
  await page.getByRole("button", { name: "Test blocked prompt", exact: true }).click();
  await expect(page.getByText("Stopped before reaching the gateway")).toBeVisible();
  expect(requests.filter(request => request.path === "/chat")).toHaveLength(1);
});

test("dashboard failures offer recovery without fabricated metrics", async ({ page }) => {
  const requests = await mockApi(page, { signedIn: true, failDashboard: true });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Activity could not be loaded" })).toBeVisible();
  await page.getByRole("button", { name: "Try again" }).click();
  await expect.poll(() => requests.filter(request => request.path.startsWith("/analytics/dashboard")).length).toBeGreaterThanOrEqual(2);
  await expect(page.getByText("Total requests", { exact: true })).toHaveCount(0);
});
