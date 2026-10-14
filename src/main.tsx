import React from "react";
import { createRoot } from "react-dom/client";
import * as Sentry from "@sentry/react";
import posthog from "posthog-js";
import App from "./App";

const SENTRY_DSN = import.meta.env.VITE_SENTRY_DSN || "";
const PRIVATE_MODE = import.meta.env.VITE_PRIVATE_MODE === "true";
if (SENTRY_DSN && !PRIVATE_MODE) {
  Sentry.init({
    dsn: SENTRY_DSN,
    environment: import.meta.env.MODE,
    tracesSampleRate: 0.1,
  });
}

const POSTHOG_KEY = import.meta.env.VITE_POSTHOG_API_KEY || "";
const POSTHOG_HOST = import.meta.env.VITE_POSTHOG_HOST || "https://us.i.posthog.com";
if (POSTHOG_KEY && !PRIVATE_MODE) {
  posthog.init(POSTHOG_KEY, { api_host: POSTHOG_HOST, capture_pageview: true });
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
