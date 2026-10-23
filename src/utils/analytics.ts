import posthog from "posthog-js";
import type { components } from "../api-types";

type UserOut = components["schemas"]["UserOut"];
const PRIVATE_MODE = import.meta.env.VITE_PRIVATE_MODE === "true";

export function identifyUser(user: UserOut | null): void {
  if (PRIVATE_MODE || !posthog || !posthog.isFeatureEnabled) return;
  if (!user) { posthog.reset(); return; }
  posthog.identify(user.id, {
    email: user.email,
    name: user.full_name,
    is_admin: user.is_admin,
    org_id: user.org_id,
  });
}

export function trackEvent(name: string, props?: Record<string, unknown>): void {
  if (PRIVATE_MODE || !posthog || !posthog.isFeatureEnabled) return;
  if (typeof posthog.capture === "function") {
    posthog.capture(name, props);
  }
}
