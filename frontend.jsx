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
      tr:last-child td { border-bottom: none !important; }
      @media (max-width: 760px) {
        .app-shell { flex-direction: column; }
        .app-sidebar { width: 100% !important; border-right: 0 !important; border-bottom: 1px solid #dbe8f3; }
        .app-main { padding: 18px !important; }
      }
    `}</style>
  );
}

// AUTH VIEW
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
    <div style={{ minHeight: "100vh", background: "linear-gradient(135deg,#f8fbff,#eefaf5 48%,#f7f9ff)", display: "flex",
      alignItems: "center", justifyContent: "center", padding: 24 }}>
      <div style={{ width: "min(1040px, 100%)", display: "grid",
        gridTemplateColumns: "repeat(auto-fit,minmax(340px,1fr))", gap: 28, alignItems: "center" }}>
        <div style={s.heroPanel}>
          <div style={{ display: "inline-flex", padding: "6px 10px",
            borderRadius: 999, background: "#e8f8f3", color: "#0f766e", fontSize: 12,
            fontWeight: 800, marginBottom: 18 }}>
            Live Groq gateway
          </div>
          <h1 style={{ margin: 0, fontSize: 44, lineHeight: 1.05, color: "#102033", letterSpacing: 0 }}>
            Ship LLM apps with a safety layer in front.
          </h1>
          <p style={{ margin: "16px 0 24px", color: "#405166", fontSize: 16, lineHeight: 1.7 }}>
            Test prompts, block injection attempts, enforce policy rules, and monitor provider usage from one clean dashboard.
          </p>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))", gap: 12 }}>
            {[["Input guard", "PII and injection checks"], ["Output guard", "Toxic and policy filters"], ["Audit trail", "Logs, tokens, latency"]].map(([title, desc]) => (
              <div key={title} style={{ background: "#fff", border: "1px solid #dce7f0", borderRadius: 8, padding: 14 }}>
                <div style={{ fontWeight: 850, color: "#102033", fontSize: 14 }}>{title}</div>
                <div style={{ color: "#607086", fontSize: 12, marginTop: 5 }}>{desc}</div>
              </div>
            ))}
          </div>
        </div>
        <div>
        <div style={{ marginBottom: 18 }}>
          <div style={{ ...s.logoText, fontSize: 24 }}>LLM Guardrail</div>
          <div style={{ ...s.logoSub, fontSize: 13 }}>Safety and compliance middleware</div>
        </div>
        <div style={{ ...s.card, padding: 24 }}>
          <div style={{ display: "flex", marginBottom: 24, background: "#eef3f8", borderRadius: 8, padding: 4 }}>
            {["login","signup"].map(t => (
              <div key={t} onClick={() => setTab(t)} style={{
                flex: 1, textAlign: "center", padding: "9px", borderRadius: 7,
                fontSize: 13, fontWeight: 850, cursor: "pointer",
                background: tab === t ? "#ffffff" : "transparent",
                color: tab === t ? "#0f5f7a" : "#607086",
                boxShadow: tab === t ? "0 6px 18px rgba(16,32,51,0.08)" : "none",
                transition: "all 0.18s ease",
              }}>{t}</div>
            ))}
          </div>

          {error && <div style={s.alert("error")}>{error}</div>}

          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {tab === "signup" && (
              <>
                <label style={s.label}>Full name</label>
                <input style={s.input} placeholder="Full name" value={form.full_name} onChange={set("full_name")} />
              </>
            )}
            <label style={s.label}>Email</label>
            <input style={s.input} placeholder="you@example.com" type="email" value={form.email} onChange={set("email")} />
            <label style={s.label}>Password</label>
            <input style={s.input} placeholder="Your password" type="password" value={form.password} onChange={set("password")} />
            {tab === "signup" && (
              <>
                <label style={s.label}>Organization</label>
                <input style={s.input} placeholder="Organization name (optional)" value={form.org_name} onChange={set("org_name")} />
              </>
            )}
            <button style={{ ...s.btn("primary"), marginTop: 8 }} onClick={submit} disabled={loading}>
              {loading ? "Working..." : tab === "login" ? "Sign in" : "Create account"}
            </button>
          </div>
        </div>
        <div style={{ textAlign:"center", marginTop:14, fontSize:12, color:"#7b8a9d" }}>
          Public demo limits are enabled to protect provider quota.
        </div>
        </div>
      </div>
    </div>
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
              Live view of prompt traffic, blocked attempts, provider spend signals, and suspicious inputs.
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
          <div style={{ marginBottom: 6 }}>Key created. Copy it now, it will not be shown again:</div>
          <code style={{ fontSize: 12, wordBreak: "break-all", color: "#067647", fontWeight: 800 }}>{rawKey}</code>
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
                <td style={{ ...s.td, fontFamily: "monospace", color: "#0f766e", fontWeight: 800 }}>{k.key_prefix}...</td>
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
                <td style={{ ...s.td, fontFamily: "monospace", color: "#0f766e", fontWeight: 800 }}>{k.key_prefix}...</td>
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
      <div style={s.heroPanel}>
        <div style={{ ...s.pageTitle, marginBottom: 8 }}>Guardrail Playground</div>
        <div style={{ color: "#405166", fontSize: 15, lineHeight: 1.6 }}>
          Send a prompt through client checks, backend policy rules, Groq, and output validation.
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
          style={{ ...s.input, marginBottom: 10 }}
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
                  <div style={{ fontSize: 14, color: "#27394f", lineHeight: 1.7,
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

// ROOT APP
const NAV = [
  { id: "dashboard", label: "Dashboard",   icon: "01" },
  { id: "chat",      label: "Playground",  icon: "02" },
  { id: "logs",      label: "Logs",        icon: "03" },
  { id: "keys",      label: "API Keys",    icon: "04" },
  { id: "policy",    label: "Policy",      icon: "05" },
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

  if (!user) return <><GlobalStyles /><AuthView onAuth={setUser} /></>;

  return (
    <div className="app-shell" style={s.app}>
      <GlobalStyles />
      {/* Sidebar */}
      <div className="app-sidebar" style={s.sidebar}>
        <div style={s.logo}>
          <div style={s.logoText}>LLM Guardrail</div>
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
        {view === "logs"      && <LogsView />}
        {view === "keys"      && <ApiKeysView />}
        {view === "policy"    && <PolicyView user={user} />}
        {view === "admin"     && user.is_admin && <AdminView />}
      </div>
    </div>
  );
}


