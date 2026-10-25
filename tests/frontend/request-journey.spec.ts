import { expect, test } from "@playwright/test";
import type { Locator, Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { dashboard, mockWorkspace } from "./fixtures";

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

test("keyboard step exploration stays paused until the visitor resumes or chooses an example", async ({ page }) => {
  const requests = await mockSignedOutPage(page);
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.clock.install({ time: new Date("2026-10-24T12:00:00Z") });
  await page.clock.pauseAt(new Date("2026-10-24T12:00:01Z"));
  await page.goto("/");
  const journey = page.getByRole("region", { name: journeyName, exact: true });
  const steps = journey.getByRole("group", { name: "Explore the three steps", exact: true });
  const checkStep = steps.getByRole("button", { name: "Step 2: A quick check", exact: true });
  await checkStep.focus();
  await page.keyboard.press("Enter");
  await expect(checkStep).toHaveAttribute("aria-pressed", "true");
  await expect(journey).toHaveAttribute("data-state", "paused");
  await expect(journey).toHaveAttribute("data-step", "1");
  const narrative = journey.getByRole("group", { name: "About the selected step", exact: true });
  await expect(narrative).toContainText("Your rules do the checking.");
  await expect(narrative).toContainText("Nothing in this example needs changing. The message can continue to the AI.");
  await page.clock.runFor(10_000);
  await expect(journey).toHaveAttribute("data-state", "paused");
  await expect(journey).toHaveAttribute("data-step", "1");
  await expect(checkStep).toBeFocused();

  const playback = journey.getByRole("button", { name: "Resume example", exact: true });
  await playback.focus();
  await page.keyboard.press("Enter");
  await expect(journey).toHaveAttribute("data-state", "playing");
  await page.clock.runFor(1600);
  await expect(journey).toHaveAttribute("data-step", "2");
  await page.clock.runFor(1600);
  await expect(journey).toHaveAttribute("data-state", "complete");

  const messageStep = steps.getByRole("button", { name: "Step 1: Your message", exact: true });
  await messageStep.focus();
  await page.keyboard.press("Enter");
  await expect(messageStep).toHaveAttribute("aria-pressed", "true");
  await expect(journey).toHaveAttribute("data-state", "paused");
  await expect(journey).toHaveAttribute("data-step", "0");
  await expect(narrative).not.toContainText("Your rules do the checking.");
  await page.clock.runFor(10_000);
  await expect(journey).toHaveAttribute("data-step", "0");
  await expect(messageStep).toBeFocused();

  const scenario = journey.getByRole("button", { name: "Private detail", exact: true });
  await scenario.focus();
  await page.keyboard.press("Enter");
  await expect(journey).toHaveAttribute("data-example", "private");
  await expect(journey).toHaveAttribute("data-state", "playing");
  await expect(scenario).toBeFocused();
  await completeJourney(page, journey);
  await checkStep.focus();
  await page.keyboard.press("Enter");
  await expect(narrative).toContainText("With an email-redaction rule, the address is hidden before the message continues.");
  expect(requests).toEqual([]);
});

test("dashboard examples explain decisions without sending a real request or changing activity", async ({ page }, info) => {
  const mocks = await mockWorkspace(page);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/?view=dashboard");
  const journey = page.getByRole("region", { name: journeyName, exact: true });
  const metrics = page.getByRole("region", { name: "Request metrics", exact: true });
  await expect(metrics).toContainText("1,248");
  const activity = page.getByRole("region", { name: "Activity at a glance", exact: true });
  const summary = dashboard.summary;
  const deliveryRate = (summary.delivered / summary.total_requests * 100).toLocaleString(undefined, { maximumFractionDigits: 1 }) + "%";
  await expect(activity.getByText(deliveryRate, { exact: true })).toBeVisible();
  await expect(activity.getByText(`${summary.delivered.toLocaleString()} of ${summary.total_requests.toLocaleString()} requests were delivered.`, { exact: true })).toBeVisible();
  for (const [label, value] of [["Stopped before the AI", summary.input_blocked], ["AI response blocked", summary.output_blocked], ["Rate limited", summary.rate_limited], ["Failed requests", summary.error_count]] as const) {
    await expect(activity.locator("dl")).toContainText(new RegExp(label + "\\s*" + value.toLocaleString()));
  }
  const shortcuts = page.getByRole("navigation", { name: "Workspace shortcuts", exact: true });
  for (const [label, view] of [["Try a question", "chat"], ["Shape your rules", "policy"], ["Understand a result", "logs"]]) {
    await expect(shortcuts.getByRole("link", { name: label, exact: true })).toHaveAttribute("href", "?view=" + view);
  }
  await page.locator(".gr-dash-activity-header").evaluate(element => element.scrollIntoView({ block: "start" }));
  await mkdir("test-results/previews", { recursive: true });
  await page.screenshot({ path: `test-results/previews/activity-${info.project.name}.png` });
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

test("an empty activity period invites a request without inventing a delivery rate", async ({ page }) => {
  const mocks = await mockWorkspace(page, { empty: true });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/?view=dashboard");
  const activity = page.getByRole("region", { name: "Activity at a glance", exact: true });
  await expect(activity.getByText("No requests in this period yet.", { exact: true })).toBeVisible();
  await expect(activity).not.toContainText("100%");
  await expect(activity).not.toContainText("90.9%");
  await expect(page.getByRole("navigation", { name: "Workspace shortcuts", exact: true })).toBeVisible();
  expect(mocks.requests.filter(request => request.method !== "GET")).toEqual([]);
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
  await journey.getByRole("button", { name: "Step 1: Your message", exact: true }).click();
  await expect(journey).toHaveAttribute("data-state", "complete");
  await expect(journey).toHaveAttribute("data-step", "0");
  await expect(journey.getByRole("button", { name: playbackName })).toHaveCount(0);
  expect(requests).toEqual([]);
});

const viewports = [
  { width: 920, height: 800, zoom: 1 },
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
    await expect(page.getByRole("region", { name: "Activity at a glance", exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const main = page.getByRole("main");
    expect(await main.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
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
