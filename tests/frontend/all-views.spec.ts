import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mkdir } from "node:fs/promises";
import { mockWorkspace } from "./fixtures";
test.setTimeout(60_000);

const views = ["dashboard", "chat", "skills", "memory", "mandate", "analytics", "logs", "health", "keys", "policy", "teams", "team", "billing", "admin", "settings", "profile", "about"];
for (const view of views) test(`${view} stays accessible and fits the viewport in both themes`, async ({ page }, info) => {
  const errors: string[] = []; page.on("pageerror", error => errors.push(error.message));
  const mocks = await mockWorkspace(page);
  await page.goto("/?view=" + view);
  await expect(page.locator("main h1")).toHaveCount(1);
  await expect(page.locator("main h1")).toBeVisible();
  await expect(page.getByText("This view couldn't load.", { exact: true })).toHaveCount(0);
  await expect(page.locator("main .ui-loading, main .workspace-view-loading, main .gr-dash-loading")).toHaveCount(0);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await mkdir("test-results/previews", { recursive: true });
  for (const theme of ["light", "dark"]) {
    if (theme === "dark") await page.getByRole("button", { name: "Switch to dark theme" }).click();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: `test-results/previews/${view}-${theme}-${info.project.name}.png` });
    const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
    expect(result.violations.map(item => ({ id: item.id, description: item.description, nodes: item.nodes.map(node => ({ target: node.target, summary: node.failureSummary })) }))).toEqual([]);
  }
  expect(errors).toEqual([]);
  expect(mocks.unknown).toEqual([]);
});

test("secondary workspaces give honest empty and error states", async ({ page }) => {
  const mocks = await mockWorkspace(page, { empty: true });
  for (const view of ["analytics", "logs", "memory", "keys", "team", "admin"]) {
    await page.goto("/?view=" + view);
    await expect(page.locator("main h1")).toBeVisible();
    await expect(page.locator("main .ui-loading, main .workspace-view-loading")).toHaveCount(0);
    await expect(page.locator("main .ui-empty").first()).toBeVisible();
    await expect(page.getByText("This view couldn't load.", { exact: true })).toHaveCount(0);
  }
  expect(mocks.unknown).toEqual([]);
});
