import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { log, memory, mockWorkspace, user } from "./fixtures";

test("memory edits, pins, recalls and archives through deliberate dialogs", async ({ page }) => {
  const { requests, unknown } = await mockWorkspace(page);
  await page.goto("/?view=memory");
  await page.getByRole("button", { name: "New memory", exact: true }).click();
  const editor = page.getByRole("dialog", { name: "Create a memory", exact: true });
  await editor.getByLabel("Title", { exact: true }).fill("Project conventions");
  await editor.getByLabel("Memory content", { exact: true }).fill("Use readable names and explicit errors.");
  await editor.getByLabel("Category", { exact: true }).selectOption("procedure");
  await editor.getByLabel("Importance", { exact: true }).selectOption("4");
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze()).violations).toEqual([]);
  await editor.getByRole("button", { name: "Save memory", exact: true }).click();
  await expect(editor).not.toBeVisible();
  expect(requests.find(item => item.path === "/memories" && item.method === "POST")?.body).toMatchObject({ title: "Project conventions", category: "procedure", importance: 4, pinned: false, kind: "user" });
  await page.getByRole("button", { name: "Edit memory", exact: true }).click();
  const edit = page.getByRole("dialog", { name: "Edit memory", exact: true });
  await edit.getByLabel("Memory content", { exact: true }).fill("Use descriptive names and actionable errors.");
  await edit.getByRole("button", { name: "Save memory", exact: true }).click();
  await expect(edit).not.toBeVisible();
  await expect(page.locator(".memory-content")).toContainText("actionable errors");
  await page.locator(".memory-detail-actions").getByRole("button", { name: "Pin to context", exact: true }).click();
  await expect(page.locator(".memory-detail")).toContainText("Pinned to context");
  await page.getByLabel("Recall query", { exact: true }).fill("What are the project conventions?");
  await page.getByRole("button", { name: "Recall", exact: true }).click();
  await expect(page.locator(".memory-recall-results")).toContainText("Project conventions");
  expect(requests.find(item => item.path === "/memories/recall")?.body).toEqual({ query: "What are the project conventions?", top_k: 6 });
  await page.getByRole("button", { name: "Archive", exact: true }).click();
  const archive = page.getByRole("dialog", { name: "Archive this memory?", exact: true });
  await archive.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(archive).not.toBeVisible();
  expect(requests.filter(item => item.method === "DELETE")).toHaveLength(0);
  await page.getByRole("button", { name: "Archive", exact: true }).click();
  await archive.getByRole("button", { name: "Archive memory", exact: true }).click();
  await expect(page.getByText("Memory archived", { exact: true })).toBeVisible();
  expect(requests.filter(item => item.method === "DELETE")).toHaveLength(1);
  await expect(page.locator(".memory-recall-results")).not.toContainText("Project conventions");
  expect(unknown).toEqual([]);
});

test("memory search, filters, and extraction preserve review before saving", async ({ page }) => {
  const { requests, unknown } = await mockWorkspace(page);
  await page.addInitScript(() => localStorage.setItem("guardrails_chat_history", JSON.stringify([{ prompt: "Please use examples", result: { response: "I'll use concrete examples." }, ts: Date.now() }])));
  await page.goto("/?view=memory");
  await page.getByLabel("Search memories", { exact: true }).fill("does-not-exist");
  await expect(page.getByRole("heading", { name: "No memories match your filters" })).toBeVisible();
  await page.getByRole("button", { name: "Reset filters", exact: true }).first().click();
  await expect(page.locator(".memory-card")).toHaveCount(1);
  await page.getByLabel("Pinned only", { exact: true }).check();
  await expect.poll(() => requests.some(item => item.path.includes("pinned_only=true"))).toBe(true);
  await page.getByRole("button", { name: "Extract from last chat", exact: true }).click();
  const review = page.getByRole("dialog", { name: "Review extracted memories", exact: true });
  await expect(review).toContainText("Communication preference");
  expect(requests.some(item => item.path === "/memories/extract/confirm")).toBe(false);
  await review.getByRole("checkbox").uncheck();
  await expect(review.getByRole("button", { name: "Save 0 memories", exact: true })).toBeDisabled();
  await review.getByRole("checkbox").check();
  await review.getByRole("button", { name: "Save 1 memory", exact: true }).click();
  await expect(review).not.toBeVisible();
  expect(requests.filter(item => item.path === "/memories/extract/confirm")).toHaveLength(1);
  expect(requests.find(item => item.path === "/memories/extract/confirm")?.body.items).toHaveLength(1);
  expect(unknown).toEqual([]);
});

