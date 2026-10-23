import { defineConfig } from "@playwright/test";

process.env.PW_PRIVATE_MODE = "1";

export default defineConfig({
  testDir: "./tests/frontend",
  testMatch: "private.spec.ts",
  timeout: 30_000,
  expect: { timeout: 12_000 },
  use: { baseURL: "http://127.0.0.1:5175", channel: process.env.PW_CHANNEL || undefined, headless: true },
  projects: [
    { name: "desktop", use: { viewport: { width: 1440, height: 1000 } } },
    { name: "mobile", use: { viewport: { width: 375, height: 812 }, isMobile: true, hasTouch: true } },
  ],
  webServer: {
    command: "node scripts/frontend-test-server.mjs",
    url: "http://127.0.0.1:5175",
    reuseExistingServer: false,
    timeout: 120_000,
    env: {
      VITE_API_BASE_URL: "",
      VITE_PRIVATE_MODE: "true",
      // Nonempty test-only values prove the private flag wins over stale configuration.
      VITE_POSTHOG_API_KEY: "private-test-key",
      VITE_SENTRY_DSN: "https://publickey@telemetry.example.test/123",
      VITE_CLERK_PUBLISHABLE_KEY: "",
    },
  },
});
