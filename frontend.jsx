import React, { useState, useEffect, useCallback } from "react";
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis,
  Tooltip, ResponsiveContainer, CartesianGrid,
} from "recharts";

// ─── CONFIG ──────────────────────────────────────────────────────────────────
const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.DEV ? "http://localhost:8000" : "");

// ─── API HELPERS ─────────────────────────────────────────────────────────────
function getToken() { return localStorage.getItem("access_token"); }
function getGatewayKey() { return localStorage.getItem("gateway_api_key") || ""; }
function setGatewayKey(key) {
  if (key) localStorage.setItem("gateway_api_key", key);
  else localStorage.removeItem("gateway_api_key");
}
function setTokens(access, refresh) {
  localStorage.setItem("access_token", access);
  localStorage.setItem("refresh_token", refresh);
}
function clearTokens() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
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
    throw new Error(err.detail || "Request failed");
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

// ─── STYLES ──────────────────────────────────────────────────────────────────
const s = {
  app: {
    minHeight: "100vh",
    background: "#0a0a0f",
    color: "#e2e8f0",
    fontFamily: "'IBM Plex Mono', 'Fira Code', monospace",
    display: "flex",
  },
  sidebar: {
    width: 220,
    background: "#0f0f1a",
    borderRight: "1px solid #1e1e30",
    padding: "24px 0",
    display: "flex",
    flexDirection: "column",
    flexShrink: 0,
  },
  logo: {
    padding: "0 20px 24px",
    borderBottom: "1px solid #1e1e30",
    marginBottom: 16,
  },
  logoText: {
    fontSize: 13,
    fontWeight: 700,
    letterSpacing: "0.15em",
    color: "#7c3aed",
    textTransform: "uppercase",
  },
  logoSub: { fontSize: 10, color: "#4a4a6a", marginTop: 2, letterSpacing: "0.1em" },
  navItem: (active) => ({
    display: "flex", alignItems: "center", gap: 10,
    padding: "9px 20px",
    cursor: "pointer",
    fontSize: 12,
    letterSpacing: "0.05em",
    color: active ? "#a78bfa" : "#6b7280",
    background: active ? "#1a1a2e" : "transparent",
    borderLeft: active ? "2px solid #7c3aed" : "2px solid transparent",
    transition: "all 0.15s",
    userSelect: "none",
  }),
  main: { flex: 1, overflow: "auto", padding: 32 },
  pageTitle: {
    fontSize: 18, fontWeight: 700, marginBottom: 24,
    color: "#f1f5f9", letterSpacing: "0.05em",
  },
  card: {
    background: "#0f0f1a",
    border: "1px solid #1e1e30",
    borderRadius: 8,
    padding: 20,
  },
  statGrid: { display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(160px,1fr))", gap: 16, marginBottom: 24 },
  statCard: {
    background: "#0f0f1a",
    border: "1px solid #1e1e30",
    borderRadius: 8,
    padding: 20,
  },
  statLabel: { fontSize: 10, color: "#4a4a6a", letterSpacing: "0.12em", textTransform: "uppercase" },
  statValue: { fontSize: 28, fontWeight: 700, marginTop: 6, color: "#f1f5f9" },
  statSub:   { fontSize: 11, color: "#6b7280", marginTop: 4 },
  grid2: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 24 },
  sectionTitle: { fontSize: 11, fontWeight: 700, letterSpacing: "0.12em", color: "#6b7280",
    textTransform: "uppercase", marginBottom: 16 },
  table: { width: "100%", borderCollapse: "collapse" },
  th: { textAlign: "left", padding: "8px 12px", fontSize: 10, color: "#4a4a6a",
    letterSpacing: "0.1em", textTransform: "uppercase", borderBottom: "1px solid #1e1e30" },
  td: { padding: "10px 12px", fontSize: 12, borderBottom: "1px solid #0f0f1a", color: "#94a3b8" },
  badge: (status) => {
    const map = {
      delivered:      { bg: "#0d2d1a", color: "#34d399", border: "#065f46" },
      input_blocked:  { bg: "#2d1a0d", color: "#fb923c", border: "#7c2d12" },
      output_blocked: { bg: "#2d1a0d", color: "#f59e0b", border: "#78350f" },
      rate_limited:   { bg: "#1f1a0d", color: "#facc15", border: "#713f12" },
      error:          { bg: "#2d0d0d", color: "#f87171", border: "#7f1d1d" },
    };
    const c = map[status] || { bg: "#1e1e30", color: "#94a3b8", border: "#374151" };
    return {
      display: "inline-block", padding: "2px 8px", borderRadius: 4,
      fontSize: 10, fontWeight: 700, letterSpacing: "0.08em",
      background: c.bg, color: c.color, border: `1px solid ${c.border}`,
    };
  },
  input: {
    width: "100%", background: "#0a0a0f", border: "1px solid #1e1e30",
    borderRadius: 6, padding: "10px 12px", color: "#e2e8f0",
    fontFamily: "inherit", fontSize: 12, outline: "none",
    boxSizing: "border-box",
  },
  btn: (variant = "primary") => ({
    padding: "9px 18px", borderRadius: 6, border: "none", cursor: "pointer",
    fontSize: 12, fontWeight: 700, letterSpacing: "0.08em",
    fontFamily: "inherit",
    ...(variant === "primary"
      ? { background: "#7c3aed", color: "#fff" }
      : variant === "danger"
      ? { background: "#7f1d1d", color: "#fca5a5" }
      : { background: "#1e1e30", color: "#94a3b8", border: "1px solid #374151" }),
  }),
  toggle: (on) => ({
    width: 36, height: 20, borderRadius: 10, position: "relative",
    background: on ? "#7c3aed" : "#1e1e30", border: "none", cursor: "pointer",
    transition: "background 0.2s", flexShrink: 0,
  }),
  toggleDot: (on) => ({
    position: "absolute", top: 3, left: on ? 19 : 3,
    width: 14, height: 14, borderRadius: "50%", background: "#fff",
    transition: "left 0.2s",
  }),
  chip: (on) => ({
    padding: "4px 12px", borderRadius: 20, fontSize: 11, cursor: "pointer",
    border: on ? "1px solid #7c3aed" : "1px solid #1e1e30",
    background: on ? "#1a1230" : "transparent",
    color: on ? "#a78bfa" : "#6b7280",
    userSelect: "none",
  }),
  alert: (type) => ({
    padding: "12px 16px", borderRadius: 6, fontSize: 12, marginBottom: 16,
    background: type === "error" ? "#2d0d0d" : type === "success" ? "#0d2d1a" : "#1a1230",
    border: `1px solid ${type === "error" ? "#7f1d1d" : type === "success" ? "#065f46" : "#312e81"}`,
    color: type === "error" ? "#f87171" : type === "success" ? "#34d399" : "#a78bfa",
  }),
};

