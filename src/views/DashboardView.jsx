import React, { useState, useEffect, useCallback, useRef } from "react";
import { api, getToken, setTokens, clearTokens, getGatewayKey, setGatewayKey, maskGatewayKey, gatewayKeyInputProps, formatApiError } from "../utils/api";
import { s } from "../styles/theme";
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis,
  Tooltip, ResponsiveContainer, CartesianGrid,
  PieChart, Pie, Cell, Legend
} from "recharts";
export default function DashboardView() {
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
              Live view of model traffic, skill scans, and policy — gateway plus agent-context protection in one console.
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
              <defs>
                <linearGradient id="colorDelivered" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#0f766e" stopOpacity={0.3}/>
                  <stop offset="95%" stopColor="#0f766e" stopOpacity={0}/>
                </linearGradient>
                <linearGradient id="colorBlocked" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#f97316" stopOpacity={0.3}/>
                  <stop offset="95%" stopColor="#f97316" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#e7eef6" />
              <XAxis dataKey="ts" tick={{ fontSize: 11, fill: "#7b8a9d" }} />
              <YAxis tick={{ fontSize: 11, fill: "#7b8a9d" }} />
              <Tooltip contentStyle={{ background: "rgba(255, 255, 255, 0.9)", border: "1px solid #dce7f0",
                borderRadius: 8, fontSize: 12, backdropFilter: "blur(10px)", boxShadow: "0 12px 28px rgba(15,118,110,0.1)" }} />
              <Area type="monotone" dataKey="delivered" stroke="#0f766e" fillOpacity={1} fill="url(#colorDelivered)" strokeWidth={2} />
              <Area type="monotone" dataKey="blocked"   stroke="#f97316" fillOpacity={1} fill="url(#colorBlocked)" strokeWidth={2} />
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
          <div style={s.sectionTitle}>Requests by Provider</div>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie data={provider_usage} dataKey="count" nameKey="backend" cx="50%" cy="50%" innerRadius={60} outerRadius={80} paddingAngle={5}>
                {provider_usage.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={["#0f766e", "#3b82f6", "#10b981", "#8b5cf6"][index % 4]} />
                ))}
              </Pie>
              <Tooltip contentStyle={{ background: "rgba(255, 255, 255, 0.9)", border: "1px solid #dce7f0", borderRadius: 8, fontSize: 12, backdropFilter: "blur(10px)" }} />
              <Legend wrapperStyle={{ fontSize: 11, color: "#7b8a9d" }} />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div style={s.card}>
          <div style={s.sectionTitle}>Tokens by Model</div>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={provider_usage} margin={{ top: 0, right: 0, left: -20, bottom: 0 }} maxBarSize={40}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e7eef6" vertical={false} />
              <XAxis dataKey="model" tick={{ fontSize: 11, fill: "#7b8a9d" }} tickLine={false} axisLine={false} />
              <YAxis tick={{ fontSize: 11, fill: "#7b8a9d" }} tickLine={false} axisLine={false} />
              <Tooltip contentStyle={{ background: "rgba(255, 255, 255, 0.9)", border: "1px solid #dce7f0", borderRadius: 8, fontSize: 12, backdropFilter: "blur(10px)" }} cursor={{ fill: "rgba(15,118,110,0.05)" }} />
              <Bar dataKey="tokens" fill="#14b8a6" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div style={s.grid2}>

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

// DEFAULT SCOPES available to add to a key
const DEFAULT_SCOPE_OPTIONS = [
  { label: "chat",          color: "#6366f1", bg: "#eef2ff",  border: "#c7d2fe" },
  { label: "policy:read",   color: "#0f766e", bg: "#ccfbf1",  border: "#99f6e4" },
  { label: "policy:write",  color: "#0f766e", bg: "#ccfbf1",  border: "#99f6e4" },
  { label: "logs:read",     color: "#1d4ed8", bg: "#dbeafe",  border: "#bfdbfe" },
  { label: "analytics",     color: "#7c3aed", bg: "#f5f3ff",  border: "#ddd6fe" },
  { label: "skills:read",   color: "#b45309", bg: "#fef9c3",  border: "#fde68a" },
  { label: "skills:write",  color: "#b45309", bg: "#fef9c3",  border: "#fde68a" },
  { label: "admin",         color: "#be123c", bg: "#fff1f2",  border: "#fecdd3" },
];