test("analytics uses the selected period, numeric sorting and authenticated downloads", async ({ page }) => {
  const { requests, unknown } = await mockWorkspace(page, { override: item => item.path.startsWith("/analytics/users?") ? { json: [{ id: "a", email: "a@example.com", full_name: "A", requests: 9, blocked: 0, tokens_used_lifetime: 100, tokens_balance: 20 }, { id: "b", email: "b@example.com", full_name: "B", requests: 100, blocked: 2, tokens_used_lifetime: 1000, tokens_balance: 900 }] } : undefined });
  await page.goto("/?view=analytics");
  await page.getByRole("button", { name: "7 days", exact: true }).click();
  await expect.poll(() => requests.some(item => item.path === "/analytics/dashboard?days=7")).toBe(true);
  const usage = page.getByRole("region", { name: "Per-user usage", exact: true });
  await expect(usage.locator("tbody tr").first()).toContainText("b@example.com");
  await usage.getByRole("button", { name: /^Requests/ }).click();
  await expect(usage.locator("tbody tr").first()).toContainText("a@example.com");
  await page.getByText("View daily data table", { exact: true }).click();
  await expect(page.locator(".obs-chart-data .ui-table-wrap")).toBeVisible();
  const downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export CSV", exact: true }).click();
  expect((await downloaded).suggestedFilename()).toBe("guardrails-logs-7d.csv");
  expect(requests.find(item => item.path === "/analytics/export?days=7")?.authorization).toBe("Bearer ui-test-token");
  expect(unknown).toEqual([]);
});

test("logs filter and page actual results, inspect decisions and export the chosen window", async ({ page }, info) => {
  const { requests, unknown } = await mockWorkspace(page, { override: item => {
    if (!item.path.startsWith("/analytics/logs?")) return;
    const currentPage = Number(new URL(item.path, "http://localhost").searchParams.get("page"));
    return { json: { total: 26, items: [{ ...log, id: "request-" + currentPage, prompt_preview: "Audit page " + currentPage }], page: currentPage, page_size: 25 } };
  } });
  await page.goto("/?view=logs");
  await page.getByLabel("Live updates", { exact: true }).uncheck();
  await expect(page.getByText("Paused", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect(page.getByText("Page 2 of 2", { exact: true })).toBeVisible();
  await page.getByLabel("Search request logs", { exact: true }).fill("Audit");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await page.getByRole("button", { name: "input blocked", exact: true }).click();
  await page.getByRole("button", { name: /^Filters/ }).click();
  await page.getByLabel("From date", { exact: true }).fill("2026-10-01");
  await page.getByLabel("To date", { exact: true }).fill("2026-10-13");
  await page.getByLabel("Provider", { exact: true }).fill("groq");
  await expect.poll(() => requests.some(item => item.path.startsWith("/analytics/logs?") && ["keyword=Audit", "status_filter=input_blocked", "date_from=2026-10-01", "date_to=2026-10-13", "backend_filter=groq", "page=1"].every(part => item.path.includes(part)))).toBe(true);
  const visibleRows = page.locator(info.project.name === "mobile" ? ".obs-log-mobile" : ".obs-log-desktop");
  await visibleRows.getByRole("button", { name: "Details", exact: true }).click();
  const detail = info.project.name === "mobile" ? page.getByRole("dialog", { name: "Request details", exact: true }) : page.locator(".obs-expanded-cell");
  await expect(detail).toContainText("req-ui-1");
  await expect(detail).toContainText("Input check");
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze()).violations).toEqual([]);
  if (info.project.name === "mobile") await detail.getByRole("button", { name: "Close dialog", exact: true }).click();
  await page.getByLabel("CSV export window", { exact: true }).selectOption("7");
  const downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export CSV", exact: true }).click();
  expect((await downloaded).suggestedFilename()).toBe("guardrails-logs-7d.csv");
  expect(requests.find(item => item.path === "/analytics/export?days=7")?.authorization).toBe("Bearer ui-test-token");
  expect(unknown).toEqual([]);
});

