// CONFIG
const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.DEV ? "http://localhost:8000" : "");

// API HELPERS
export function getToken() { return localStorage.getItem("access_token"); }
export function getGatewayKey() { return localStorage.getItem("gateway_api_key") || ""; }
export function setGatewayKey(key) {
  if (key) localStorage.setItem("gateway_api_key", key);
  else localStorage.removeItem("gateway_api_key");
}

/** Mask gateway keys in UI — show a short prefix hint, hide the rest. */
export function maskGatewayKey(key) {
  if (!key) return "";
  const visible = Math.min(8, key.length);
  return key.slice(0, visible) + "*".repeat(Math.max(8, key.length - visible));
}

export const gatewayKeyInputProps = {
  type: "password",
  autoComplete: "off",
  spellCheck: false,
};
export function setTokens(access, refresh) {
  localStorage.setItem("access_token", access);
  localStorage.setItem("refresh_token", refresh);
}
export function clearTokens() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
}

export function formatApiError(detail) {
  if (!detail) return "Request failed";
  if (typeof detail === "string") return detail;
  if (typeof detail === "object" && detail.message) return detail.message;
  if (Array.isArray(detail)) {
    return detail.map((item) => item.msg || JSON.stringify(item)).join("; ");
  }
  return String(detail);
}

export async function api(path, opts = {}) {
  const token = getToken();
  const res = await fetch(BASE_URL + path, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: "Bearer " + token } : {}),
      ...(opts.headers || {}),
    },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(formatApiError(err.detail) || "Request failed");
  }
  if (res.status === 204) return null;
  return res.json();
}

// Input guardrail regex (mirrors backend)
const PII_PATTERNS = [
  { name: "credit_card", regex: /\b(?:\d[ -]?){13,16}\b/ },
  { name: "ssn",         regex: /\b\d{3}-\d{2}-\d{4}\b/ },
];
const INJECTION_KW = ["ignore previous instructions", "disregard your system prompt", "forget everything"];
const JAILBREAK_KW = ["DAN mode", "developer mode", "pretend you have no restrictions"];

const USER_PROMPT = "What does AI Guardrails protect?";
const AI_RESPONSE = "I secure AI workflows end to end: live model traffic, Cursor skills, MCP instructions, and agent system prompts. I block leaked credentials, PII, destructive shell/SQL, and jailbreaks before they reach providers or coding agents — with one dashboard and git hooks you control from chat.";

/** Type text character-by-character or word-by-word when `active` becomes true. */