// ─── AUTH VIEW ───────────────────────────────────────────────────────────────
function AuthView({ onAuth }) {
  const [tab, setTab] = useState("login");
  const [form, setForm] = useState({ email: "", password: "", full_name: "", org_name: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  async function submit() {
    setError(""); setLoading(true);
    try {
      if (tab === "login") {
        const data = await api("/auth/login", {
          method: "POST", body: { email: form.email, password: form.password },
        });
        setTokens(data.access_token, data.refresh_token);
        const me = await api("/auth/me");
        onAuth(me);
      } else {
        await api("/auth/signup", {
          method: "POST",
          body: {
            email: form.email, password: form.password,
            full_name: form.full_name,
            org_name: form.org_name || undefined,
          },
        });
        // auto-login after signup
        const data = await api("/auth/login", {
          method: "POST", body: { email: form.email, password: form.password },
        });
        setTokens(data.access_token, data.refresh_token);
        const me = await api("/auth/me");
        onAuth(me);
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ minHeight: "100vh", background: "#0a0a0f", display: "flex",
      alignItems: "center", justifyContent: "center" }}>
      <div style={{ width: 380 }}>
        <div style={{ textAlign: "center", marginBottom: 32 }}>
          <div style={{ fontSize: 11, letterSpacing: "0.2em", color: "#7c3aed",
            textTransform: "uppercase", fontFamily: "'IBM Plex Mono',monospace" }}>
            ▣ LLM GUARDRAILS
          </div>
          <div style={{ fontSize: 11, color: "#4a4a6a", marginTop: 6,
            fontFamily: "monospace", letterSpacing: "0.05em" }}>
            Safety & compliance middleware
          </div>
        </div>
        <div style={{ ...s.card }}>
          {/* Tab toggle */}
          <div style={{ display: "flex", marginBottom: 24, background: "#0a0a0f",
            borderRadius: 6, padding: 3 }}>
            {["login","signup"].map(t => (
              <div key={t} onClick={() => setTab(t)} style={{
                flex: 1, textAlign: "center", padding: "7px", borderRadius: 4,
                fontSize: 11, letterSpacing: "0.1em", textTransform: "uppercase",
                cursor: "pointer", fontFamily: "monospace",
                background: tab === t ? "#7c3aed" : "transparent",
                color: tab === t ? "#fff" : "#4a4a6a",
                transition: "all 0.15s",
              }}>{t}</div>
            ))}
          </div>

          {error && <div style={s.alert("error")}>{error}</div>}

          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {tab === "signup" && (
              <input style={s.input} placeholder="Full name"
                value={form.full_name} onChange={set("full_name")} />
            )}
            <input style={s.input} placeholder="Email"
              type="email" value={form.email} onChange={set("email")} />
            <input style={s.input} placeholder="Password"
              type="password" value={form.password} onChange={set("password")} />
            {tab === "signup" && (
              <input style={s.input} placeholder="Organization name (optional)"
                value={form.org_name} onChange={set("org_name")} />
            )}
            <button style={{ ...s.btn("primary"), marginTop: 4 }}
              onClick={submit} disabled={loading}>
              {loading ? "..." : tab === "login" ? "SIGN IN" : "CREATE ACCOUNT"}
            </button>
          </div>
        </div>
        <div style={{ textAlign:"center", marginTop:16, fontSize:10, color:"#4a4a6a",
          fontFamily:"monospace", letterSpacing:"0.05em" }}>
          Set BASE_URL at top of file → your backend
        </div>
      </div>
    </div>
  );
}

// ─── DASHBOARD VIEW ──────────────────────────────────────────────────────────
function DashboardView() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api("/analytics/dashboard?days=7")
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <div style={s.alert("error")}>{error}</div>;
  if (!data) return <div style={{ color: "#4a4a6a", fontSize: 12 }}>Loading...</div>;

  const { summary, time_series, top_rules, provider_usage = [], recent_suspicious = [], recent_logs } = data;
  const maxRule = Math.max(...(top_rules.map(r => r.count)), 1);
  const blockedTotal = summary.input_blocked + summary.output_blocked + (summary.rate_limited || 0);

  return (
    <div>
      <div style={s.pageTitle}>Dashboard</div>

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
              <CartesianGrid strokeDasharray="3 3" stroke="#1e1e30" />
              <XAxis dataKey="ts" tick={{ fontSize: 10, fill: "#4a4a6a" }} />
              <YAxis tick={{ fontSize: 10, fill: "#4a4a6a" }} />
              <Tooltip contentStyle={{ background: "#0f0f1a", border: "1px solid #1e1e30",
                borderRadius: 4, fontSize: 11, fontFamily: "monospace" }} />
              <Area type="monotone" dataKey="delivered" stroke="#34d399" fill="#0d2d1a" strokeWidth={2} />
              <Area type="monotone" dataKey="blocked"   stroke="#f87171" fill="#2d0d0d" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Top rules */}
        <div style={s.card}>
          <div style={s.sectionTitle}>Top Violation Types</div>
          {top_rules.length === 0
            ? <div style={{ color: "#4a4a6a", fontSize: 12 }}>No rules fired yet</div>
            : top_rules.map(r => (
              <div key={r.rule} style={{ marginBottom: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between",
                  fontSize: 11, marginBottom: 4 }}>
                  <span style={{ color: "#94a3b8" }}>{r.rule}</span>
                  <span style={{ color: "#7c3aed" }}>{r.count}</span>
                </div>
                <div style={{ height: 4, background: "#1e1e30", borderRadius: 2 }}>
                  <div style={{ height: "100%", borderRadius: 2,
                    width: (r.count / maxRule * 100) + "%",
                    background: "#7c3aed", transition: "width 0.5s" }} />
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
                <td style={s.td}>{log.fired_rule || "—"}</td>
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

// ─── API KEYS VIEW ───────────────────────────────────────────────────────────
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
      <div style={s.pageTitle}>API Keys</div>

      {error && <div style={s.alert("error")}>{error}</div>}
      {keys.length === 0 && !rawKey && (
        <div style={s.alert("info")}>
          Create a gateway API key before using Chat Tester or integrating an app.
        </div>
      )}
      {rawKey && (
        <div style={s.alert("success")}>
          <div style={{ marginBottom: 6 }}>Key created — copy it now, it won't be shown again:</div>
          <code style={{ fontSize: 11, wordBreak: "break-all", color: "#34d399" }}>{rawKey}</code>
          <div style={{ marginTop: 8 }}>
            <button style={s.btn("secondary")} onClick={() => { navigator.clipboard.writeText(rawKey); }}>
              COPY
            </button>
            <button style={{ ...s.btn("secondary"), marginLeft: 8 }} onClick={() => setRawKey("")}>
              DISMISS
            </button>
          </div>
        </div>
      )}

      <div style={{ ...s.card, marginBottom: 24 }}>
        <div style={s.sectionTitle}>Create New Key</div>
        <div style={{ display: "flex", gap: 12 }}>
          <input style={{ ...s.input, flex: 1 }} placeholder="Key name (e.g. production)"
            value={newName} onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && create()} />
          <button style={s.btn("primary")} onClick={create} disabled={loading}>
            {loading ? "..." : "CREATE"}
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
                <td style={{ ...s.td, fontFamily: "monospace", color: "#7c3aed" }}>{k.key_prefix}…</td>
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
                    <button style={s.btn("danger")} onClick={() => revoke(k.id)}>REVOKE</button>
                  )}
                </td>
              </tr>
            ))}
            {keys.length === 0 && (
              <tr><td colSpan={7} style={{ ...s.td, textAlign: "center", color: "#4a4a6a" }}>
                No keys yet
              </td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─── LOGS VIEW ───────────────────────────────────────────────────────────────
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
      <div style={s.pageTitle}>Admin</div>
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
                <td style={{ ...s.td, fontFamily: "monospace", color: "#7c3aed" }}>{k.key_prefix}...</td>
                <td style={s.td}>{k.total_requests.toLocaleString()}</td>
                <td style={s.td}>{k.total_blocked.toLocaleString()}</td>
                <td style={s.td}><span style={s.badge(k.is_active ? "delivered" : "error")}>{k.is_active ? "active" : "revoked"}</span></td>
                <td style={s.td}>{k.is_active && <button style={s.btn("danger")} onClick={() => revokeKey(k.id)}>REVOKE</button>}</td>
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
      <div style={s.pageTitle}>Request Logs</div>
      {error && <div style={s.alert("error")}>{error}</div>}

      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        {filters.map(f => (
          <div key={f} style={s.chip(filter === f)} onClick={() => { setFilter(f); setPage(1); }}>
            {f || "all"}
          </div>
        ))}
        <div style={{ marginLeft: "auto", fontSize: 11, color: "#4a4a6a",
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
                <td style={s.td}>{log.fired_rule || "—"}</td>
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
            onClick={() => setPage(p => p - 1)}>← PREV</button>
          <span style={{ fontSize: 11, color: "#6b7280" }}>
            Page {page} of {Math.ceil(total / 25) || 1}
          </span>
          <button style={s.btn("secondary")} disabled={page * 25 >= total}
            onClick={() => setPage(p => p + 1)}>NEXT →</button>
        </div>
      </div>
    </div>
  );
}

// ─── POLICY VIEW ─────────────────────────────────────────────────────────────
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
  if (!policy) return <div style={{ color: "#4a4a6a", fontSize: 12 }}>Loading...</div>;

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
      padding: "12px 0", borderBottom: "1px solid #1e1e30" }}>
      <span style={{ fontSize: 12, color: "#94a3b8" }}>{label}</span>
      <button style={s.toggle(policy[section]?.[k])}
        onClick={() => user.is_admin && toggleRule(section, k)}>
        <div style={s.toggleDot(policy[section]?.[k])} />
      </button>
    </div>
  );

  return (
    <div>
      <div style={s.pageTitle}>Policy Editor</div>
      {!user.is_admin && <div style={s.alert("info")}>View only — admin access required to edit</div>}
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
            <input style={{ ...s.input, flex: 1 }} placeholder="Add custom topic…"
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
            <div style={{ fontSize: 11, color: "#4a4a6a", marginBottom: 6 }}>Backend</div>
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
            <div style={{ fontSize: 11, color: "#4a4a6a", marginBottom: 6 }}>Model</div>
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
            {saving ? "SAVING..." : "SAVE POLICY"}
          </button>
          <button style={s.btn("secondary")} onClick={reset}>RESET DEFAULTS</button>
        </div>
      )}
    </div>
  );
}

