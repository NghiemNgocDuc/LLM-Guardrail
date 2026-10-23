import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { mockWorkspace } from "./fixtures";

const viewports = [
  { width: 900, height: 700, zoom: 1 },
  { width: 812, height: 375, zoom: 1 },
  { width: 375, height: 812, zoom: 1.25 },
];

for (const viewport of viewports) {
  test(`help remains reachable at ${viewport.width}x${viewport.height}${viewport.zoom > 1 ? " with enlarged text" : ""}`, async ({ page }, info) => {
    test.skip(info.project.name !== "desktop", "Custom viewports are covered once through the desktop project.");
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await mockWorkspace(page);
    await page.goto("/?view=about");
    await expect(page.locator("main h1")).toBeVisible();
    if (viewport.zoom > 1) await page.evaluate(zoom => { document.documentElement.style.zoom = String(zoom); }, viewport.zoom);

    const buttons = page.locator(".workspace-topbar").getByRole("button");
    expect(await buttons.count()).toBeGreaterThan(0);
    for (const button of await buttons.all()) {
      await expect(button).toBeVisible();
      const bounds = await button.boundingBox();
      expect(bounds).not.toBeNull();
      expect(bounds!.x).toBeGreaterThanOrEqual(0);
      expect(bounds!.y).toBeGreaterThanOrEqual(0);
      expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(viewport.width);
      expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(viewport.height);
    }

    const trigger = page.getByRole("button", { name: "Help with this page", exact: true });
    await trigger.click();
    const dialog = page.getByRole("dialog", { name: "Help with Help & getting started", exact: true });
    await expect(dialog).toBeVisible();
    const dialogBounds = await dialog.boundingBox();
    expect(dialogBounds).not.toBeNull();
    expect(dialogBounds!.x).toBeGreaterThanOrEqual(0);
    expect(dialogBounds!.y).toBeGreaterThanOrEqual(0);
    expect(dialogBounds!.x + dialogBounds!.width).toBeLessThanOrEqual(viewport.width);
    expect(dialogBounds!.y + dialogBounds!.height).toBeLessThanOrEqual(viewport.height);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);

    const close = dialog.getByRole("button", { name: "Close dialog", exact: true });
    await close.scrollIntoViewIfNeeded();
    await close.focus();
    await expect(close).toBeFocused();
    const closeBounds = await close.boundingBox();
    expect(closeBounds).not.toBeNull();
    expect(closeBounds!.x).toBeGreaterThanOrEqual(0);
    expect(closeBounds!.y).toBeGreaterThanOrEqual(0);
    expect(closeBounds!.x + closeBounds!.width).toBeLessThanOrEqual(viewport.width);
    expect(closeBounds!.y + closeBounds!.height).toBeLessThanOrEqual(viewport.height);
    await mkdir("test-results/previews", { recursive: true });
    await page.screenshot({ path: `test-results/previews/responsive-help-${viewport.width}x${viewport.height}.png` });

    await page.keyboard.press("Escape");
    await expect(dialog).not.toBeVisible();
    await expect(trigger).toBeFocused();
  });
}
