import posthog from "posthog-js";

export function identifyUser(user) {
  if (!posthog || !posthog.isFeatureEnabled) return;
  if (!user) { posthog.reset(); return; }
  posthog.identify(user.id, {
    email: user.email,
    name: user.full_name,
    is_admin: user.is_admin,
    org_id: user.org_id,
  });
}

export function trackEvent(name, props) {
  if (!posthog || !posthog.isFeatureEnabled) return;
  if (typeof posthog.capture === "function") {
    posthog.capture(name, props);
  }
}

export function trackChatResult(result) {
  trackEvent("chat_sent", {
    status: result.status,
    backend: result.backend,
    model: result.model,
    latency_ms: result.latency_ms,
    input_blocked: result.status === "input_blocked",
    output_blocked: result.status === "output_blocked",
    error: result.status === "error",
  });
}
