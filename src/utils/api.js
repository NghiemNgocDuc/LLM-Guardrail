const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.DEV ? "http://localhost:8000" : "");

export function getGatewayKey() { return localStorage.getItem("gateway_api_key") || ""; }
export function setGatewayKey(key) {
  if (key) localStorage.setItem("gateway_api_key", key);
  else localStorage.removeItem("gateway_api_key");
}

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

export function formatApiError(detail) {
  if (!detail) return "Request failed";
  if (typeof detail === "string") return detail;
  if (typeof detail === "object" && detail.message) return detail.message;
  if (Array.isArray(detail)) {
    return detail.map((item) => item.msg || JSON.stringify(item)).join("; ");
  }
  return String(detail);
}

let _getClerkToken = null;
export function setClerkTokenProvider(fn) {
  _getClerkToken = fn;
}

export function getToken() { return null; }
export function setTokens() {}
export function clearTokens() {}

export async function api(path, opts = {}) {
  let token = null;
  if (_getClerkToken) {
    try { token = await _getClerkToken(); } catch { token = null; }
  }

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

export const PII_PATTERNS = [
  { name: "credit_card", regex: /\b(?:\d[ -]?){13,16}\b/ },
  { name: "ssn",         regex: /\b\d{3}-\d{2}-\d{4}\b/ },
];
export const INJECTION_KW = ["ignore previous instructions", "disregard your system prompt", "forget everything"];
export const JAILBREAK_KW = ["DAN mode", "developer mode", "pretend you have no restrictions"];

export const USER_PROMPT = "What does AI Guardrails protect?";
export const AI_RESPONSE = "I secure AI workflows end to end: live model traffic, Cursor skills, MCP instructions, and agent system prompts. I block leaked credentials, PII, destructive shell/SQL, and jailbreaks before they reach providers or coding agents — with one dashboard and git hooks you control from chat.";
