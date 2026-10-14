import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { log, mockWorkspace, policy, user } from "./fixtures";

test("profile edits update the workspace identity without changing the email", async ({ page }) => {
  const { requests, unknown } = await mockWorkspace(page);
  await page.goto("/?view=profile");
  const name = page.getByLabel("Display name", { exact: true });
  await expect(name).toHaveValue(user.full_name);
  await expect(page.getByLabel("Email address", { exact: true })).toHaveAttribute("readonly", "");
  await name.fill("  Alex Builder  ");
  await page.getByRole("button", { name: "Save profile", exact: true }).click();
  await expect(page.getByText("Your profile has been saved.")).toBeVisible();
  expect(requests.find((request) => request.path === "/auth/profile" && request.method === "PATCH")?.body).toEqual({ full_name: "Alex Builder" });
  await expect(page.getByRole("heading", { name: "Alex Builder", exact: true })).toBeVisible();
  expect(unknown).toEqual([]);
});

test("security settings preserve unrelated compliance rules and request limits save independently", async ({ page }) => {
  const { requests, unknown } = await mockWorkspace(page);
  await page.goto("/?view=settings");
  await page.getByLabel("Webhook URL", { exact: true }).fill("https://example.com/guardrail-events");
  await page.getByLabel("IP blocklist", { exact: true }).fill("192.0.2.10\n\n 198.51.100.8 ");
  await page.getByRole("button", { name: "Save security settings", exact: true }).click();
  await expect(page.getByText("Webhook and access settings saved.")).toBeVisible();
  const security = requests.find((request) => request.path === "/policy" && request.method === "PATCH");
  expect(security?.body).toEqual({ compliance_rules: { ...policy.compliance_rules, webhook_url: "https://example.com/guardrail-events", blocked_ips: ["192.0.2.10", "198.51.100.8"] } });
  await page.getByLabel("Requests per minute", { exact: true }).fill("120");
  await page.getByLabel("Requests per day", { exact: true }).fill("");
  await page.getByRole("button", { name: "Save request limits", exact: true }).click();
  await expect(page.getByText("Workspace request limits saved.")).toBeVisible();
  expect(requests.filter((request) => request.path === "/policy" && request.method === "PATCH").at(-1)?.body).toEqual({ rate_limit_rpm: 120, rate_limit_rpd: 0 });
  expect(unknown).toEqual([]);
});

test("password mismatch stays local and a valid change uses the authenticated endpoint once", async ({ page }) => {
  const { requests, unknown } = await mockWorkspace(page);
  await page.goto("/?view=settings");
  await page.getByLabel("Current password", { exact: true }).fill("current-secret");
  await page.getByLabel("New password", { exact: true }).fill("new-valid-secret");
  await page.getByLabel("Confirm new password", { exact: true }).fill("different-secret");
  await page.getByRole("button", { name: "Update password", exact: true }).click();
  await expect(page.getByText("The new passwords do not match.")).toBeVisible();
  expect(requests.filter((request) => request.path === "/auth/change-password")).toHaveLength(0);
  await page.getByLabel("Confirm new password", { exact: true }).fill("new-valid-secret");
  await page.getByRole("button", { name: "Update password", exact: true }).click();
  await expect(page.getByText("Password updated.", { exact: true })).toBeVisible();
  const changes = requests.filter((request) => request.path === "/auth/change-password");
  expect(changes).toHaveLength(1);
  expect(changes[0]).toMatchObject({ method: "POST", authorization: "Bearer ui-test-token", body: { current_password: "current-secret", new_password: "new-valid-secret" } });
  await expect(page.getByLabel("Current password", { exact: true })).toHaveValue("");
  await expect(page.getByLabel("New password", { exact: true })).toHaveValue("");
  expect(unknown).toEqual([]);
});

