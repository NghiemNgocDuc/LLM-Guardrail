import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mkdir } from "node:fs/promises";
import { mockWorkspace } from "./fixtures";

test.setTimeout(60_000);
test.use({ reducedMotion: "reduce" });

const views = ["dashboard", "chat", "skills", "memory", "mandate", "analytics", "logs", "health", "keys", "policy", "teams", "team", "billing", "admin", "settings", "profile", "about"];

test("the sign-in introduction explains the project without submitting or losing the form", async ({ page }, info) => {
  const apiRequests: string[] = [];
  await page.route("**/*", async route => {
    const request = route.request(), url = new URL(request.url());
    if (/posthog|sentry/i.test(url.hostname)) return route.abort();
    if (/^\/(auth|analytics|chat|feedback|billing|org)(\/|$)/.test(url.pathname)) {
      apiRequests.push(request.method() + " " + url.pathname);
      return route.fulfill({ status: 200, json: {} });
    }
    return route.continue();
  });
  await page.goto("/");
  const email = page.getByLabel("Email address", { exact: true });
  await email.fill("reviewer@example.com");
  const trigger = page.getByRole("button", { name: "What is LLM Guardrail?", exact: true });
  await trigger.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "Meet LLM Guardrail", exact: true });
  await expect(dialog).toBeVisible();
  await mkdir("test-results/previews", { recursive: true });
  await page.screenshot({ path: `test-results/previews/project-intro-${info.project.name}.png` });
  const explanation = await dialog.evaluate(element => (element.getAttribute("aria-describedby") || "").split(/\s+/).map(id => document.getElementById(id)?.textContent || "").join(" "));
  expect(explanation.length).toBeGreaterThan(40);
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(trigger).toBeFocused();
  await expect(email).toHaveValue("reviewer@example.com");
  expect(apiRequests).toEqual([]);
});

test("every workspace page offers contextual help without changing workspace data", async ({ page }) => {
  const mocks = await mockWorkspace(page);
  const explanations = new Set<string>();
  for (const view of views) {
    await page.goto("/?view=" + view);
    await expect(page.locator("main h1")).toBeVisible();
    const trigger = page.getByRole("button", { name: "Help with this page", exact: true });
    await trigger.click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog).toHaveAccessibleName("Help with " + await page.getByRole("main", { includeHidden: true }).getAttribute("aria-label"));
    const explanation = await dialog.evaluate(element => (element.getAttribute("aria-describedby") || "").split(/\s+/).map(id => document.getElementById(id)?.textContent || "").join(" "));
    expect(explanation.length).toBeGreaterThan(40);
    explanations.add(explanation);
    await expect(dialog.getByRole("link", { name: "Open full guide", exact: true })).toHaveAttribute("href", "?view=about");
    await page.keyboard.press("Escape");
    await expect(dialog).not.toBeVisible();
    await expect(trigger).toBeFocused();
    await expect(page).toHaveURL(new RegExp("view=" + view + "$"));
  }
  expect(explanations.size).toBe(views.length);
  expect(mocks.requests.filter(request => request.method !== "GET")).toEqual([]);
  expect(mocks.unknown).toEqual([]);
});

test("page help supports keyboard entry, contains focus, and restores it on Escape", async ({ page }) => {
  await mockWorkspace(page);
  await page.goto("/?view=dashboard");
  const trigger = page.getByRole("button", { name: "Help with this page", exact: true });
  await trigger.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  for (const key of ["Tab", "Tab", "Tab", "Tab", "Tab", "Tab", "Shift+Tab", "Shift+Tab", "Shift+Tab", "Shift+Tab", "Shift+Tab", "Shift+Tab"]) {
    await page.keyboard.press(key);
    expect(await dialog.evaluate(element => element.contains(document.activeElement))).toBe(true);
  }
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(trigger).toBeFocused();
});

