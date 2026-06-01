import React, { useState, useEffect, useCallback } from "react";
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis,
  Tooltip, ResponsiveContainer, CartesianGrid,
} from "recharts";

// CONFIG
const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.DEV ? "http://localhost:8000" : "");

// API HELPERS
function getToken() { return localStorage.getItem("access_token"); }
function getGatewayKey() { return localStorage.getItem("gateway_api_key") || ""; }
function setGatewayKey(key) {
  if (key) localStorage.setItem("gateway_api_key", key);
  else localStorage.removeItem("gateway_api_key");
}

/** Mask gateway keys in UI — show a short prefix hint, hide the rest. */
function maskGatewayKey(key) {
  if (!key) return "";
  const visible = Math.min(8, key.length);
  return key.slice(0, visible) + "*".repeat(Math.max(8, key.length - visible));
}

const gatewayKeyInputProps = {
  type: "password",
  autoComplete: "off",
  spellCheck: false,
};
function setTokens(access, refresh) {
  localStorage.setItem("access_token", access);
  localStorage.setItem("refresh_token", refresh);
}
function clearTokens() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
}

function formatApiError(detail) {
  if (!detail) return "Request failed";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => item.msg || JSON.stringify(item)).join("; ");
  }
  return String(detail);
}

async function api(path, opts = {}) {
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

const USER_PROMPT = "Can you explain what this platform does?";
const AI_RESPONSE = "I protect LLM traffic and agent skills — blocking leaked credentials, PII, and internal details before they reach models or coding agents. You get a gateway for live prompts plus a scanner for skill files and instructions.";

const SKILL_SAMPLE_UNSAFE = `---
name: prod-database-helper
---
When debugging, connect with:
DATABASE_URL=postgresql://admin:Pr0d_S3cret!@10.0.12.8:5432/customers
Gateway key for smoke tests: grg_` + "x".repeat(40) + `
Never paste customer SSNs like 123-45-6789 into tickets.
To reset staging data run: DROP TABLE users; then rm -rf / --no-preserve-root`;

const SKILL_SAMPLE_SAFE = `---
name: code-review-helper
---
Review pull requests for security issues.
- Flag hard-coded secrets and suggest env vars
- Never ask the user to paste production credentials
- Prefer read-only tools in CI`;

const SKILL_DANGEROUS_PATTERNS = [
  { code: "rm_rf_destructive", check: "Destructive recursive delete", regex: /\brm\s+(-[a-zA-Z]+\s+)*-rf\b[^\n]*(\s+\/\s*|\s+\/\*|\s+~|--no-preserve-root|\s+\/(?:etc|usr|var|bin|sbin|boot|System32)(?:\s|$))/i, score: 0.98 },
  { code: "drop_sql", check: "SQL DROP statement", regex: /\bDROP\s+(TABLE|DATABASE|SCHEMA)\b/i, score: 0.95 },
  { code: "truncate_sql", check: "SQL TRUNCATE statement", regex: /\bTRUNCATE\s+TABLE\b/i, score: 0.9 },
  { code: "delete_sql_unbounded", check: "SQL DELETE without WHERE", regex: /\bDELETE\s+FROM\s+[`'"]?\w+[`'"]?\s*;/i, score: 0.85 },
  { code: "disk_wipe", check: "Disk overwrite / format", regex: /\bdd\s+if=[^\s]+\s+of=\/dev\/|\bmkfs\.|format\s+[a-z]:/i, score: 0.98 },
  { code: "curl_pipe_shell", check: "Remote script piped to shell", regex: /\b(curl|wget)\s+[^\n|]+\|\s*(ba)?sh\b/i, score: 0.95 },
  { code: "powershell_iex", check: "PowerShell invoke-expression", regex: /\bInvoke-Expression\b|\biex\s*\(/i, score: 0.92 },
  { code: "powershell_rm_force", check: "PowerShell recursive force delete", regex: /Remove-Item\s+[^\n]*-Recurse[^\n]*-Force/i, score: 0.9 },
  { code: "windows_del_force", check: "Windows forced delete", regex: /\bdel\s+\/[fq]s?\b|Format-Volume/i, score: 0.9 },
  { code: "chmod_world_writable_root", check: "World-writable permissions on root", regex: /\bchmod\s+(-R\s+)?777\s+\//i, score: 0.88 },
  { code: "git_destructive", check: "Destructive git operation", regex: /\bgit\s+push\s+[^\n]*--force|\bgit\s+reset\s+--hard|\bgit\s+clean\s+-[a-z]*f/i, score: 0.85 },
  { code: "system_shutdown", check: "System shutdown or reboot", regex: /\b(shutdown|reboot|poweroff|halt)\s+(-[hfr]|\/s|now)\b/i, score: 0.88 },
  { code: "fork_bomb", check: "Fork bomb pattern", regex: /:\(\)\s*\{\s*:\|:/, score: 0.99 },
  { code: "eval_exec_injection", check: "Dynamic eval/exec of shell", regex: /\beval\s+[`$]|\bexec\s*\(\s*[`$]/i, score: 0.9 },
  { code: "iptables_flush", check: "Flush firewall rules", regex: /\biptables\s+-F\b/i, score: 0.85 },
  { code: "kill_all", check: "Kill all processes", regex: /\bkill(all)?\s+-9\s+(-1|0)\b|\bpkill\s+-9\b/i, score: 0.9 },
];

const SKILL_LINE_PATTERNS = [
  { code: "gateway_api_key", check: "Gateway API key", regex: /\bgrg_[A-Za-z0-9_-]{20,}\b/, score: 0.95 },
  { code: "database_url", check: "Database connection URL", regex: /\b(?:postgres(?:ql)?|mysql|mongodb|redis)(?:\+[a-z0-9]+)?:\/\/[^\s"']+/i, score: 0.92 },
  { code: "credential_assignment", check: "Hard-coded credential", regex: /(?:api[_-]?key|secret|password|token|auth)\s*[:=]\s*['"]?[^\s'"#,]{8,}/i, score: 0.88 },
  { code: "bearer_token", check: "Bearer token", regex: /Bearer\s+[A-Za-z0-9._-]{20,}/i, score: 0.9 },
  { code: "env_assignment", check: ".env-style secret", regex: /^[A-Z][A-Z0-9_]*\s*=\s*\S+/m, score: 0.75 },
  { code: "private_ip", check: "Private network address", regex: /\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b/, score: 0.55 },
  { code: "groq_api_key", check: "Groq API key", regex: /\bgsk_[A-Za-z0-9_-]{20,}\b/, score: 0.95 },
  { code: "openai_api_key", check: "OpenAI API key", regex: /\bsk-[A-Za-z0-9_-]{20,}\b/, score: 0.95 },
  { code: "ssn", check: "PII (SSN)", regex: /\b\d{3}-\d{2}-\d{4}\b/, score: 0.85 },
  { code: "credit_card", check: "PII (card)", regex: /\b(?:\d[ -]?){13,16}\b/, score: 0.85 },
];

const SKILL_OVERRIDE_STORAGE = "skill_guard_overrides";

const SKILL_EXPLANATIONS = {
  gateway_api_key: "A gateway API key in the skill could be sent to the model or logs.",
  groq_api_key: "A Groq API key in the skill can be exfiltrated through agent context.",
  openai_api_key: "An OpenAI API key in the skill can leak via agent transcripts.",
  secret_detected: "Credential-like material should live only in a secret manager.",
  pii_detected: "Personal data in skills may be sent to external models.",
  database_url: "A database URL with credentials allows data access if the agent runs tools.",
  credential_assignment: "Hard-coded secrets in instructions are often copied by agents.",
  rm_rf_destructive: "Recursive delete against system paths can wipe the machine.",
  drop_sql: "DROP statements can destroy tables if the agent executes SQL.",
  curl_pipe_shell: "Remote script piped to shell runs arbitrary code.",
};

function explainSkillFinding(f) {
  return SKILL_EXPLANATIONS[f.reason_code]
    || `${f.check}. This pattern can expose sensitive data or cause harmful actions when the agent runs tools.`;
}

function skillFindingKey(f) {
  return f.finding_key || `${f.reason_code}:${f.line_number || 0}`;
}

function loadSkillOverrides() {
  try {
    const raw = JSON.parse(localStorage.getItem(SKILL_OVERRIDE_STORAGE) || "{}");
    return {
      session_allow_keys: raw.session_allow_keys || [],
      always_allow_keys: raw.always_allow_keys || [],
      always_allow_reason_codes: raw.always_allow_reason_codes || [],
    };
  } catch {
    return { session_allow_keys: [], always_allow_keys: [], always_allow_reason_codes: [] };
  }
}

function saveSkillOverrides(overrides) {
  localStorage.setItem(SKILL_OVERRIDE_STORAGE, JSON.stringify(overrides));
}

function isFindingAllowed(f, overrides, sessionAllow) {
  const key = skillFindingKey(f);
  if (sessionAllow.includes(key)) return true;
  if (overrides.session_allow_keys.includes(key)) return true;
  if (overrides.always_allow_keys.includes(key)) return true;
  if (overrides.always_allow_reason_codes.includes(f.reason_code)) return true;
  return false;
}

function applySkillOverrides(scan, overrides, sessionAllow) {
  if (!scan?.findings?.length) {
    return { ...scan, blocking: [], overridden: [], agent_may_continue: true, blocked: false };
  }
  const blocking = [];
  const overridden = [];
  for (const f of scan.findings) {
    if (isFindingAllowed(f, overrides, sessionAllow)) overridden.push({ ...f, allowed_by_override: true });
    else blocking.push(f);
  }
  const agent_may_continue = blocking.length === 0;
  return {
    ...scan,
    blocking,
    overridden,
    agent_may_continue,
    blocked: !agent_may_continue,
    rejection_summary: agent_may_continue
      ? null
      : `Agent blocked: ${blocking.length} issue(s). Choose Run once, Always allow, or Reject for each item.`,
  };
}

function clientSkillScan(content) {
  if (!content.trim()) return { safe: true, risk_score: 0, findings: [] };
  const lines = content.split("\n");
  const findings = [];
  const seen = new Set();
  lines.forEach((line, idx) => {
    const lineNo = idx + 1;
    for (const p of [...SKILL_DANGEROUS_PATTERNS, ...SKILL_LINE_PATTERNS]) {
      if (p.regex.test(line)) {
        const key = `${p.code}:${lineNo}`;
        if (seen.has(key)) continue;
        seen.add(key);
        const snippet = line.trim().length > 72 ? line.trim().slice(0, 69) + "..." : line.trim();
        const category = SKILL_DANGEROUS_PATTERNS.some((d) => d.code === p.code)
          ? "destructive_command"
          : p.code.startsWith("ssn") || p.code === "credit_card"
            ? "pii"
            : ["groq_api_key", "openai_api_key"].includes(p.code)
              ? "secret"
              : "agent_context";
        const row = {
          finding_key: key,
          category,
          severity: p.score >= 0.9 ? "critical" : p.score >= 0.75 ? "high" : "medium",
          check: p.check,
          reason: `${p.check} on line ${lineNo}`,
          reason_code: p.code,
          line_number: lineNo,
          snippet,
          risk_score: p.score,
        };
        row.explanation = explainSkillFinding(row);
        findings.push(row);
      }
    }
  });
  const risk = findings.reduce((m, f) => Math.max(m, f.risk_score), 0);
  return { safe: findings.length === 0, risk_score: risk, findings };
}

/** Type text character-by-character or word-by-word when `active` becomes true. */
function useTypewriter(text, { speed = 36, delay = 0, active = false, wordByWord = false } = {}) {
  const [displayed, setDisplayed] = useState("");
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!active) {
      setDisplayed("");
      setDone(false);
      return;
    }

    setDisplayed("");
    setDone(false);
    
    const items = wordByWord ? text.split(" ") : text;
    let index = 0;
    let intervalId = null;
    
    const startId = window.setTimeout(() => {
      intervalId = window.setInterval(() => {
        index += 1;
        const next = wordByWord 
          ? items.slice(0, index).join(" ") + (index < items.length ? " " : "")
          : items.slice(0, index);
        setDisplayed(next);
        if (index >= items.length) {
          if (intervalId) window.clearInterval(intervalId);
          setDone(true);
        }
      }, speed);
    }, delay);

    return () => {
      window.clearTimeout(startId);
      if (intervalId) window.clearInterval(intervalId);
    };
  }, [text, speed, delay, active, wordByWord]);

  return { displayed, done };
}

function TypeCursor({ visible }) {
  if (!visible) return null;
  return <span className="auth-cursor">▍</span>;
}

function AuthFlowBackground() {
  const particles = [
    { left: "8%", delay: "0s", dur: "14s" },
    { left: "22%", delay: "2s", dur: "18s" },
    { left: "38%", delay: "4s", dur: "16s" },
    { left: "55%", delay: "1s", dur: "20s" },
    { left: "72%", delay: "3s", dur: "15s" },
    { left: "88%", delay: "5s", dur: "17s" },
  ];

  return (
    <div className="auth-flow-bg" aria-hidden>
      <div className="auth-flow-orb auth-flow-orb-1" />
      <div className="auth-flow-orb auth-flow-orb-2" />
      <div className="auth-flow-orb auth-flow-orb-3" />
      <svg className="auth-flow-svg" viewBox="0 0 1200 800" preserveAspectRatio="xMidYMid slice">
        <path className="auth-flow-path auth-flow-path-1" d="M-80 520 C 220 120, 420 680, 720 380 S 1180 180, 1320 420" />
        <path className="auth-flow-path auth-flow-path-2" d="M-60 180 C 280 420, 520 40, 760 260 S 1100 620, 1280 300" />
        <path className="auth-flow-path auth-flow-path-3" d="M 80 720 C 360 520, 600 760, 880 540 S 1240 320, 1320 580" />
      </svg>
      <div className="auth-flow-grid" />
      {particles.map((p, i) => (
        <span
          key={i}
          className="auth-flow-particle"
          style={{ left: p.left, animationDelay: p.delay, animationDuration: p.dur }}
        />
      ))}
    </div>
  );
}

function AuthTerminalIntro() {
  const [showPrompt, setShowPrompt] = useState(false);
  const [showThinking, setShowThinking] = useState(false);
  const [showResponse, setShowResponse] = useState(false);
  const [responseDone, setResponseDone] = useState(false);
  const [showFeatures, setShowFeatures] = useState(false);

  const promptText = useTypewriter(USER_PROMPT, {
    speed: 30, delay: 600, active: showPrompt, wordByWord: false
  });

  const responseText = useTypewriter(AI_RESPONSE, {
    speed: 25, delay: 0, active: showResponse, wordByWord: false
  });

  useEffect(() => {
    setShowPrompt(true);
  }, []);

  useEffect(() => {
    if (promptText.done) {
      setShowThinking(true);
      const id = window.setTimeout(() => {
        setShowThinking(false);
        setShowResponse(true);
      }, 800);
      return () => window.clearTimeout(id);
    }
  }, [promptText.done]);

  useEffect(() => {
    if (responseText.done) {
      setResponseDone(true);
      const id = window.setTimeout(() => setShowFeatures(true), 400);
      return () => window.clearTimeout(id);
    }
  }, [responseText.done]);

  return (
    <div style={authStyles.introPanel}>
      <div style={authStyles.terminal}>
        <div style={authStyles.terminalBar}>
          <span style={authStyles.dot("#ff5f57")} />
          <span style={authStyles.dot("#febc2e")} />
          <span style={authStyles.dot("#28c840")} />
          <span style={{...authStyles.terminalTitle, fontWeight: 600, fontFamily: "inherit"}}>AI Assistant</span>
        </div>
        <div style={{ ...authStyles.terminalBody, padding: "24px", fontFamily: "inherit" }}>
          
          {showPrompt && (
            <div style={{ display: "flex", gap: 14, marginBottom: 20 }}>
              <div style={{ flexShrink: 0, width: 32, height: 32, borderRadius: "50%", background: "#e2e8f0", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 13, fontWeight: 700, color: "#64748b" }}>U</div>
              <div style={{ flex: 1, background: "rgba(241, 245, 249, 0.6)", padding: "12px 16px", borderRadius: "12px", borderTopLeftRadius: "2px", color: "#334155", fontSize: 14, lineHeight: 1.5, border: "1px solid rgba(200, 215, 235, 0.4)", boxShadow: "0 2px 4px rgba(0,0,0,0.02)" }}>
                {promptText.displayed}
                {!promptText.done && <TypeCursor visible />}
              </div>
            </div>
          )}

          {(showThinking || showResponse) && (
            <div style={{ display: "flex", gap: 14, animation: "authFadeIn 0.3s ease forwards" }}>
              <div style={{ flexShrink: 0, width: 32, height: 32, borderRadius: "50%", background: "linear-gradient(135deg, #6366f1, #a855f7)", display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 13, fontWeight: 700, boxShadow: "0 4px 10px rgba(99, 102, 241, 0.3)" }}>AI</div>
              <div style={{ flex: 1, color: "#1e293b", fontSize: 14, lineHeight: 1.6, paddingTop: 5 }}>
                {showThinking && <span style={{ color: "#94a3b8", fontStyle: "italic", animation: "authBlink 1.5s infinite" }}>Analyzing request...</span>}
                {showResponse && (
                  <>
                    {responseText.displayed}
                    {!responseText.done && <TypeCursor visible />}
                  </>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {responseDone && (
        <div style={{ marginTop: 28 }} className="auth-intro-copy">
          <div style={authStyles.badge}>// live_gateway_active</div>
          <h1 style={authStyles.headline}>Ship LLM & agent workflows safely.</h1>
        </div>
      )}

      {showFeatures && (
        <div style={{ ...authStyles.featureGrid, animation: "authFadeIn 0.5s ease forwards", marginTop: 20 }}>
          {[
            ["LLM Gateway", "Blocks PII & injections"],
            ["Skill Guard", "Scans agent instructions"],
            ["Audit Log", "Tracks tokens & latency"],
          ].map(([title, desc]) => (
            <div key={title} style={authStyles.featureCard}>
              <div style={{...authStyles.featureTitle, fontFamily: "inherit"}}>{title}</div>
              <div style={{...authStyles.featureDesc, fontFamily: "inherit"}}>{desc}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const authStyles = {
  page: {
    position: "relative",
    minHeight: "100vh",
    background: "#f4f7fb",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: 24,
    overflow: "hidden",
  },
  pageInner: {
    position: "relative",
    zIndex: 1,
    width: "min(1100px, 100%)",
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit,minmax(340px,1fr))",
    gap: 28,
    alignItems: "center",
  },
  introPanel: { color: "#102033" },
  terminal: {
    background: "rgba(255, 255, 255, 0.6)",
    border: "1px solid rgba(255, 255, 255, 0.8)",
    backdropFilter: "blur(24px)",
    borderRadius: 12,
    overflow: "hidden",
    boxShadow: "0 24px 60px rgba(32, 48, 80, 0.08)",
  },
  terminalBar: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    padding: "10px 14px",
    background: "rgba(255, 255, 255, 0.4)",
    borderBottom: "1px solid rgba(200, 215, 235, 0.4)",
  },
  dot: (color) => ({
    width: 10,
    height: 10,
    borderRadius: "50%",
    background: color,
    display: "inline-block",
  }),
  terminalTitle: {
    marginLeft: 8,
    fontSize: 11,
    color: "#607086",
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
  },
  terminalBody: {
    margin: 0,
    padding: "16px 18px 20px",
    fontSize: 12.5,
    lineHeight: 1.65,
    color: "#304050",
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
    minHeight: 148,
  },
  badge: {
    display: "inline-flex",
    padding: "5px 10px",
    borderRadius: 6,
    background: "linear-gradient(135deg, #f0f5ff, #f5f3ff)",
    border: "1px solid #d8b4fe",
    color: "#7c3aed",
    fontSize: 11,
    fontWeight: 700,
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
    marginBottom: 14,
  },
  headline: {
    margin: 0,
    fontSize: "clamp(28px, 4vw, 40px)",
    lineHeight: 1.15,
    fontWeight: 800,
    color: "#102033",
    minHeight: "1.2em",
    letterSpacing: "-0.02em",
  },
  subhead: {
    margin: "14px 0 0",
    color: "#475569",
    fontSize: 15,
    lineHeight: 1.7,
    minHeight: 0,
  },
  featureGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))",
    gap: 12,
    marginTop: 24,
  },
  featureCard: {
    background: "rgba(255, 255, 255, 0.6)",
    border: "1px solid rgba(200, 215, 235, 0.6)",
    backdropFilter: "blur(12px)",
    borderRadius: 8,
    padding: 14,
  },
  featureTitle: {
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
    fontWeight: 700,
    color: "#6366f1",
    fontSize: 13,
  },
  featureDesc: { color: "#64748b", fontSize: 12, marginTop: 6 },
  formShell: { color: "#102033" },
  formCard: {
    background: "rgba(255,255,255,0.97)",
    border: "1px solid #dce7f0",
    borderRadius: 10,
    padding: 24,
    boxShadow: "0 20px 50px rgba(0,0,0,0.25)",
  },
  codeLabel: {
    fontSize: 11,
    fontWeight: 700,
    color: "#0f766e",
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
    letterSpacing: "0.02em",
  },
  codeInput: {
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
    fontSize: 13,
  },
  passwordWrap: { position: "relative", width: "100%" },
  passwordToggle: {
    position: "absolute",
    right: 8,
    top: "50%",
    transform: "translateY(-50%)",
    border: "none",
    background: "transparent",
    color: "#607086",
    fontSize: 11,
    fontWeight: 700,
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
    cursor: "pointer",
    padding: "6px 8px",
    borderRadius: 6,
    lineHeight: 1,
  },
};

function PasswordInput({ value, onChange, placeholder, autoComplete }) {
  const [visible, setVisible] = useState(false);

  return (
    <div style={authStyles.passwordWrap}>
      <input
        style={{ ...s.input, ...authStyles.codeInput, paddingRight: 72 }}
        type={visible ? "text" : "password"}
        placeholder={placeholder}
        value={value}
        onChange={onChange}
        autoComplete={autoComplete}
      />
      <button
        type="button"
        className="auth-password-toggle"
        style={authStyles.passwordToggle}
        onClick={() => setVisible((v) => !v)}
        aria-label={visible ? "Hide password" : "Show password"}
        title={visible ? "Hide password" : "Show password"}
      >
        {visible ? "hide()" : "show()"}
      </button>
    </div>
  );
}

function clientGuardrail(prompt) {
  for (const p of PII_PATTERNS) {
    if (p.regex.test(prompt)) return { blocked: true, reason: `PII detected: ${p.name}` };
  }
  const lower = prompt.toLowerCase();
  for (const kw of INJECTION_KW) {
    if (lower.includes(kw.toLowerCase())) return { blocked: true, reason: `Prompt injection: "${kw}"` };
  }
  for (const kw of JAILBREAK_KW) {
    if (lower.includes(kw.toLowerCase())) return { blocked: true, reason: `Jailbreak attempt: "${kw}"` };
  }
  return { blocked: false };
}

// STYLES
const s = {
  app: {
    minHeight: "100vh",
    background: "linear-gradient(135deg, #f8fbff 0%, #eef7f3 42%, #f7f9ff 100%)",
    color: "#102033",
    fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    display: "flex",
  },
  sidebar: {
    width: 260,
    background: "rgba(255,255,255,0.88)",
    borderRight: "1px solid #dbe8f3",
    padding: "22px 14px",
    display: "flex",
    flexDirection: "column",
    flexShrink: 0,
    boxShadow: "12px 0 40px rgba(17, 39, 68, 0.06)",
    backdropFilter: "blur(16px)",
  },
  logo: {
    padding: "0 10px 20px",
    borderBottom: "1px solid #e7eef6",
    marginBottom: 18,
  },
  logoText: {
    fontSize: 18,
    fontWeight: 800,
    letterSpacing: 0,
    color: "#102033",
  },
  logoSub: { fontSize: 12, color: "#607086", marginTop: 6, overflow: "hidden", textOverflow: "ellipsis" },
  navItem: (active) => ({
    display: "flex", alignItems: "center", gap: 10,
    padding: "11px 12px",
    cursor: "pointer",
    fontSize: 14,
    fontWeight: active ? 750 : 650,
    letterSpacing: 0,
    color: active ? "#0f5f7a" : "#607086",
    background: active ? "linear-gradient(135deg, #e8f8f3, #eef5ff)" : "transparent",
    border: active ? "1px solid #bfe8dd" : "1px solid transparent",
    borderRadius: 8,
    transition: "all 0.18s ease",
    userSelect: "none",
    marginBottom: 6,
  }),
  main: { flex: 1, overflow: "auto", padding: 32, maxWidth: 1520, margin: "0 auto" },
  pageTitle: {
    fontSize: 28, fontWeight: 850, marginBottom: 22,
    color: "#102033", letterSpacing: 0,
  },
  card: {
    background: "rgba(255,255,255,0.92)",
    border: "1px solid #dce7f0",
    borderRadius: 8,
    padding: 22,
    boxShadow: "0 16px 42px rgba(16, 32, 51, 0.07)",
  },
  statGrid: { display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(185px,1fr))", gap: 16, marginBottom: 24 },
  statCard: {
    background: "linear-gradient(180deg, #ffffff 0%, #f8fbff 100%)",
    border: "1px solid #dce7f0",
    borderRadius: 8,
    padding: 20,
    boxShadow: "0 12px 28px rgba(16, 32, 51, 0.06)",
  },
  statLabel: { fontSize: 12, color: "#607086", letterSpacing: 0, fontWeight: 750 },
  statValue: { fontSize: 32, fontWeight: 850, marginTop: 6, color: "#102033" },
  statSub:   { fontSize: 12, color: "#7b8a9d", marginTop: 4 },
  grid2: { display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(340px,1fr))", gap: 18, marginBottom: 24 },
  sectionTitle: { fontSize: 13, fontWeight: 800, letterSpacing: 0, color: "#27394f",
    marginBottom: 16 },
  table: { width: "100%", borderCollapse: "collapse" },
  th: { textAlign: "left", padding: "10px 12px", fontSize: 11, color: "#7b8a9d",
    letterSpacing: "0.04em", textTransform: "uppercase", borderBottom: "1px solid #e7eef6", whiteSpace: "nowrap" },
  td: { padding: "12px", fontSize: 13, borderBottom: "1px solid #eef3f8", color: "#405166" },
  badge: (status) => {
    const map = {
      delivered:      { bg: "#e8f8ef", color: "#067647", border: "#abe7c6" },
      input_blocked:  { bg: "#fff3e8", color: "#b45309", border: "#fed7aa" },
      output_blocked: { bg: "#fff7df", color: "#99620f", border: "#fde68a" },
      rate_limited:   { bg: "#eff6ff", color: "#1d4ed8", border: "#bfdbfe" },
      error:          { bg: "#fff1f2", color: "#be123c", border: "#fecdd3" },
    };
    const c = map[status] || { bg: "#eef3f8", color: "#405166", border: "#dce7f0" };
    return {
      display: "inline-flex", alignItems: "center", padding: "4px 9px", borderRadius: 999,
      fontSize: 11, fontWeight: 800, letterSpacing: 0,
      background: c.bg, color: c.color, border: `1px solid ${c.border}`,
    };
  },
  input: {
    width: "100%", background: "#ffffff", border: "1px solid #ccd9e6",
    borderRadius: 8, padding: "11px 12px", color: "#102033",
    fontFamily: "inherit", fontSize: 14, outline: "none",
    boxSizing: "border-box",
    boxShadow: "0 1px 0 rgba(16,32,51,0.03)",
  },
  btn: (variant = "primary") => ({
    padding: "10px 16px", borderRadius: 8, border: "1px solid transparent", cursor: "pointer",
    fontSize: 13, fontWeight: 800, letterSpacing: 0,
    fontFamily: "inherit",
    ...(variant === "primary"
      ? { background: "linear-gradient(135deg, #0f766e, #2563eb)", color: "#fff", boxShadow: "0 10px 22px rgba(37, 99, 235, 0.18)" }
      : variant === "danger"
      ? { background: "#fff1f2", color: "#be123c", border: "1px solid #fecdd3" }
      : { background: "#ffffff", color: "#405166", border: "1px solid #ccd9e6" }),
  }),
  toggle: (on) => ({
    width: 42, height: 24, borderRadius: 999, position: "relative",
    background: on ? "#0f766e" : "#cad6e2", border: "none", cursor: "pointer",
    transition: "background 0.2s", flexShrink: 0,
  }),
  toggleDot: (on) => ({
    position: "absolute", top: 3, left: on ? 21 : 3,
    width: 18, height: 18, borderRadius: "50%", background: "#fff",
    transition: "left 0.2s",
    boxShadow: "0 2px 8px rgba(16,32,51,0.18)",
  }),
  chip: (on) => ({
    padding: "7px 12px", borderRadius: 999, fontSize: 12, cursor: "pointer",
    border: on ? "1px solid #8ddfcf" : "1px solid #dce7f0",
    background: on ? "#e8f8f3" : "#ffffff",
    color: on ? "#0f766e" : "#607086",
    fontWeight: 750,
    userSelect: "none",
  }),
  alert: (type) => ({
    padding: "13px 15px", borderRadius: 8, fontSize: 13, marginBottom: 16,
    background: type === "error" ? "#fff1f2" : type === "success" ? "#e8f8ef" : "#eff6ff",
    border: `1px solid ${type === "error" ? "#fecdd3" : type === "success" ? "#abe7c6" : "#bfdbfe"}`,
    color: type === "error" ? "#be123c" : type === "success" ? "#067647" : "#1d4ed8",
    lineHeight: 1.5,
  }),
  muted: { color: "#7b8a9d", fontSize: 13 },
  label: { fontSize: 12, color: "#607086", fontWeight: 750, marginBottom: 6 },
  heroPanel: {
    background: "linear-gradient(135deg, #ffffff 0%, #ecfdf7 52%, #eff6ff 100%)",
    border: "1px solid #d3eadf",
    borderRadius: 8,
    padding: 24,
    marginBottom: 24,
    boxShadow: "0 18px 50px rgba(16, 32, 51, 0.08)",
  },
};

function GlobalStyles() {
  return (
    <style>{`
      * { box-sizing: border-box; }
      body { margin: 0; background: #f8fbff; }
      button, input, textarea, select { transition: box-shadow .18s ease, border-color .18s ease, transform .18s ease; }
      button:hover:not(:disabled) { transform: translateY(-1px); }
      button:disabled { opacity: .58; cursor: not-allowed; }
      input:focus, textarea:focus, select:focus { border-color: #0f766e !important; box-shadow: 0 0 0 3px rgba(15,118,110,.12) !important; }
      .auth-password-toggle:hover { color: #0f766e; background: rgba(15, 118, 110, 0.08); }
      .auth-password-toggle:focus-visible { outline: 2px solid #0f766e; outline-offset: 2px; }
      tr:last-child td { border-bottom: none !important; }
      @media (max-width: 760px) {
        .app-shell { flex-direction: column; }
        .app-sidebar { width: 100% !important; border-right: 0 !important; border-bottom: 1px solid #dbe8f3; }
        .app-main { padding: 18px !important; }
      }
      .auth-cursor {
        display: inline-block;
        margin-left: 2px;
        color: #6366f1;
        animation: authBlink 1s step-end infinite;
      }
      @keyframes authBlink {
        50% { opacity: 0; }
      }
      @keyframes authFadeIn {
        from { opacity: 0; transform: translateY(8px); }
        to { opacity: 1; transform: translateY(0); }
      }
      .auth-intro-copy {
        animation: authFadeIn 0.35s ease forwards;
      }

      .auth-flow-bg {
        position: absolute;
        inset: 0;
        z-index: 0;
        pointer-events: none;
        overflow: hidden;
        background: linear-gradient(145deg, #f4f7fb 0%, #ffffff 42%, #f5f3ff 100%);
      }
      .auth-flow-orb {
        position: absolute;
        border-radius: 50%;
        filter: blur(80px);
        opacity: 0.85;
        will-change: transform;
      }
      .auth-flow-orb-1 {
        width: 420px;
        height: 420px;
        background: radial-gradient(circle, rgba(139, 92, 246, 0.45) 0%, transparent 70%);
        top: -12%;
        left: -8%;
        animation: authOrbDrift1 22s ease-in-out infinite;
      }
      .auth-flow-orb-2 {
        width: 520px;
        height: 520px;
        background: radial-gradient(circle, rgba(59, 130, 246, 0.35) 0%, transparent 70%);
        bottom: -18%;
        right: -10%;
        animation: authOrbDrift2 26s ease-in-out infinite;
      }
      .auth-flow-orb-3 {
        width: 360px;
        height: 360px;
        background: radial-gradient(circle, rgba(16, 185, 129, 0.30) 0%, transparent 70%);
        top: 40%;
        left: 45%;
        animation: authOrbDrift3 20s ease-in-out infinite;
      }
      @keyframes authOrbDrift1 {
        0%, 100% { transform: translate(0, 0) scale(1); }
        50% { transform: translate(80px, 60px) scale(1.08); }
      }
      @keyframes authOrbDrift2 {
        0%, 100% { transform: translate(0, 0) scale(1); }
        50% { transform: translate(-70px, -50px) scale(1.1); }
      }
      @keyframes authOrbDrift3 {
        0%, 100% { transform: translate(-50%, -50%) scale(1); }
        50% { transform: translate(calc(-50% + 40px), calc(-50% - 30px)) scale(0.92); }
      }
      .auth-flow-svg {
        position: absolute;
        inset: -10%;
        width: 120%;
        height: 120%;
        opacity: 0.35;
      }
      .auth-flow-path {
        fill: none;
        stroke-width: 1.5;
        stroke-linecap: round;
        stroke-dasharray: 12 18;
        animation: authPathFlow 24s linear infinite;
      }
      .auth-flow-path-1 { stroke: rgba(139, 92, 246, 0.5); animation-duration: 28s; }
      .auth-flow-path-2 { stroke: rgba(59, 130, 246, 0.45); animation-duration: 22s; animation-direction: reverse; }
      .auth-flow-path-3 { stroke: rgba(45, 212, 191, 0.4); animation-duration: 32s; }
      @keyframes authPathFlow {
        from { stroke-dashoffset: 0; }
        to { stroke-dashoffset: -600; }
      }
      .auth-flow-grid {
        position: absolute;
        inset: 0;
        background-image:
          linear-gradient(rgba(100, 116, 139, 0.05) 1px, transparent 1px),
          linear-gradient(90deg, rgba(100, 116, 139, 0.05) 1px, transparent 1px);
        background-size: 48px 48px;
        -webkit-mask: radial-gradient(ellipse 80% 70% at 50% 50%, black 20%, transparent 75%);
        mask: radial-gradient(ellipse 80% 70% at 50% 50%, black 20%, transparent 75%);
        animation: authGridScroll 40s linear infinite;
      }
      @keyframes authGridScroll {
        from { background-position: 0 0, 0 0; }
        to { background-position: 0 48px, 48px 0; }
      }
      .auth-flow-particle {
        position: absolute;
        bottom: -20px;
        width: 4px;
        height: 4px;
        border-radius: 50%;
        background: rgba(139, 92, 246, 0.5);
        box-shadow: 0 0 12px rgba(139, 92, 246, 0.3);
        animation-name: authParticleRise;
        animation-timing-function: linear;
        animation-iteration-count: infinite;
      }
      @keyframes authParticleRise {
        0% { transform: translateY(0) scale(0.6); opacity: 0; }
        10% { opacity: 0.9; }
        90% { opacity: 0.35; }
        100% { transform: translateY(-110vh) scale(1); opacity: 0; }
      }
      @media (prefers-reduced-motion: reduce) {
        .auth-flow-orb,
        .auth-flow-path,
        .auth-flow-grid,
        .auth-flow-particle {
          animation: none !important;
        }
      }
    `}</style>
  );
}

// AUTH VIEW
function authScreenFromLocation() {
  const path = window.location.pathname.replace(/\/$/, "") || "/";
  const token = new URLSearchParams(window.location.search).get("token") || "";
  if (path.endsWith("/verify-email") && token) return { screen: "verify", token };
  if (path.endsWith("/reset-password") && token) return { screen: "reset", token };
  return { screen: "auth", token: "" };
}

function AuthView({ onAuth }) {
  const initial = authScreenFromLocation();
  const [tab, setTab] = useState("login");
  const [screen, setScreen] = useState(initial.screen);
  const [linkToken, setLinkToken] = useState(initial.token);
  const [form, setForm] = useState({
    email: "", password: "", full_name: "", org_name: "", new_password: "", confirm_password: "",
  });
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [loading, setLoading] = useState(false);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  function goHome() {
    window.history.replaceState({}, "", "/");
    setScreen("auth");
    setLinkToken("");
    setError("");
    setInfo("");
  }

  useEffect(() => {
    if (screen !== "verify" || !linkToken) return;
    setLoading(true);
    setError("");
    api("/auth/verify-email", { method: "POST", body: { token: linkToken } })
      .then((data) => {
        window.history.replaceState({}, "", "/");
        setScreen("auth");
        setLinkToken("");
        setTab("login");
        setInfo(data.message);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [screen, linkToken]);

  async function submit() {
    setError(""); setInfo(""); setLoading(true);
    try {
      if (tab === "login") {
        const data = await api("/auth/login", {
          method: "POST", body: { email: form.email, password: form.password },
        });
        setTokens(data.access_token, data.refresh_token);
        const me = await api("/auth/me");
        onAuth(me);
      } else if (tab === "signup") {
        const data = await api("/auth/signup", {
          method: "POST",
          body: {
            email: form.email, password: form.password,
            full_name: form.full_name,
            org_name: form.org_name || undefined,
          },
        });
        setInfo(data.message);
        setTab("login");
      } else if (tab === "forgot") {
        const data = await api("/auth/forgot-password", {
          method: "POST", body: { email: form.email },
        });
        setInfo(data.message);
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function submitReset() {
    setError(""); setInfo("");
    if (form.new_password !== form.confirm_password) {
      setError("Passwords do not match");
      return;
    }
    setLoading(true);
    try {
      const data = await api("/auth/reset-password", {
        method: "POST",
        body: { token: linkToken, new_password: form.new_password },
      });
      window.history.replaceState({}, "", "/");
      setScreen("auth");
      setLinkToken("");
      setTab("login");
      setInfo(data.message);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function resendVerification() {
    if (!form.email) {
      setError("Enter your email first");
      return;
    }
    setError(""); setInfo(""); setLoading(true);
    try {
      const data = await api("/auth/resend-verification", {
        method: "POST", body: { email: form.email },
      });
      setInfo(data.message);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
    <GlobalStyles />
    <div style={authStyles.page}>
      <AuthFlowBackground />
      <div style={authStyles.pageInner}>
        <AuthTerminalIntro />
        <div style={authStyles.formShell}>
        <div style={{ marginBottom: 18 }}>
          <div style={{ ...s.logoText, fontSize: 24 }}>LLM Guardrail</div>
          <div style={{ ...s.logoSub, fontSize: 13 }}>
            Sign in to manage your workspace
          </div>
        </div>
        <div style={authStyles.formCard}>
          <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 16, color: "#102033" }}>
            {screen === "verify" ? "Verify Email" :
             screen === "reset" ? "Reset Password" :
             tab === "forgot" ? "Reset Password" :
             tab === "signup" ? "Create an Account" : "Welcome Back"}
          </div>

          {screen === "auth" && (
            <div style={{ display: "flex", marginBottom: 24, background: "#eef3f8", borderRadius: 8, padding: 4 }}>
              {["login", "signup"].map((t) => (
                <div key={t} onClick={() => { setTab(t); setError(""); setInfo(""); }} style={{
                  flex: 1, textAlign: "center", padding: "9px", borderRadius: 7,
                  fontSize: 13, fontWeight: 850, cursor: "pointer",
                  background: tab === t ? "#ffffff" : "transparent",
                  color: tab === t ? "#0f5f7a" : "#607086",
                  boxShadow: tab === t ? "0 6px 18px rgba(16,32,51,0.08)" : "none",
                }}>{t === "login" ? "Sign in" : "Sign up"}</div>
              ))}
            </div>
          )}

          {error && <div style={s.alert("error")}>{error}</div>}
          {info && <div style={s.alert("success")}>{info}</div>}

          {screen === "verify" && (
            <div style={{ color: "#607086", fontSize: 14 }}>
              {loading ? "Verifying your email…" : "Verification complete. You can sign in."}
            </div>
          )}

          {screen === "reset" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <label style={s.label}>New Password</label>
              <PasswordInput
                placeholder="Min 8 characters"
                value={form.new_password}
                onChange={set("new_password")}
                autoComplete="new-password"
              />
              <label style={s.label}>Confirm Password</label>
              <PasswordInput
                placeholder="Confirm new password"
                value={form.confirm_password}
                onChange={set("confirm_password")}
                autoComplete="new-password"
              />
              <button style={{ ...s.btn("primary"), marginTop: 8 }} onClick={submitReset} disabled={loading}>
                {loading ? "Resetting..." : "Reset Password"}
              </button>
              <button type="button" style={s.btn("secondary")} onClick={goHome}>Back to sign in</button>
            </div>
          )}

          {screen === "auth" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {tab === "signup" && (
                <>
                  <label style={s.label}>Full Name</label>
                  <input style={s.input} placeholder="Jane Developer"
                    value={form.full_name} onChange={set("full_name")} />
                </>
              )}
              {(tab === "login" || tab === "signup" || tab === "forgot") && (
                <>
                  <label style={s.label}>Email Address</label>
                  <input style={s.input} placeholder="dev@acme.corp"
                    type="email" value={form.email} onChange={set("email")} autoComplete="email" />
                </>
              )}
              {tab !== "forgot" && (
                <>
                  <label style={s.label}>Password</label>
                  <PasswordInput
                    placeholder="••••••••"
                    value={form.password}
                    onChange={set("password")}
                    autoComplete={tab === "login" ? "current-password" : "new-password"}
                  />
                </>
              )}
              {tab === "signup" && (
                <>
                  <label style={s.label}>Organization Name (Optional)</label>
                  <input style={s.input} placeholder="Acme Corp"
                    value={form.org_name} onChange={set("org_name")} />
                </>
              )}
              <button style={{ ...s.btn("primary"), marginTop: 8 }} onClick={submit} disabled={loading}>
                {loading ? "Please wait..." :
                  tab === "login" ? "Sign In" :
                  tab === "forgot" ? "Send Reset Link" : "Create Account"}
              </button>
              {tab === "login" && (
                <button type="button" style={{ ...s.btn("secondary"), fontSize: 13 }}
                  onClick={() => { setTab("forgot"); setError(""); setInfo(""); }}>
                  Forgot password?
                </button>
              )}
              {tab === "forgot" && (
                <button type="button" style={{ ...s.btn("secondary"), fontSize: 13 }}
                  onClick={() => { setTab("login"); setError(""); setInfo(""); }}>
                  Back to login
                </button>
              )}
              {(tab === "login" || tab === "forgot") && (
                <button type="button" style={{ ...s.btn("secondary"), fontSize: 13 }}
                  onClick={resendVerification} disabled={loading}>
                  Resend verification email
                </button>
              )}
            </div>
          )}
        </div>
        <div style={{ textAlign:"center", marginTop:14, fontSize:11, color:"#607086",
          fontFamily: "ui-monospace, monospace" }}>
          {"// demo_mode: rate limits active"}
        </div>
        </div>
      </div>
    </div>
    </>
  );
}

// DASHBOARD VIEW
function DashboardView() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api("/analytics/dashboard?days=7")
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <div style={s.alert("error")}>{error}</div>;
  if (!data) return <div style={s.muted}>Loading dashboard...</div>;

  const { summary, time_series, top_rules, provider_usage = [], recent_suspicious = [], recent_logs } = data;
  const maxRule = Math.max(...(top_rules.map(r => r.count)), 1);
  const blockedTotal = summary.input_blocked + summary.output_blocked + (summary.rate_limited || 0);

  return (
    <div>
      <div style={s.heroPanel}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "flex-start", flexWrap: "wrap" }}>
          <div>
            <div style={{ ...s.pageTitle, marginBottom: 8 }}>Security Operations</div>
            <div style={{ color: "#405166", fontSize: 15, lineHeight: 1.6, maxWidth: 720 }}>
              Live view of LLM gateway traffic plus tools to keep agent skills free of secrets and internal data.
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <span style={s.badge("delivered")}>Groq connected</span>
            <span style={s.badge(blockedTotal > 0 ? "input_blocked" : "delivered")}>
              {blockedTotal > 0 ? "Threats blocked" : "No active threats"}
            </span>
          </div>
        </div>
      </div>

      {/* Stat cards */}
      <div style={s.statGrid}>
        {[
          { label: "Total Requests", value: summary.total_requests.toLocaleString(), sub: "last 7 days" },
          { label: "Blocked Requests", value: blockedTotal.toLocaleString(), sub: summary.block_rate_pct + "% of traffic" },
          { label: "Rate-Limit Hits", value: (summary.rate_limited || 0).toLocaleString(), sub: "quota protected" },
          { label: "Avg Latency", value: summary.avg_latency_ms + "ms", sub: "end-to-end" },
          { label: "Total Tokens", value: summary.total_tokens.toLocaleString(), sub: "in + out" },
        ].map(c => (
          <div key={c.label} style={s.statCard}>
            <div style={s.statLabel}>{c.label}</div>
            <div style={s.statValue}>{c.value}</div>
            <div style={s.statSub}>{c.sub}</div>
          </div>
        ))}
      </div>

      <div style={s.grid2}>
        {/* Area chart */}
        <div style={s.card}>
          <div style={s.sectionTitle}>Delivered vs Blocked</div>
          <ResponsiveContainer width="100%" height={180}>
            <AreaChart data={time_series} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e7eef6" />
              <XAxis dataKey="ts" tick={{ fontSize: 11, fill: "#7b8a9d" }} />
              <YAxis tick={{ fontSize: 11, fill: "#7b8a9d" }} />
              <Tooltip contentStyle={{ background: "#ffffff", border: "1px solid #dce7f0",
                borderRadius: 8, fontSize: 12, boxShadow: "0 12px 28px rgba(16,32,51,0.1)" }} />
              <Area type="monotone" dataKey="delivered" stroke="#0f766e" fill="#ccfbf1" strokeWidth={2} />
              <Area type="monotone" dataKey="blocked"   stroke="#f97316" fill="#ffedd5" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Top rules */}
        <div style={s.card}>
          <div style={s.sectionTitle}>Top Violation Types</div>
          {top_rules.length === 0
            ? <div style={s.muted}>No rules fired yet</div>
            : top_rules.map(r => (
              <div key={r.rule} style={{ marginBottom: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between",
                  fontSize: 11, marginBottom: 4 }}>
                  <span style={{ color: "#405166", fontWeight: 700 }}>{r.rule}</span>
                  <span style={{ color: "#0f766e", fontWeight: 850 }}>{r.count}</span>
                </div>
                <div style={{ height: 7, background: "#eef3f8", borderRadius: 999 }}>
                  <div style={{ height: "100%", borderRadius: 2,
                    width: (r.count / maxRule * 100) + "%",
                    background: "linear-gradient(90deg,#0f766e,#2563eb)", transition: "width 0.5s" }} />
                </div>
              </div>
            ))
          }
        </div>
      </div>

      <div style={s.grid2}>
        <div style={s.card}>
          <div style={s.sectionTitle}>Provider Usage</div>
          <table style={s.table}>
            <thead>
              <tr>
                {["Backend","Model","Requests","Tokens"].map(h => (
                  <th key={h} style={s.th}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {provider_usage.length === 0 ? (
                <tr><td colSpan={4} style={s.td}>No provider calls yet</td></tr>
              ) : provider_usage.map(p => (
                <tr key={`${p.backend}:${p.model}`}>
                  <td style={s.td}>{p.backend}</td>
                  <td style={{ ...s.td, maxWidth: 180, overflow: "hidden",
                    textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.model}</td>
                  <td style={s.td}>{p.count.toLocaleString()}</td>
                  <td style={s.td}>{p.tokens.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div style={s.card}>
          <div style={s.sectionTitle}>Recent Suspicious Prompts</div>
          <table style={s.table}>
            <thead>
              <tr>
                {["Status","Prompt","Reason","Time"].map(h => (
                  <th key={h} style={s.th}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {recent_suspicious.length === 0 ? (
                <tr><td colSpan={4} style={s.td}>No suspicious prompts yet</td></tr>
              ) : recent_suspicious.map(log => (
                <tr key={log.id}>
                  <td style={s.td}><span style={s.badge(log.status)}>{log.status}</span></td>
                  <td style={{ ...s.td, maxWidth: 180, overflow: "hidden",
                    textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{log.prompt_preview}</td>
                  <td style={{ ...s.td, maxWidth: 160, overflow: "hidden",
                    textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{log.reason || log.fired_rule || "-"}</td>
                  <td style={s.td}>{new Date(log.created_at).toLocaleTimeString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Recent logs */}
      <div style={s.card}>
        <div style={s.sectionTitle}>Recent Requests</div>
        <table style={s.table}>
          <thead>
            <tr>
              {["Status","Prompt","Rule Fired","Backend","Latency","Time"].map(h => (
                <th key={h} style={s.th}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {recent_logs.slice(0,10).map(log => (
              <tr key={log.id}>
                <td style={s.td}><span style={s.badge(log.status)}>{log.status}</span></td>
                <td style={{ ...s.td, maxWidth: 200, overflow: "hidden",
                  textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{log.prompt_preview}</td>
                <td style={s.td}>{log.fired_rule || "-"}</td>
                <td style={s.td}>{log.backend}</td>
                <td style={s.td}>{log.latency_ms}ms</td>
                <td style={s.td}>{new Date(log.created_at).toLocaleTimeString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// API KEYS VIEW
function ApiKeysView() {
  const [keys, setKeys] = useState([]);
  const [newName, setNewName] = useState("");
  const [rawKey, setRawKey] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const load = useCallback(() => {
    api("/api-keys").then(setKeys).catch((e) => setError(e.message));
  }, []);

  useEffect(() => { load(); }, [load]);

  async function create() {
    if (!newName.trim()) return;
    setError(""); setLoading(true);
    try {
      const data = await api("/api-keys", { method: "POST", body: { name: newName.trim() } });
      setRawKey(data.raw_key);
      setGatewayKey(data.raw_key);
      setNewName("");
      load();
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }

  async function revoke(id) {
    if (!confirm("Revoke this key?")) return;
    try {
      await api("/api-keys/" + id, { method: "DELETE" });
      load();
    } catch (e) { setError(e.message); }
  }

  return (
    <div>
      <div style={s.heroPanel}>
        <div style={{ ...s.pageTitle, marginBottom: 8 }}>Gateway API Keys</div>
        <div style={{ color: "#405166", fontSize: 15, lineHeight: 1.6 }}>
          Create scoped keys for applications that need guardrail protection before calling the LLM provider.
        </div>
      </div>

      {error && <div style={s.alert("error")}>{error}</div>}
      {keys.length === 0 && !rawKey && (
        <div style={s.alert("info")}>
          Create a gateway API key before using Chat Tester or integrating an app.
        </div>
      )}
      {rawKey && (
        <div style={s.alert("success")}>
          <div style={{ marginBottom: 6 }}>
            Key created and saved for Chat Tester. Use Copy key to grab the full value once — it is masked here and will not be shown again.
            The short prefix in the table is not enough to authenticate.
          </div>
          <code style={{ fontSize: 12, wordBreak: "break-all", color: "#067647", fontWeight: 800 }}>
            {maskGatewayKey(rawKey)}
          </code>
          <div style={{ marginTop: 8 }}>
            <button style={s.btn("secondary")} onClick={() => { navigator.clipboard.writeText(rawKey); }}>
              Copy key
            </button>
            <button style={{ ...s.btn("secondary"), marginLeft: 8 }} onClick={() => setRawKey("")}>
              Dismiss
            </button>
          </div>
        </div>
      )}

      <div style={{ ...s.card, marginBottom: 24 }}>
          <div style={s.sectionTitle}>Create new key</div>
        <div style={{ display: "flex", gap: 12 }}>
          <input style={{ ...s.input, flex: 1 }} placeholder="Key name (e.g. production)"
            value={newName} onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && create()} />
          <button style={s.btn("primary")} onClick={create} disabled={loading}>
            {loading ? "Creating..." : "Create"}
          </button>
        </div>
      </div>

      <div style={s.card}>
        <table style={s.table}>
          <thead>
            <tr>
              {["Name","Prefix","Requests","Blocked","Created","Status",""].map(h => (
                <th key={h} style={s.th}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {keys.map(k => (
              <tr key={k.id}>
                <td style={s.td}>{k.name}</td>
                <td style={{ ...s.td, fontFamily: "monospace", color: "#0f766e", fontWeight: 800 }}>
                  {maskGatewayKey(k.key_prefix + "0".repeat(24))}
                </td>
                <td style={s.td}>{k.total_requests.toLocaleString()}</td>
                <td style={s.td}>{k.total_blocked.toLocaleString()}</td>
                <td style={s.td}>{new Date(k.created_at).toLocaleDateString()}</td>
                <td style={s.td}>
                  <span style={s.badge(k.is_active ? "delivered" : "error")}>
                    {k.is_active ? "active" : "revoked"}
                  </span>
                </td>
                <td style={s.td}>
                  {k.is_active && (
                    <button style={s.btn("danger")} onClick={() => revoke(k.id)}>Revoke</button>
                  )}
                </td>
              </tr>
            ))}
            {keys.length === 0 && (
              <tr><td colSpan={7} style={{ ...s.td, textAlign: "center", color: "#7b8a9d" }}>
                No keys yet
              </td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// LOGS VIEW
function AdminView() {
  const [users, setUsers] = useState([]);
  const [keys, setKeys] = useState([]);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    Promise.all([api("/admin/users"), api("/admin/api-keys")])
      .then(([u, k]) => { setUsers(u); setKeys(k); })
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => { load(); }, [load]);

  async function patchUser(user, body) {
    setError("");
    try {
      await api("/admin/users/" + user.id, { method: "PATCH", body });
      load();
    } catch (e) { setError(e.message); }
  }

  async function revokeKey(id) {
    if (!confirm("Revoke this organization key?")) return;
    setError("");
    try {
      await api("/admin/api-keys/" + id, { method: "DELETE" });
      load();
    } catch (e) { setError(e.message); }
  }

  return (
    <div>
      <div style={s.heroPanel}>
        <div style={{ ...s.pageTitle, marginBottom: 8 }}>Admin Controls</div>
        <div style={{ color: "#405166", fontSize: 15, lineHeight: 1.6 }}>
          Manage organization users and revoke keys when access should be removed.
        </div>
      </div>
      {error && <div style={s.alert("error")}>{error}</div>}

      <div style={{ ...s.card, marginBottom: 24 }}>
        <div style={s.sectionTitle}>Organization Users</div>
        <table style={s.table}>
          <thead>
            <tr>{["Email","Name","Role","Status","Created",""].map(h => <th key={h} style={s.th}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {users.map(u => (
              <tr key={u.id}>
                <td style={s.td}>{u.email}</td>
                <td style={s.td}>{u.full_name}</td>
                <td style={s.td}>{u.is_admin ? "admin" : "member"}</td>
                <td style={s.td}><span style={s.badge(u.is_active ? "delivered" : "error")}>{u.is_active ? "active" : "disabled"}</span></td>
                <td style={s.td}>{new Date(u.created_at).toLocaleDateString()}</td>
                <td style={s.td}>
                  <button style={s.btn("secondary")} onClick={() => patchUser(u, { is_admin: !u.is_admin })}>
                    {u.is_admin ? "MEMBER" : "ADMIN"}
                  </button>
                  <button style={{ ...s.btn(u.is_active ? "danger" : "secondary"), marginLeft: 8 }}
                    onClick={() => patchUser(u, { is_active: !u.is_active })}>
                    {u.is_active ? "DISABLE" : "ENABLE"}
                  </button>
                </td>
              </tr>
            ))}
            {users.length === 0 && (
              <tr><td colSpan={6} style={s.td}>No users found</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div style={s.card}>
        <div style={s.sectionTitle}>Organization API Keys</div>
        <table style={s.table}>
          <thead>
            <tr>{["Name","Prefix","Requests","Blocked","Status",""].map(h => <th key={h} style={s.th}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {keys.map(k => (
              <tr key={k.id}>
                <td style={s.td}>{k.name}</td>
                <td style={{ ...s.td, fontFamily: "monospace", color: "#0f766e", fontWeight: 800 }}>
                  {maskGatewayKey(k.key_prefix + "0".repeat(24))}
                </td>
                <td style={s.td}>{k.total_requests.toLocaleString()}</td>
                <td style={s.td}>{k.total_blocked.toLocaleString()}</td>
                <td style={s.td}><span style={s.badge(k.is_active ? "delivered" : "error")}>{k.is_active ? "active" : "revoked"}</span></td>
                <td style={s.td}>{k.is_active && <button style={s.btn("danger")} onClick={() => revokeKey(k.id)}>Revoke</button>}</td>
              </tr>
            ))}
            {keys.length === 0 && (
              <tr><td colSpan={6} style={s.td}>No organization keys found</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function LogsView() {
  const [logs, setLogs] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [filter, setFilter] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const params = new URLSearchParams({ page, page_size: 25 });
    if (filter) params.set("status_filter", filter);
    api("/analytics/logs?" + params)
      .then((d) => { setLogs(d.items); setTotal(d.total); })
      .catch((e) => setError(e.message));
  }, [page, filter]);

  const filters = ["", "delivered", "input_blocked", "output_blocked", "error"];

  return (
    <div>
      <div style={s.heroPanel}>
        <div style={{ ...s.pageTitle, marginBottom: 8 }}>Request Logs</div>
        <div style={{ color: "#405166", fontSize: 15, lineHeight: 1.6 }}>
          Filter recent gateway activity and inspect blocked reasons, latency, tokens, and provider behavior.
        </div>
      </div>
      {error && <div style={s.alert("error")}>{error}</div>}

      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        {filters.map(f => (
          <div key={f} style={s.chip(filter === f)} onClick={() => { setFilter(f); setPage(1); }}>
            {f || "all"}
          </div>
        ))}
        <div style={{ marginLeft: "auto", fontSize: 12, color: "#607086", fontWeight: 750,
          alignSelf: "center" }}>{total} total</div>
      </div>

      <div style={s.card}>
        <table style={s.table}>
          <thead>
            <tr>
              {["Status","Prompt","Rule Fired","Backend","Latency","Tokens","Time"].map(h => (
                <th key={h} style={s.th}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {logs.map(log => (
              <tr key={log.id}>
                <td style={s.td}><span style={s.badge(log.status)}>{log.status}</span></td>
                <td style={{ ...s.td, maxWidth: 220, overflow: "hidden",
                  textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                  title={log.input_block_reason || log.output_block_reason || ""}>
                  {log.prompt_preview}
                </td>
                <td style={s.td}>{log.fired_rule || "-"}</td>
                <td style={s.td}>{log.backend}</td>
                <td style={s.td}>{log.latency_ms}ms</td>
                <td style={s.td}>{(log.input_tokens + log.output_tokens).toLocaleString()}</td>
                <td style={s.td}>{new Date(log.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>

        {/* Pagination */}
        <div style={{ display: "flex", justifyContent: "center", gap: 8,
          marginTop: 16, alignItems: "center" }}>
          <button style={s.btn("secondary")} disabled={page === 1}
            onClick={() => setPage(p => p - 1)}>Previous</button>
          <span style={{ fontSize: 11, color: "#6b7280" }}>
            Page {page} of {Math.ceil(total / 25) || 1}
          </span>
          <button style={s.btn("secondary")} disabled={page * 25 >= total}
            onClick={() => setPage(p => p + 1)}>Next</button>
        </div>
      </div>
    </div>
  );
}

// POLICY VIEW
function PolicyView({ user }) {
  const [policy, setPolicy] = useState(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [saving, setSaving] = useState(false);
  const [newTopic, setNewTopic] = useState("");

  useEffect(() => {
    api("/policy").then(setPolicy).catch((e) => setError(e.message));
  }, []);

  async function save() {
    if (!user.is_admin) return;
    setSaving(true); setError(""); setSuccess("");
    try {
      const updated = await api("/policy", { method: "PATCH", body: policy });
      setPolicy(updated);
      setSuccess("Policy saved.");
    } catch (e) { setError(e.message); }
    finally { setSaving(false); }
  }

  async function reset() {
    if (!confirm("Reset to defaults?")) return;
    try {
      const updated = await api("/policy/reset", { method: "POST" });
      setPolicy(updated);
      setSuccess("Policy reset to defaults.");
    } catch (e) { setError(e.message); }
  }

  if (error && !policy) return <div style={s.alert("error")}>{error}</div>;
  if (!policy) return <div style={s.muted}>Loading policy...</div>;

  const toggleRule = (section, key) => {
    setPolicy(p => ({
      ...p,
      [section]: { ...p[section], [key]: !p[section][key] },
    }));
  };

  const toggleTopic = (topic) => {
    const blocked = policy.topic_policy?.blocked_topics || [];
    const next = blocked.includes(topic)
      ? blocked.filter(t => t !== topic)
      : [...blocked, topic];
    setPolicy(p => ({ ...p, topic_policy: { ...p.topic_policy, blocked_topics: next } }));
  };

  const addTopic = () => {
    if (!newTopic.trim()) return;
    toggleTopic(newTopic.trim());
    setNewTopic("");
  };

  const blockedTopics = policy.topic_policy?.blocked_topics || [];
  const allTopics = [
    "competitor products", "medical advice", "legal advice",
    "financial advice", "politics", "adult content", "violence",
    ...blockedTopics.filter(t => !["competitor products","medical advice","legal advice",
      "financial advice","politics","adult content","violence"].includes(t)),
  ];

  const Rule = ({ label, section, k }) => (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
      padding: "12px 0", borderBottom: "1px solid #e7eef6" }}>
      <span style={{ fontSize: 13, color: "#405166", fontWeight: 700 }}>{label}</span>
      <button style={s.toggle(policy[section]?.[k])}
        onClick={() => user.is_admin && toggleRule(section, k)}>
        <div style={s.toggleDot(policy[section]?.[k])} />
      </button>
    </div>
  );

  return (
    <div>
      <div style={s.heroPanel}>
        <div style={{ ...s.pageTitle, marginBottom: 8 }}>Policy Editor</div>
        <div style={{ color: "#405166", fontSize: 15, lineHeight: 1.6 }}>
          Tune the organization rules that run before and after provider responses.
        </div>
      </div>
      {!user.is_admin && <div style={s.alert("info")}>View only. Admin access is required to edit.</div>}
      {error && <div style={s.alert("error")}>{error}</div>}
      {success && <div style={s.alert("success")}>{success}</div>}

      <div style={s.grid2}>
        <div style={s.card}>
          <div style={s.sectionTitle}>Input Guardrails</div>
          <Rule label="Block PII (SSN, credit cards, email)" section="input_rules" k="block_pii" />
          <Rule label="Block prompt injection" section="input_rules" k="block_prompt_injection" />
          <Rule label="Block jailbreak attempts" section="input_rules" k="block_jailbreak" />
        </div>
        <div style={s.card}>
          <div style={s.sectionTitle}>Output Guardrails</div>
          <Rule label="Block toxic content" section="output_rules" k="block_toxic_content" />
          <Rule label="Enforce schema validation" section="output_rules" k="enforce_schema" />
          <div style={{ ...s.sectionTitle, marginTop: 16 }}>Compliance</div>
          <Rule label="Block medical advice" section="compliance_rules" k="block_medical_advice" />
          <Rule label="Never discuss competitors" section="compliance_rules" k="never_discuss_competitors" />
        </div>
      </div>

      {/* Blocked topics */}
      <div style={{ ...s.card, marginBottom: 16 }}>
        <div style={s.sectionTitle}>Blocked Topics</div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 16 }}>
          {allTopics.map(t => (
            <div key={t} style={s.chip(blockedTopics.includes(t))}
              onClick={() => user.is_admin && toggleTopic(t)}>
              {t}
            </div>
          ))}
        </div>
        {user.is_admin && (
          <div style={{ display: "flex", gap: 8 }}>
            <input style={{ ...s.input, flex: 1 }} placeholder="Add custom topic..."
              value={newTopic} onChange={(e) => setNewTopic(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addTopic()} />
            <button style={s.btn("secondary")} onClick={addTopic}>ADD</button>
          </div>
        )}
      </div>

      {/* LLM backend */}
      <div style={{ ...s.card, marginBottom: 24 }}>
        <div style={s.sectionTitle}>LLM Backend Override</div>
        <div style={{ display: "flex", gap: 12 }}>
          <div style={{ flex: 1 }}>
            <div style={s.label}>Backend</div>
            <select style={{ ...s.input }} value={policy.llm_backend || ""}
              disabled={!user.is_admin}
              onChange={(e) => setPolicy(p => ({ ...p, llm_backend: e.target.value || null }))}>
              <option value="">Default</option>
              <option value="anthropic">Anthropic</option>
              <option value="openai">OpenAI</option>
              <option value="gemini">Gemini</option>
              <option value="groq">Groq</option>
              <option value="ollama">Ollama</option>
              <option value="openai_compatible">OpenAI-compatible</option>
              <option value="mock">Mock local</option>
            </select>
          </div>
          <div style={{ flex: 2 }}>
            <div style={s.label}>Model</div>
            <input style={s.input} placeholder="e.g. claude-sonnet-4-20250514"
              disabled={!user.is_admin}
              value={policy.llm_model || ""}
              onChange={(e) => setPolicy(p => ({ ...p, llm_model: e.target.value || null }))} />
          </div>
        </div>
      </div>

      {user.is_admin && (
        <div style={{ display: "flex", gap: 12 }}>
          <button style={s.btn("primary")} onClick={save} disabled={saving}>
            {saving ? "Saving..." : "Save policy"}
          </button>
          <button style={s.btn("secondary")} onClick={reset}>Reset defaults</button>
        </div>
      )}
    </div>
  );
}

// MARKDOWN RENDERER HELPERS
function parseInlineMarkdown(text) {
  if (!text) return "";
  const regex = /(\*\*.*?\*\*|`.*?`)/g;
  const tokens = text.split(regex);
  return tokens.map((token, i) => {
    if (token.startsWith("**") && token.endsWith("**")) {
      return <strong key={i} style={{ fontWeight: 700, color: "#1e293b" }}>{token.slice(2, -2)}</strong>;
    }
    if (token.startsWith("`") && token.endsWith("`")) {
      return (
        <code
          key={i}
          style={{
            background: "#f1f5f9",
            color: "#0f766e",
            padding: "2px 5px",
            borderRadius: 4,
            fontSize: "0.9em",
            fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
          }}
        >
          {token.slice(1, -1)}
        </code>
      );
    }
    return token;
  });
}

function MarkdownResponse({ text }) {
  if (!text) return null;
  const lines = text.split("\n");
  const elements = [];
  let currentList = [];

  const flushList = (key) => {
    if (currentList.length > 0) {
      elements.push(
        <ul key={`list-${key}`} style={{ margin: "8px 0 12px 20px", paddingLeft: 0, listStyleType: "disc" }}>
          {currentList}
        </ul>
      );
      currentList = [];
    }
  };

  lines.forEach((line, index) => {
    const trimmed = line.trim();
    if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
      const content = line.replace(/^[-*]\s+/, "");
      currentList.push(
        <li key={`li-${index}`} style={{ marginBottom: 6, lineHeight: 1.6 }}>
          {parseInlineMarkdown(content)}
        </li>
      );
    } else {
      flushList(index);
      if (trimmed === "") {
        elements.push(<div key={`space-${index}`} style={{ height: 8 }} />);
      } else {
        elements.push(
          <p key={`p-${index}`} style={{ margin: "0 0 12px 0", lineHeight: 1.65 }}>
            {parseInlineMarkdown(line)}
          </p>
        );
      }
    }
  });

  flushList(lines.length);
  return <div style={{ color: "#27394f", fontSize: 14 }}>{elements}</div>;
}

// CHAT TESTER VIEW
function ChatView() {
  const [prompt, setPrompt] = useState("");
  const [gatewayKey, setGatewayKeyState] = useState(getGatewayKey());
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [clientBlock, setClientBlock] = useState(null);

  function onGatewayKeyChange(e) {
    const key = e.target.value.trim();
    setGatewayKeyState(key);
    setGatewayKey(key);
  }

  function onPromptChange(e) {
    const val = e.target.value;
    setPrompt(val);
    setClientBlock(null);
    if (val) {
      const guard = clientGuardrail(val);
      if (guard.blocked) setClientBlock(guard.reason);
    }
  }

  async function send() {
    if (!prompt.trim()) return;
    if (!gatewayKey && !getToken()) {
      setResult({ error: "Sign in and create a gateway API key, or paste your full grg_ key here." });
      return;
    }
    const guard = clientGuardrail(prompt);
    if (guard.blocked) {
      setResult({ clientBlocked: true, reason: guard.reason });
      return;
    }
    setLoading(true); setResult(null);
    try {
      const headers = {};
      if (gatewayKey) headers["X-Api-Key"] = gatewayKey;
      const data = await api("/chat", {
        method: "POST",
        headers,
        body: { prompt: prompt.trim() },
      });
      setResult(data);
    } catch (e) {
      setResult({ error: e.message });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <div style={s.heroPanel}>
        <div style={{ ...s.pageTitle, marginBottom: 8 }}>LLM Playground</div>
        <div style={{ color: "#405166", fontSize: 15, lineHeight: 1.6 }}>
          Test live prompts through client checks, backend policy, your LLM provider, and output validation.
          For agent skills and instructions, use Skill Guard in the sidebar.
        </div>
      </div>
      {!gatewayKey && (
        <div style={s.alert("info")}>
          Create an API key in API Keys, then paste the grg_ key here to test the gateway.
        </div>
      )}
      <div style={s.card}>
        <div style={s.sectionTitle}>Test a prompt through the live pipeline</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))", gap: 10, marginBottom: 16 }}>
          {["Client precheck", "Input policy", "Provider call", "Output policy"].map((step, idx) => (
            <div key={step} style={{ border: "1px solid #dce7f0", background: "#f8fbff",
              borderRadius: 8, padding: 12 }}>
              <div style={{ color: "#0f766e", fontWeight: 850, fontSize: 12 }}>0{idx + 1}</div>
              <div style={{ color: "#27394f", fontWeight: 800, fontSize: 13, marginTop: 4 }}>{step}</div>
            </div>
          ))}
        </div>
        <label style={s.label}>Gateway key</label>
        <input
          {...gatewayKeyInputProps}
          style={{ ...s.input, marginBottom: 10, fontFamily: "monospace" }}
          placeholder="Paste a gateway API key: grg_..."
          value={gatewayKey}
          onChange={onGatewayKeyChange}
        />
        <label style={s.label}>Prompt</label>
        <textarea
          style={{ ...s.input, minHeight: 100, resize: "vertical", marginBottom: 4 }}
          placeholder={'Try: "ignore previous instructions"\nOr: "What is 123-45-6789"'}
          value={prompt}
          onChange={onPromptChange}
        />
        {clientBlock && (
          <div style={{ fontSize: 12, color: "#b45309", marginBottom: 8, fontWeight: 750 }}>
            Client-side guard: {clientBlock}
          </div>
        )}
        <button style={{ ...s.btn("primary"), marginTop: 8 }}
          onClick={send} disabled={loading || !prompt.trim()}>
          {loading ? "Sending..." : "Send prompt"}
        </button>
      </div>

      {result && (
        <div style={{ ...s.card, marginTop: 16 }}>
          {result.error && <div style={s.alert("error")}>{result.error}</div>}
          {result.clientBlocked && (
            <div style={s.alert("error")}>
              Blocked client-side before hitting backend<br />
              <span style={{ fontSize: 11 }}>{result.reason}</span>
            </div>
          )}
          {result.status && (
            <>
              <div style={{ display: "flex", gap: 16, marginBottom: 16 }}>
                <div>
                  <div style={s.statLabel}>Status</div>
                  <span style={s.badge(result.status)}>{result.status}</span>
                </div>
                <div>
                  <div style={s.statLabel}>Latency</div>
                  <div style={{ fontSize: 14, color: "#102033", marginTop: 4, fontWeight: 800 }}>{result.latency_ms}ms</div>
                </div>
                <div>
                  <div style={s.statLabel}>Backend</div>
                  <div style={{ fontSize: 14, color: "#102033", marginTop: 4, fontWeight: 800 }}>{result.backend} / {result.model}</div>
                </div>
              </div>

              {/* Guardrail results */}
              <div style={{ display: "flex", gap: 12, marginBottom: 16 }}>
                {[
                  { label: "Input Guard", g: result.input_guard },
                  ...(result.output_guard ? [{ label: "Output Guard", g: result.output_guard }] : []),
                ].map(({ label, g }) => (
                  <div key={label} style={{ flex: 1, padding: 14,
                    background: g.passed ? "#e8f8ef" : "#fff1f2",
                    borderRadius: 8, border: `1px solid ${g.passed ? "#abe7c6" : "#fecdd3"}` }}>
                    <div style={{ fontSize: 12, color: g.passed ? "#067647" : "#be123c",
                      fontWeight: 850, marginBottom: 4 }}>
                      {label}: {g.passed ? "PASS" : "BLOCK"}
                    </div>
                    <div style={{ fontSize: 12, color: "#405166" }}>{g.reason}</div>
                    <div style={{ fontSize: 11, color: "#7b8a9d", marginTop: 6 }}>
                      {g.reason_code} / risk {Math.round((g.risk_score || 0) * 100)}%
                    </div>
                  </div>
                ))}
              </div>

              {result.response && (
                <div>
                  <div style={s.sectionTitle}>Response</div>
                  <MarkdownResponse text={result.response} />
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

// SKILL GUARD VIEW
function SkillGuardView() {
  const [content, setContent] = useState(SKILL_SAMPLE_UNSAFE);
  const [filename, setFilename] = useState("SKILL.md");
  const [preview, setPreview] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [overrides, setOverrides] = useState(() => loadSkillOverrides());
  const [sessionAllow, setSessionAllow] = useState([]);

  useEffect(() => {
    setPreview(clientSkillScan(content));
  }, [content]);

  const rawDisplay = result || preview;
  const effective = rawDisplay
    ? applySkillOverrides(rawDisplay, overrides, sessionAllow)
    : null;

  async function runServerScan() {
    if (!content.trim()) return;
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const data = await api("/skills/scan", {
        method: "POST",
        body: {
          content,
          filename: filename.trim() || null,
          overrides: { ...overrides, session_allow_keys: sessionAllow },
        },
      });
      setResult(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  function onRunOnce(finding) {
    const key = skillFindingKey(finding);
    setSessionAllow((prev) => (prev.includes(key) ? prev : [...prev, key]));
  }

  function onAlwaysAllow(finding) {
    const key = skillFindingKey(finding);
    const next = {
      ...overrides,
      always_allow_keys: [...new Set([...overrides.always_allow_keys, key])],
      always_allow_reason_codes: [...new Set([...overrides.always_allow_reason_codes, finding.reason_code])],
    };
    saveSkillOverrides(next);
    setOverrides(next);
  }

  const severityColor = { critical: "#be123c", high: "#c2410c", medium: "#b45309" };

  return (
    <div>
      <div style={s.heroPanel}>
        <div style={{ ...s.pageTitle, marginBottom: 8 }}>Agent Skill Guard</div>
        <div style={{ color: "#405166", fontSize: 15, lineHeight: 1.6, maxWidth: 820 }}>
          Scan Cursor skills, MCP instructions, and system prompts before agents load them.
          Catch leaked secrets and PII, plus shell/SQL commands that could damage the host (rm -rf /, DROP TABLE, curl | bash, etc.).
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(140px,1fr))", gap: 10, marginBottom: 16 }}>
        {[
          ["01", "Paste skill", "Markdown or YAML instructions"],
          ["02", "Instant preview", "Client-side pattern match"],
          ["03", "Server scan", "Full policy-backed audit"],
          ["04", "Ship safe", "Redact findings before publish"],
        ].map(([num, title, desc]) => (
          <div key={title} style={{ border: "1px solid #dce7f0", background: "#f8fbff", borderRadius: 8, padding: 12 }}>
            <div style={{ color: "#0f766e", fontWeight: 850, fontSize: 12 }}>{num}</div>
            <div style={{ color: "#27394f", fontWeight: 800, fontSize: 13, marginTop: 4 }}>{title}</div>
            <div style={{ color: "#607086", fontSize: 11, marginTop: 4 }}>{desc}</div>
          </div>
        ))}
      </div>

      <div style={s.card}>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
          <button type="button" style={s.btn("secondary")} onClick={() => setContent(SKILL_SAMPLE_UNSAFE)}>
            Load risky example
          </button>
          <button type="button" style={s.btn("secondary")} onClick={() => setContent(SKILL_SAMPLE_SAFE)}>
            Load safe example
          </button>
        </div>
        <label style={s.label}>Filename (optional)</label>
        <input
          style={{ ...s.input, marginBottom: 10, fontFamily: "monospace" }}
          value={filename}
          onChange={(e) => setFilename(e.target.value)}
          placeholder="SKILL.md"
        />
        <label style={s.label}>Skill / instruction content</label>
        <textarea
          style={{ ...s.input, minHeight: 220, resize: "vertical", fontFamily: "ui-monospace, monospace", fontSize: 13 }}
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="Paste your agent skill, rules file, or system prompt..."
        />
        <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
          <button style={s.btn("primary")} onClick={runServerScan} disabled={loading || !content.trim()}>
            {loading ? "Scanning..." : "Run server scan"}
          </button>
          {effective && effective.blocked && (
            <span style={{ fontSize: 12, color: "#b45309", alignSelf: "center", fontWeight: 700 }}>
              {effective.blocking.length} issue(s) blocking agent
            </span>
          )}
        </div>
      </div>

      {error && <div style={{ ...s.alert("error"), marginTop: 16 }}>{error}</div>}

      {effective && (
        <div style={{ ...s.card, marginTop: 16 }}>
          <div style={{ display: "flex", gap: 16, marginBottom: 16, flexWrap: "wrap" }}>
            <div>
              <div style={s.statLabel}>Agent</div>
              <span style={s.badge(effective.agent_may_continue ? "delivered" : "input_blocked")}>
                {effective.agent_may_continue ? "May continue" : "Blocked"}
              </span>
            </div>
            <div>
              <div style={s.statLabel}>Raw scan</div>
              <span style={s.badge(effective.safe ? "delivered" : "input_blocked")}>
                {effective.safe ? "Clean" : `${effective.findings.length} finding(s)`}
              </span>
            </div>
            <div>
              <div style={s.statLabel}>Risk score</div>
              <div style={{ fontSize: 14, fontWeight: 800, marginTop: 4 }}>
                {Math.round((effective.risk_score || 0) * 100)}%
              </div>
            </div>
            {effective.line_count != null && (
              <div>
                <div style={s.statLabel}>Size</div>
                <div style={{ fontSize: 14, fontWeight: 800, marginTop: 4 }}>
                  {effective.line_count} lines · {(effective.char_count || content.length).toLocaleString()} chars
                </div>
              </div>
            )}
          </div>

          {effective.agent_may_continue && !effective.safe && (
            <div style={s.alert("success")}>
              Agent may continue — {effective.overridden.length} issue(s) allowed via Run once / Always allow.
              Review overrides before publishing to production.
            </div>
          )}

          {effective.safe && (
            <div style={s.alert("success")}>
              No blocking issues. Agent may continue; still review for business-sensitive prose.
            </div>
          )}

          {effective.blocked && (
            <>
              <div style={s.alert("error")}>
                <strong>Agent rejected — why:</strong>
                <div style={{ marginTop: 8, fontWeight: 500 }}>
                  {result?.rejection_summary || effective.rejection_summary}
                </div>
                <div style={{ marginTop: 8, fontSize: 13 }}>
                  For each issue choose: <strong>Run once</strong> (allow this time),
                  <strong> Always allow</strong> (skip this rule in future scans),
                  or <strong> Reject</strong> (keep blocked until you fix the skill).
                </div>
              </div>
              {effective.blocking.map((f, i) => (
                <div key={skillFindingKey(f) + i} style={{
                  marginTop: 12, padding: 14, borderRadius: 8,
                  border: "1px solid #fecdd3", background: "#fffbfb",
                }}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
                    <div style={{ fontWeight: 800, color: severityColor[f.severity] || "#be123c" }}>
                      [{f.severity}] {f.check}
                      {f.line_number ? ` · line ${f.line_number}` : ""}
                    </div>
                    <code style={{ fontSize: 11, color: "#7b8a9d" }}>{skillFindingKey(f)}</code>
                  </div>
                  <div style={{ fontSize: 13, color: "#405166", marginTop: 8, lineHeight: 1.5 }}>
                    {f.explanation || explainSkillFinding(f)}
                  </div>
                  <div style={{ fontSize: 12, fontFamily: "monospace", color: "#607086", marginTop: 8,
                    padding: 8, background: "#f8fafc", borderRadius: 6 }}>
                    {f.snippet}
                  </div>
                  <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
                    <button type="button" style={s.btn("primary")} onClick={() => onRunOnce(f)}>
                      Run once
                    </button>
                    <button type="button" style={s.btn("secondary")} onClick={() => onAlwaysAllow(f)}>
                      Always allow
                    </button>
                    <span style={{ fontSize: 12, color: "#7b8a9d", alignSelf: "center" }}>
                      Reject = leave blocked (fix skill text)
                    </span>
                  </div>
                </div>
              ))}
            </>
          )}

          {effective.overridden.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <div style={s.sectionTitle}>Allowed by override ({effective.overridden.length})</div>
              <table style={s.table}>
                <thead>
                  <tr>
                    {["Check", "Line", "Snippet"].map((h) => (
                      <th key={h} style={s.th}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {effective.overridden.map((f, i) => (
                    <tr key={`ov-${skillFindingKey(f)}-${i}`}>
                      <td style={s.td}>{f.check}</td>
                      <td style={s.td}>{f.line_number || "—"}</td>
                      <td style={{ ...s.td, fontFamily: "monospace", fontSize: 11 }}>{f.snippet}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      <div style={{ ...s.card, marginTop: 16 }}>
        <div style={s.sectionTitle}>Block pushes to GitHub (recommended)</div>
        <pre style={{ margin: 0, fontSize: 12, lineHeight: 1.5, padding: 14, background: "#f1f5f9",
          borderRadius: 8, border: "1px solid #dce7f0", overflow: "auto" }}>
{`# Once per clone — runs before every git push
./scripts/install-git-hooks.sh

# Windows
.\\scripts\\install-git-hooks.ps1`}
        </pre>
        <div style={{ color: "#607086", fontSize: 12, marginTop: 8 }}>
          On push, the hook explains each block and prompts:
          <strong> Run once</strong>, <strong>Always allow</strong>, or <strong>Reject</strong>
          (saved rules go to <code style={{ fontSize: 11 }}>.cursor/skill-guard-overrides.json</code>).
        </div>
      </div>

      <div style={{ ...s.card, marginTop: 16 }}>
        <div style={s.sectionTitle}>GitHub Actions (server-side)</div>
        <pre style={{ margin: 0, fontSize: 12, lineHeight: 1.5, padding: 14, background: "#f1f5f9",
          borderRadius: 8, border: "1px solid #dce7f0", overflow: "auto" }}>
{`# Workflow: .github/workflows/scan-agent-skills.yml
# - pull_request → scan all skills
# - push → scan only changed skill files

python scripts/scan_agent_skills.py
python scripts/scan_agent_skills.py --git-range origin/main..HEAD`}
        </pre>
        <div style={{ color: "#607086", fontSize: 12, marginTop: 8 }}>
          Catches issues even if a teammate skipped the local hook. Same rules as the dashboard scan.
        </div>
      </div>
    </div>
  );
}

// ROOT APP
const NAV = [
  { id: "dashboard", label: "Dashboard",    icon: "01" },
  { id: "chat",      label: "LLM Playground", icon: "02" },
  { id: "skills",    label: "Skill Guard",  icon: "SG" },
  { id: "logs",      label: "Logs",         icon: "03" },
  { id: "keys",      label: "API Keys",     icon: "04" },
  { id: "policy",    label: "Policy",       icon: "05" },
  { id: "admin",     label: "Admin",        icon: "A", adminOnly: true },
];

export default function App() {
  const [user, setUser] = useState(null);
  const [view, setView] = useState("dashboard");

  // Try to restore session
  useEffect(() => {
    if (getToken()) {
      api("/auth/me").then(setUser).catch(() => clearTokens());
    }
  }, []);

  function logout() { clearTokens(); setUser(null); }

  if (!user) return <><GlobalStyles /><AuthView onAuth={setUser} /></>;

  return (
    <div className="app-shell" style={s.app}>
      <GlobalStyles />
      {/* Sidebar */}
      <div className="app-sidebar" style={s.sidebar}>
        <div style={s.logo}>
          <div style={s.logoText}>AI Guardrails</div>
          <div style={{ fontSize: 11, color: "#7b8a9d", marginTop: 4 }}>LLM gateway · Agent skills</div>
          <div style={s.logoSub}>{user.email}</div>
          {user.is_admin && (
            <div style={{ display: "inline-flex", marginTop: 8, ...s.badge("rate_limited") }}>Admin</div>
          )}
        </div>
        {NAV.filter(n => !n.adminOnly || user.is_admin).map(n => (
          <div key={n.id} style={s.navItem(view === n.id)} onClick={() => setView(n.id)}>
            <span style={{ fontSize: 11, fontWeight: 850, color: view === n.id ? "#0f766e" : "#9aabba" }}>{n.icon}</span>
            <span>{n.label}</span>
          </div>
        ))}
        <div style={{ flex: 1 }} />
        <div style={{ ...s.navItem(false), marginTop: "auto" }} onClick={logout}>
          <span style={{ fontSize: 11, fontWeight: 850, color: "#9aabba" }}>--</span><span>Sign out</span>
        </div>
      </div>

      {/* Main */}
      <div className="app-main" style={s.main}>
        {view === "dashboard" && <DashboardView />}
        {view === "chat"      && <ChatView />}
        {view === "skills"    && <SkillGuardView />}
        {view === "logs"      && <LogsView />}
        {view === "keys"      && <ApiKeysView />}
        {view === "policy"    && <PolicyView user={user} />}
        {view === "admin"     && user.is_admin && <AdminView />}
      </div>
    </div>
  );
}


