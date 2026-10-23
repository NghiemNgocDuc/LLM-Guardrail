import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/frontend",
  fullyParallel: true,
  workers: process.env.CI ? 2 : 3,
  timeout: 30_000,
  expect: { timeout: 12_000 },
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:5173",
    channel: process.env.PW_CHANNEL || undefined,
    headless: true,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "desktop", use: { viewport: { width: 1440, height: 1000 } } },
    { name: "mobile", use: { viewport: { width: 375, height: 812 }, isMobile: true, hasTouch: true } },
  ],
  webServer: {
    command: "node scripts/frontend-test-server.mjs",
    url: "http://127.0.0.1:5173",
    reuseExistingServer: false,
    timeout: 120_000,
    env: { VITE_API_BASE_URL: "http://127.0.0.1:8000", VITE_PRIVATE_MODE: "false", VITE_POSTHOG_API_KEY: "", VITE_SENTRY_DSN: "" },
  },
});