test("page help fits the viewport and is accessible in both themes", async ({ page }, info) => {
  await mockWorkspace(page);
  await page.goto("/?view=dashboard");
  await mkdir("test-results/previews", { recursive: true });
  for (const theme of ["light", "dark"]) {
    if (theme === "dark") await page.getByRole("button", { name: "Switch to dark theme" }).click();
    await page.getByRole("button", { name: "Help with this page", exact: true }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await page.screenshot({ path: `test-results/previews/help-${theme}-${info.project.name}.png` });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect(await dialog.evaluate(element => {
      const bounds = element.getBoundingClientRect();
      return bounds.left >= 0 && bounds.right <= innerWidth && bounds.top >= 0 && bounds.bottom <= innerHeight && element.scrollWidth <= element.clientWidth;
    })).toBe(true);
    const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
    expect(result.violations.map(item => ({ id: item.id, nodes: item.nodes.map(node => ({ target: node.target, summary: node.failureSummary })) }))).toEqual([]);
    await page.keyboard.press("Escape");
  }
});

test("the full guide opens from page help and browser back restores the original page", async ({ page }) => {
  const mocks = await mockWorkspace(page);
  await page.goto("/?view=skills");
  await page.getByRole("button", { name: "Help with this page", exact: true }).click();
  await page.getByRole("dialog").getByRole("link", { name: "Open full guide", exact: true }).click();
  await expect(page).toHaveURL(/view=about$/);
  await expect(page.getByRole("heading", { name: "What does this project do?", exact: true })).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.goBack();
  await expect(page).toHaveURL(/view=skills$/);
  await expect(page.getByRole("main", { name: "Skill Guard", exact: true })).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(mocks.requests.filter(request => request.method !== "GET")).toEqual([]);
});

test("contextual help suggests a useful next page without running an AI request", async ({ page }) => {
  const mocks = await mockWorkspace(page);
  await page.goto("/?view=dashboard");
  await page.getByRole("button", { name: "Help with this page", exact: true }).click();
  const nextStep = page.getByRole("dialog").getByRole("link", { name: "Try your first prompt", exact: true });
  await expect(nextStep).toHaveAttribute("href", "?view=chat");
  await nextStep.click();
  await expect(page).toHaveURL(/view=chat$/);
  await expect(page.getByRole("heading", { name: "LLM Playground", exact: true })).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.goBack();
  await expect(page.getByRole("main", { name: "Overview", exact: true })).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(mocks.requests.filter(request => request.method !== "GET")).toEqual([]);
});

test("the beginner guide provides working task links and a discoverable navigation entry", async ({ page }, info) => {
  const mocks = await mockWorkspace(page);
  await page.goto("/?view=about");
  await expect(page.getByRole("heading", { name: "What would you like to do?", exact: true })).toBeVisible();
  await mkdir("test-results/previews", { recursive: true });
  await page.screenshot({ path: `test-results/previews/getting-started-${info.project.name}.png` });
  for (const [label, view] of [["Try a safe first prompt", "chat"], ["Check an agent skill", "skills"], ["Choose what gets checked", "policy"], ["Understand a decision", "logs"]]) {
    const link = page.getByRole("navigation", { name: "Getting started tasks", exact: true }).getByRole("link", { name: new RegExp("^" + label + "\\b") });
    await expect(link).toHaveAttribute("href", "?view=" + view);
    await link.click();
    await expect(page).toHaveURL(new RegExp("view=" + view + "$"));
    await expect(page.locator("main h1")).toBeVisible();
    await page.goBack();
    await expect(page).toHaveURL(/view=about$/);
  }
  if (info.project.name === "mobile") await page.getByRole("button", { name: "Open navigation" }).click();
  await expect(page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "Help & getting started", exact: true })).toHaveAttribute("aria-current", "page");
  expect(mocks.requests.filter(request => request.method !== "GET")).toEqual([]);
  expect(mocks.unknown).toEqual([]);
});
