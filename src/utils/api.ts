import type { components } from "../api-types";

export const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.DEV ? "http://localhost:8000" : "");

export function getGatewayKey(): string { return localStorage.getItem("gateway_api_key") || ""; }
export function setGatewayKey(key: string): void {
  if (key) localStorage.setItem("gateway_api_key", key);
  else localStorage.removeItem("gateway_api_key");
}

export function maskGatewayKey(key: string): string {
  if (!key) return "";
  const visible = Math.min(8, key.length);
  return key.slice(0, visible) + "*".repeat(Math.max(8, key.length - visible));
}

export function isProviderKey(key: string): boolean {
  const k = key.trim();
  return /^(gsk_|sk-|sk-ant-|AKIA)/.test(k) || /sk-proj-/.test(k);
}

export const gatewayKeyInputProps = {
  type: "password",
  autoComplete: "off",
  spellCheck: false,
} as const;

export type ApiDetail =
  | string
  | { message?: string }
  | Array<{ msg?: string }>;

export function formatApiError(detail: ApiDetail | undefined): string {
  if (!detail) return "Request failed";
  if (typeof detail === "string") return detail;
  if (typeof detail === "object" && !Array.isArray(detail) && detail.message) return detail.message;
  if (Array.isArray(detail)) {
    return detail.map((item) => item.msg || JSON.stringify(item)).join("; ");
  }
  return String(detail);
}

export type ApiOptions = {
  method?: string;
  headers?: Record<string, string>;
  body?: unknown;
};

export async function getAuthToken(): Promise<string | null> {
  return localStorage.getItem("access_token");
}

export function getToken(): string | null { return localStorage.getItem("access_token"); }
export function setTokens(accessToken?: string, refreshToken?: string): void {
  if (accessToken) localStorage.setItem("access_token", accessToken);
  if (refreshToken) localStorage.setItem("refresh_token", refreshToken);
}
export function clearTokens(): void {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
}

export async function api<T = unknown>(path: string, opts: ApiOptions = {}): Promise<T> {
  let token: string | null = null;
  token = getToken();

  const res = await fetch(BASE_URL + path, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: "Bearer " + token } : {}),
      ...(opts.headers || {}),
    },
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(formatApiError(err.detail) || "Request failed");
  }
  if (res.status === 204) return null as T;
  return res.json() as Promise<T>;
}

export type GuardrailPattern = { name: string; regex: RegExp };
export const PII_PATTERNS: GuardrailPattern[] = [
  { name: "credit_card", regex: /\b(?:\d[ -]?){13,16}\b/ },
  { name: "ssn",         regex: /\b\d{3}-\d{2}-\d{4}\b/ },
];
export const INJECTION_KW: string[] = ["ignore previous instructions", "disregard your system prompt", "forget everything"];
export const JAILBREAK_KW: string[] = ["DAN mode", "developer mode", "pretend you have no restrictions"];

export const USER_PROMPT = "What does AI Guardrails protect?";
export const AI_RESPONSE = "I secure AI workflows end to end: live model traffic, Cursor skills, MCP instructions, and agent system prompts. I block leaked credentials, PII, destructive shell/SQL, and jailbreaks before they reach providers or coding agents — with one dashboard and git hooks you control from chat.";

export type ChatStatus = components["schemas"]["ChatResponse"]["status"];