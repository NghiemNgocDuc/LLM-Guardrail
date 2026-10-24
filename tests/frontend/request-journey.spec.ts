import { expect, test } from "@playwright/test";
import type { Locator, Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { mockWorkspace } from "./fixtures";

const journeyName = "How guardrails work";
const playbackName = /^(Pause|Resume|Replay) example$/;

async function completeJourney(page: Page, journey: Locator) {
  // Let React commit each stage and schedule its next timer before advancing again.
  for (const step of ["1", "2"]) {
    await page.clock.runFor(1600);
    await expect(journey).toHaveAttribute("data-step", step);
  }
  await page.clock.runFor(1600);
  await expect(journey).toHaveAttribute("data-state", "complete");
}

async function mockSignedOutPage(page: Page) {
  const requests: string[] = [];
  await page.route("**/*", async route => {
    const request = route.request(), url = new URL(request.url());
    if (/posthog|sentry/i.test(url.hostname)) return route.abort();
    if (/^\/(auth|analytics|chat|feedback|billing|org|policy|skills|memories|gateway)(\/|$)/.test(url.pathname)) {
      if (request.method() !== "OPTIONS") requests.push(request.method() + " " + url.pathname);
      return route.fulfill({ status: 200, json: {} });
    }
    return route.continue();
  });
  return requests;
}

test("the illustrative journey pauses, finishes once, and replays without submitting the sign-in form", async ({ page }) => {
  const requests = await mockSignedOutPage(page);
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.clock.install({ time: new Date("2026-10-24T12:00:00Z") });
  await page.clock.pauseAt(new Date("2026-10-24T12:00:01Z"));
  await page.goto("/");
  const journey = page.getByRole("region", { name: journeyName, exact: true });
  await expect(journey).toHaveAttribute("data-state", "playing");
  const email = page.getByLabel("Email address", { exact: true });
  const password = page.getByLabel("Password", { exact: true });
  await email.fill("reviewer@example.com");
  await password.fill("valid-password");

  const playback = journey.getByRole("button", { name: playbackName });
  await playback.focus();
  await page.keyboard.press("Enter");
  await expect(playback).toHaveAccessibleName("Resume example");
  await expect(journey).toHaveAttribute("data-state", "paused");
  const pausedStep = await journey.getAttribute("data-step");
  await page.clock.runFor(10_000);
  await expect(journey).toHaveAttribute("data-step", pausedStep!);
  await expect(playback).toBeFocused();

  await page.keyboard.press("Enter");
  await expect(playback).toHaveAccessibleName("Pause example");
  await completeJourney(page, journey);
  await expect(journey).toHaveAttribute("data-step", "2");
  await expect(playback).toHaveAccessibleName("Replay example");
  await expect(playback).toBeFocused();
  await page.clock.runFor(20_000);
  await expect(journey).toHaveAttribute("data-state", "complete");

  await page.keyboard.press("Enter");
  await expect(journey).toHaveAttribute("data-state", "playing");
  await expect(journey).toHaveAttribute("data-step", "0");
  await page.clock.runFor(600);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(journey).toHaveAttribute("data-state", "complete");
  await expect(journey).toHaveAttribute("data-step", "2");
  await expect(playback).toHaveCount(0);
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await expect(playback).toHaveAccessibleName("Replay example");
  expect(await journey.evaluate(element => element.getAnimations({ subtree: true }).filter(animation => animation.playState === "running").length)).toBe(0);
  await page.clock.runFor(10_000);
  await expect(journey).toHaveAttribute("data-state", "complete");
  await playback.focus();
  await page.keyboard.press("Enter");
  await expect(journey).toHaveAttribute("data-state", "playing");
  await completeJourney(page, journey);
  await expect(email).toHaveValue("reviewer@example.com");
  await expect(password).toHaveValue("valid-password");
  expect(requests).toEqual([]);
});

test("dashboard examples explain decisions without sending a real request or changing activity", async ({ page }) => {
  const mocks = await mockWorkspace(page);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/?view=dashboard");
  const journey = page.getByRole("region", { name: journeyName, exact: true });
  const metrics = page.getByRole("region", { name: "Request metrics", exact: true });
  await expect(metrics).toContainText("1,248");
  const originalMetrics = await metrics.innerText();
  for (const scenario of ["Private detail", "Risky instruction", "Everyday question"]) {
    const button = journey.getByRole("button", { name: scenario, exact: true });
    await button.focus();
    await page.keyboard.press("Enter");
    await expect(button).toHaveAttribute("aria-pressed", "true");
    await expect(button).toBeFocused();
    await expect(journey).toHaveAttribute("data-state", "complete");
    await expect(journey).toHaveAttribute("data-step", "2");
  }
  await expect(metrics).toHaveText(originalMetrics, { useInnerText: true });
  expect(mocks.requests.filter(request => request.method !== "GET")).toEqual([]);
  expect(mocks.requests.some(request => request.path === "/chat")).toBe(false);
  expect(mocks.unknown).toEqual([]);
});

test("reduced motion keeps the complete sign-in explanation readable without playback", async ({ page }, info) => {
  const requests = await mockSignedOutPage(page);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  const journey = page.getByRole("region", { name: journeyName, exact: true });
  await expect(journey).toHaveAttribute("data-state", "complete");
  await expect(journey).toHaveAttribute("data-step", "2");
  await expect(journey.getByRole("button", { name: playbackName })).toHaveCount(0);
  await expect(journey.getByRole("button", { name: "Everyday question", exact: true })).toHaveAttribute("aria-pressed", "true");
  for (const label of ["Your message", "A quick check", "What happens next", "Illustrative example"]) {
    await expect(journey.getByText(label, { exact: true })).toBeVisible();
  }
  await expect(journey.getByText("Help me write a friendly thank-you note.", { exact: true })).toBeVisible();
  await expect(journey.getByText("Thanks for your help. You made my day!", { exact: true })).toBeVisible();
  await expect(journey.getByText("Examples only. Your workspace rules determine the result.", { exact: true })).toBeVisible();
  expect(await journey.evaluate(element => element.getAnimations({ subtree: true }).filter(animation => animation.playState === "running").length)).toBe(0);
  await mkdir("test-results/previews", { recursive: true });
  await page.screenshot({ path: `test-results/previews/sign-in-${info.project.name}.png`, fullPage: true });
  await journey.getByRole("button", { name: "Private detail", exact: true }).click();
  await expect(journey).toHaveAttribute("data-state", "complete");
  await expect(journey.getByRole("button", { name: playbackName })).toHaveCount(0);
  expect(requests).toEqual([]);
});

const viewports = [
  { width: 900, height: 700, zoom: 1 },
  { width: 812, height: 375, zoom: 1 },
  { width: 375, height: 812, zoom: 1.25 },
];

for (const viewport of viewports) {
  test(`the explanation fits at ${viewport.width}x${viewport.height}${viewport.zoom > 1 ? " with enlarged text" : ""}`, async ({ page }, info) => {
    test.skip(info.project.name !== "desktop", "Custom viewports are covered once through the desktop project.");
    const mocks = await mockWorkspace(page);
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/?view=dashboard");
    if (viewport.zoom > 1) await page.evaluate(zoom => { document.documentElement.style.zoom = String(zoom); }, viewport.zoom);
    const journey = page.getByRole("region", { name: journeyName, exact: true });
    await expect(journey).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    for (const button of await journey.getByRole("button").all()) {
      await button.scrollIntoViewIfNeeded();
      await expect(button).toBeVisible();
      const bounds = await button.boundingBox();
      expect(bounds).not.toBeNull();
      expect(bounds!.x).toBeGreaterThanOrEqual(0);
      expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(viewport.width);
    }
    await mkdir("test-results/previews", { recursive: true });
    await page.screenshot({ path: `test-results/previews/journey-${viewport.width}x${viewport.height}.png` });
    expect(mocks.unknown).toEqual([]);
  });
}