test("audit export downloads every page with the selected period", async ({ page }) => {
  const { requests, unknown } = await mockWorkspace(page, { override: (request) => {
    if (!request.path.startsWith("/org/export?")) return;
    const url = new URL(request.path, "http://localhost");
    const page = Number(url.searchParams.get("page"));
    return { json: { total: 501, page, page_size: 500, items: page === 1 ? Array.from({ length: 500 }, (_, index) => ({ ...log, id: `export-${index}` })) : [{ ...log, id: "export-500" }] } };
  } });
  await page.goto("/?view=settings");
  await page.getByLabel("Export period", { exact: true }).selectOption("7");
  const downloadEvent = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download audit export", exact: true }).click();
  const download = await downloadEvent;
  expect(download.suggestedFilename()).toMatch(/^guardrails-audit-7days-\d{4}-\d{2}-\d{2}\.json$/);
  const downloadPath = await download.path();
  expect(downloadPath).not.toBeNull();
  const exported = JSON.parse(await readFile(downloadPath!, "utf8"));
  expect(exported).toMatchObject({ days: 7, total: 501 });
  expect(new Set(exported.items.map((item: { id: string }) => item.id)).size).toBe(501);
  await expect(page.getByText("Exported 501 audit records.")).toBeVisible();
  expect(requests.filter((request) => request.path.startsWith("/org/export?"))).toHaveLength(2);
  expect(requests.filter((request) => request.path.startsWith("/org/export?")).every((request) => request.path.includes("days=7") && request.authorization === "Bearer ui-test-token")).toBe(true);
  expect(unknown).toEqual([]);
});

test("switching teams refreshes the current role before opening team access", async ({ page }) => {
  let switched = false;
  const { requests, unknown } = await mockWorkspace(page, { override: (request) => {
    if (request.path === "/org/switch") switched = true;
    if (request.path === "/auth/me" && switched) return { json: { ...user, org_id: "ui-org-2", is_admin: false } };
  } });
  await page.goto("/?view=teams");
  await page.getByRole("button", { name: "Switch workspace", exact: true }).click();
  await expect(page).toHaveURL(/view=team(?:&|$)/);
  await expect(page.getByRole("heading", { name: "An administrator manages team access", exact: true })).toBeVisible();
  expect(requests.find((request) => request.path === "/org/switch")?.body).toEqual({ org_id: "ui-org-2" });
  expect(requests.filter((request) => request.path === "/auth/me").length).toBeGreaterThanOrEqual(2);
  expect(unknown).toEqual([]);
});