// ─── CHAT TESTER VIEW ────────────────────────────────────────────────────────
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
    if (!gatewayKey) {
      setResult({ error: "Enter a gateway API key first. Create one in API Keys, then paste the grg_ key here." });
      return;
    }
    const guard = clientGuardrail(prompt);
    if (guard.blocked) {
      setResult({ clientBlocked: true, reason: guard.reason });
      return;
    }
    setLoading(true); setResult(null);
    try {
      const data = await api("/chat", {
        method: "POST",
        headers: { "X-Api-Key": gatewayKey },
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
      <div style={s.pageTitle}>Chat Tester</div>
      {!gatewayKey && (
        <div style={s.alert("info")}>
          Create an API key in API Keys, then paste the grg_ key here to test the gateway.
        </div>
      )}
      <div style={s.card}>
        <div style={s.sectionTitle}>Test a prompt through the live pipeline</div>
        <input
          style={{ ...s.input, marginBottom: 10 }}
          placeholder="Paste a gateway API key: grg_..."
          value={gatewayKey}
          onChange={onGatewayKeyChange}
        />
        <textarea
          style={{ ...s.input, minHeight: 100, resize: "vertical", marginBottom: 4 }}
          placeholder={'Try: "ignore previous instructions"\nOr: "What is 123-45-6789"'}
          value={prompt}
          onChange={onPromptChange}
        />
        {clientBlock && (
          <div style={{ fontSize: 11, color: "#fb923c", marginBottom: 8 }}>
            ⚡ Client-side guard: {clientBlock}
          </div>
        )}
        <button style={{ ...s.btn("primary"), marginTop: 8 }}
          onClick={send} disabled={loading || !prompt.trim()}>
          {loading ? "SENDING..." : "SEND →"}
        </button>
      </div>

      {result && (
        <div style={{ ...s.card, marginTop: 16 }}>
          {result.error && <div style={s.alert("error")}>{result.error}</div>}
          {result.clientBlocked && (
            <div style={s.alert("error")}>
              🚫 Blocked client-side before hitting backend<br />
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
                  <div style={{ fontSize: 14, color: "#f1f5f9", marginTop: 4 }}>{result.latency_ms}ms</div>
                </div>
                <div>
                  <div style={s.statLabel}>Backend</div>
                  <div style={{ fontSize: 14, color: "#f1f5f9", marginTop: 4 }}>{result.backend} / {result.model}</div>
                </div>
              </div>

              {/* Guardrail results */}
              <div style={{ display: "flex", gap: 12, marginBottom: 16 }}>
                {[
                  { label: "Input Guard", g: result.input_guard },
                  ...(result.output_guard ? [{ label: "Output Guard", g: result.output_guard }] : []),
                ].map(({ label, g }) => (
                  <div key={label} style={{ flex: 1, padding: 12,
                    background: g.passed ? "#0d2d1a" : "#2d0d0d",
                    borderRadius: 6, border: `1px solid ${g.passed ? "#065f46" : "#7f1d1d"}` }}>
                    <div style={{ fontSize: 10, color: g.passed ? "#34d399" : "#f87171",
                      letterSpacing: "0.1em", marginBottom: 4 }}>
                      {label}: {g.passed ? "✓ PASS" : "✗ BLOCK"}
                    </div>
                    <div style={{ fontSize: 11, color: "#94a3b8" }}>{g.reason}</div>
                    <div style={{ fontSize: 10, color: "#6b7280", marginTop: 6 }}>
                      {g.reason_code} · risk {Math.round((g.risk_score || 0) * 100)}%
                    </div>
                  </div>
                ))}
              </div>

              {result.response && (
                <div>
                  <div style={s.sectionTitle}>Response</div>
                  <div style={{ fontSize: 13, color: "#e2e8f0", lineHeight: 1.6,
                    whiteSpace: "pre-wrap" }}>{result.response}</div>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ─── ROOT APP ────────────────────────────────────────────────────────────────
const NAV = [
  { id: "dashboard", label: "Dashboard",   icon: "▣" },
  { id: "chat",      label: "Chat Tester", icon: "◈" },
  { id: "logs",      label: "Logs",        icon: "≡" },
  { id: "keys",      label: "API Keys",    icon: "⊕" },
  { id: "policy",    label: "Policy",      icon: "◎" },
  { id: "admin",     label: "Admin",       icon: "A", adminOnly: true },
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

  if (!user) return <AuthView onAuth={setUser} />;

  return (
    <div style={s.app}>
      {/* Sidebar */}
      <div style={s.sidebar}>
        <div style={s.logo}>
          <div style={s.logoText}>▣ Guardrails</div>
          <div style={s.logoSub}>{user.email}</div>
          {user.is_admin && (
            <div style={{ fontSize: 9, color: "#7c3aed", marginTop: 2,
              letterSpacing: "0.1em" }}>ADMIN</div>
          )}
        </div>
        {NAV.filter(n => !n.adminOnly || user.is_admin).map(n => (
          <div key={n.id} style={s.navItem(view === n.id)} onClick={() => setView(n.id)}>
            <span>{n.icon}</span>
            <span>{n.label}</span>
          </div>
        ))}
        <div style={{ flex: 1 }} />
        <div style={{ ...s.navItem(false), marginTop: "auto" }} onClick={logout}>
          <span>⊗</span><span>Sign out</span>
        </div>
      </div>

      {/* Main */}
      <div style={s.main}>
        {view === "dashboard" && <DashboardView />}
        {view === "chat"      && <ChatView />}
        {view === "logs"      && <LogsView />}
        {view === "keys"      && <ApiKeysView />}
        {view === "policy"    && <PolicyView user={user} />}
        {view === "admin"     && user.is_admin && <AdminView />}
      </div>
    </div>
  );
}