test("live request notifications authenticate the real org and refetch complete API data", async ({ page }) => {
  const { requests, unknown } = await mockWorkspace(page);
  let socket: import("@playwright/test").WebSocketRoute | undefined;
  let joined = "", socketUrl = "";
  await page.routeWebSocket("**/live-feed/websocket*", route => {
    socket = route; socketUrl = route.url();
    route.onMessage(message => { const [, ref, topic, event] = JSON.parse(String(message)); if (event === "phx_join") { joined = topic; route.send(JSON.stringify([null, ref, topic, "phx_reply", { status: "ok", response: {} }])); } });
  });
  await page.goto("/?view=logs");
  await expect(page.getByText("Connected", { exact: true })).toBeVisible();
  expect(joined).toBe("requests:" + user.org_id);
  expect(new URL(socketUrl).searchParams.get("token")).toBe("ui-test-token");
  expect(new URL(socketUrl).searchParams.get("vsn")).toBe("2.0.0");
  const before = requests.filter(item => item.path.startsWith("/analytics/logs?")).length;
  socket!.send(JSON.stringify([null, null, joined, "new_request", { id: "notification-only" }]));
  await expect.poll(() => requests.filter(item => item.path.startsWith("/analytics/logs?")).length).toBeGreaterThan(before);
  await expect(page.locator("main")).not.toContainText("notification-only");
  expect(unknown).toEqual([]);
});

test("health retains degraded HTTP503 details and labels unconfigured services honestly", async ({ page }) => {
  const { requests, unknown } = await mockWorkspace(page, { override: item => {
    if (item.path === "/health") return { status: 503, json: { status: "degraded", env: "production", backend: "groq", database: "unavailable" } };
    if (item.path === "/health/detailed") return { json: { overall: "degraded", database: { status: "error" }, redis: { status: "not_configured" }, vectorstore: { status: "not_configured" } } };
    if (item.path === "/health/breakers") return { json: { overall: "degraded", breakers: { groq: "open" } } };
  } });
  await page.goto("/?view=health");
  await expect(page.getByRole("heading", { name: "Needs attention", exact: true })).toBeVisible();
  await expect(page.getByText("503", { exact: true })).toBeVisible();
  await expect(page.getByText("Not configured", { exact: true })).toHaveCount(2);
  await expect(page.getByText("Requests paused", { exact: true })).toBeVisible();
  await expect(page.locator("main")).not.toContainText("99.98");
  await page.getByLabel("Refresh every 30 seconds", { exact: true }).uncheck();
  const before = requests.filter(item => item.path === "/health").length;
  await page.getByRole("button", { name: "Refresh checks", exact: true }).click();
  await expect.poll(() => requests.filter(item => item.path === "/health").length).toBe(before + 1);
  expect(unknown).toEqual([]);
});

test("health retry errors keep previous results visibly marked and recover", async ({ page }) => {
  let failed = false;
  await mockWorkspace(page, { override: item => item.path === "/health/detailed" && failed ? { status: 503, json: { detail: "Dependency endpoint unavailable" } } : undefined });
  await page.goto("/?view=health");
  await expect(page.getByRole("heading", { name: "Core services responding", exact: true })).toBeVisible();
  failed = true;
  await page.getByRole("button", { name: "Refresh checks", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Dependency endpoint unavailable");
  await expect(page.getByRole("heading", { name: "Checks incomplete", exact: true })).toBeVisible();
  await expect(page.getByText("Previous results remain visible", { exact: false })).toBeVisible();
  failed = false;
  await page.getByRole("button", { name: "Refresh checks", exact: true }).click();
  await expect(page.getByRole("alert")).toHaveCount(0);
});