test("team deletion can be cancelled and requires the exact full name", async ({ page }) => {
  const { requests, unknown } = await mockWorkspace(page);
  await page.goto("/?view=teams");
  await page.getByRole("button", { name: "Delete Research team", exact: true }).click();
  const deletion = page.getByRole("dialog", { name: "Delete Research team?", exact: true });
  await expect(deletion).toBeVisible();
  await deletion.getByRole("button", { name: "Keep team", exact: true }).click();
  await expect(deletion).not.toBeVisible();
  expect(requests.some((request) => request.method === "DELETE")).toBe(false);
  await page.getByRole("button", { name: "Delete Research team", exact: true }).click();
  await deletion.getByLabel("Confirm with your full name", { exact: true }).fill("Alex");
  await expect(deletion.getByRole("button", { name: "Delete team", exact: true })).toBeDisabled();
  await deletion.getByLabel("Confirm with your full name", { exact: true }).fill(user.full_name);
  await deletion.getByRole("button", { name: "Delete team", exact: true }).click();
  await expect(page.getByText("Deleted Research team.", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Research team", exact: true })).toHaveCount(0);
  expect(requests.filter((request) => request.method === "DELETE")).toEqual([expect.objectContaining({ path: "/org/ui-org-2", body: { full_name: user.full_name } })]);
  expect(unknown).toEqual([]);
});

test("billing shows a real purchase record and prevents duplicate checkout while pending", async ({ page }) => {
  let finishCheckout: (() => void) | undefined;
  const checkoutPending = new Promise<void>((resolve) => { finishCheckout = resolve; });
  const { requests, unknown } = await mockWorkspace(page, { override: async (request) => {
    if (request.path === "/billing/checkout") { await checkoutPending; return { json: { checkout_url: null, message: "Mock credits added." } }; }
  } });
  await page.goto("/?view=billing");
  await page.getByRole("button", { name: "View record", exact: true }).click();
  const receipt = page.getByRole("dialog", { name: "Purchase record", exact: true });
  await expect(receipt.getByText("purchase-1", { exact: true })).toBeVisible();
  await expect(receipt.getByRole("button", { name: "Print record", exact: true })).toBeVisible();
  await receipt.getByRole("button", { name: "Close", exact: true }).click();
  await expect(receipt).not.toBeVisible();
  const buy = page.getByRole("button", { name: "Buy Starter", exact: true });
  await buy.click();
  await expect(buy).toBeDisabled();
  await expect(page.getByRole("button", { name: "Buy Builder", exact: true })).toBeDisabled();
  await buy.evaluate((button) => (button as HTMLButtonElement).click());
  expect(requests.filter((request) => request.path === "/billing/checkout")).toHaveLength(1);
  finishCheckout?.();
  await expect(page.getByText("Mock credits added.", { exact: true })).toBeVisible();
  await expect(buy).toBeEnabled();
  expect(requests.find((request) => request.path === "/billing/checkout")?.body).toEqual({ plan_slug: "starter" });
  expect(unknown).toEqual([]);
});

test("administration protects the signed-in account and confirms bulk membership changes", async ({ page }) => {
  const { requests, unknown } = await mockWorkspace(page);
  await page.goto("/?view=admin");
  await expect(page.getByRole("checkbox", { name: `Select ${user.email}`, exact: true })).toBeDisabled();
  await page.getByRole("checkbox", { name: "Select sam@example.com", exact: true }).check();
  const bulk = page.getByRole("region", { name: "Actions for selected accounts", exact: true });
  await bulk.getByRole("button", { name: "Remove", exact: true }).click();
  const remove = page.getByRole("dialog", { name: "Remove 1 selected accounts?", exact: true });
  await remove.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(remove).not.toBeVisible();
  expect(requests.some((request) => request.path === "/admin/users/bulk")).toBe(false);
  await bulk.getByRole("button", { name: "Enable", exact: true }).click();
  const enable = page.getByRole("dialog", { name: "Enable 1 selected accounts?", exact: true });
  await enable.getByRole("button", { name: "Enable accounts", exact: true }).click();
  await expect(page.getByText("Bulk request completed. Review the refreshed accounts below.", { exact: true })).toBeVisible();
  expect(requests.find((request) => request.path === "/admin/users/bulk")?.body).toEqual({ action: "enable", user_ids: ["ui-user-2"] });
  await expect(bulk).toHaveCount(0);
  expect(unknown).toEqual([]);
});

test("failed ban loading is reported honestly and key revocation remains deliberate", async ({ page }) => {
  const { requests, unknown } = await mockWorkspace(page, { override: (request) => request.path === "/admin/bans" ? { status: 503, json: { detail: "Restrictions temporarily unavailable" } } : undefined });
  await page.goto("/?view=admin");
  await expect(page.getByRole("alert")).toContainText("Restrictions could not be loaded");
  await expect(page.getByRole("heading", { name: "No active restrictions", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Revoke", exact: true }).click();
  const revoke = page.getByRole("dialog", { name: "Revoke Application gateway?", exact: true });
  await revoke.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(revoke).not.toBeVisible();
  expect(requests.some((request) => request.path === "/admin/api-keys/key-1" && request.method === "DELETE")).toBe(false);
  await page.getByRole("button", { name: "Revoke", exact: true }).click();
  await revoke.getByRole("button", { name: "Revoke key", exact: true }).click();
  await expect(page.getByText("Revoked Application gateway.", { exact: true })).toBeVisible();
  expect(requests.filter((request) => request.path === "/admin/api-keys/key-1" && request.method === "DELETE")).toHaveLength(1);
  expect(unknown).toEqual([]);
});
