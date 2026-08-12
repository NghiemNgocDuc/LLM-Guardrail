import React from "react";
import { createRoot } from "react-dom/client";
import { ClerkProvider } from "@clerk/clerk-react";
import * as Sentry from "@sentry/react";
import posthog from "posthog-js";
import App from "./App";

const SENTRY_DSN = import.meta.env.VITE_SENTRY_DSN || "";
if (SENTRY_DSN) {
  Sentry.init({
    dsn: SENTRY_DSN,
    environment: import.meta.env.MODE,
    tracesSampleRate: 0.1,
  });
}

const POSTHOG_KEY = import.meta.env.VITE_POSTHOG_API_KEY || "";
const POSTHOG_HOST = import.meta.env.VITE_POSTHOG_HOST || "https://us.i.posthog.com";
if (POSTHOG_KEY) {
  posthog.init(POSTHOG_KEY, { api_host: POSTHOG_HOST, capture_pageview: true });
}

const CLERK_PK = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY || "";

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ClerkProvider publishableKey={CLERK_PK}>
      <App />
    </ClerkProvider>
  </React.StrictMode>
);
