import React, { useState, useEffect } from "react";
import { api } from "../utils/api";
import { s } from "../styles/theme";
import type { components, RecentLogItem, SuspiciousLogItem } from "../api-types";
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis,
  Tooltip, ResponsiveContainer, CartesianGrid,
  PieChart, Pie, Cell, Legend
} from "recharts";

type AnalyticsDashboard = components["schemas"]["AnalyticsDashboard"];
type UsageSummary = components["schemas"]["UsageSummary"];
type TimeSeriesPoint = components["schemas"]["TimeSeriesPoint"];
type TopFiredRule = components["schemas"]["TopFiredRule"];
type ProviderUsage = components["schemas"]["ProviderUsage"];

interface DashboardData {
  summary: UsageSummary;
  time_series: TimeSeriesPoint[];
  top_rules: TopFiredRule[];
  provider_usage: ProviderUsage[];
  recent_suspicious: SuspiciousLogItem[];
  recent_logs: RecentLogItem[];
}

export default function DashboardView() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<DashboardData>("/analytics/dashboard?days=7")
      .then(setData)
      .catch((e: Error) => setError(e.message));
  }, []);

  if (error) return <div style={s.alert("error")}>{error}</div>;
  if (!data) return <div style={s.muted}>Loading dashboard...</div>;

  const { summary, time_series, top_rules, provider_usage = [], recent_suspicious = [], recent_logs } = data;
  const maxRule = Math.max(...(top_rules.map(r => r.count)), 1);
  const blockedTotal = summary.input_blocked + summary.output_blocked + (summary.rate_limited || 0);

  const statCards = [
    { label: "Total Requests", value: summary.total_requests.toLocaleString(), sub: "last 7 days" },
    { label: "Blocked Requests", value: blockedTotal.toLocaleString(), sub: summary.block_rate_pct + "% of traffic" },
    { label: "Rate-Limit Hits", value: (summary.rate_limited || 0).toLocaleString(), sub: "quota protected" },
    { label: "Avg Latency", value: summary.avg_latency_ms + "ms", sub: "end-to-end" },
    { label: "Total Tokens", value: summary.total_tokens.toLocaleString(), sub: "in + out" },
  ];

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
        {statCards.map(c => (
          <div key={c.label} style={s.statCard}>
            <div style={s.statLabel}>{c.label}</div>
            <div style={s.statValue}>{c.value}</div>
            <div style={s.statSub}>{c.sub}</div>
          </div>
        ))}
      </div>

      <div style={s.grid2}>
        {/* Area chart — ultra-smooth */}
        <div style={{ ...s.card, padding: 0, overflow: "hidden" }}>
          <div style={{ padding: "18px 22px 6px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div style={s.sectionTitle}>Delivered vs Blocked</div>
            <span style={{ fontSize: 11, fontWeight: 700, color: "#8a9bb0", letterSpacing: "0.04em", textTransform: "uppercase" }}>7 days · smooth</span>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={time_series} margin={{ top: 8, right: 16, left: -10, bottom: 0 }}>
              <defs>
                <linearGradient id="colorDelivered2" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#0f766e" stopOpacity={0.32}/>
                  <stop offset="55%" stopColor="#14b8a6" stopOpacity={0.12}/>
                  <stop offset="100%" stopColor="#14b8a6" stopOpacity={0}/>
                </linearGradient>
                <linearGradient id="colorBlocked2" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#f97316" stopOpacity={0.30}/>
                  <stop offset="60%" stopColor="#fb7185" stopOpacity={0.10}/>
                  <stop offset="100%" stopColor="#fb7185" stopOpacity={0}/>
                </linearGradient>
                <filter id="shadowDelivered" x="-20%" y="-20%" width="140%" height="140%">
                  <feDropShadow dx="0" dy="8" stdDeviation="10" floodColor="#0f766e" floodOpacity="0.14" />
                </filter>
                <filter id="shadowBlocked" x="-20%" y="-20%" width="140%" height="140%">
                  <feDropShadow dx="0" dy="6" stdDeviation="8" floodColor="#f97316" floodOpacity="0.14" />
                </filter>
              </defs>
              <CartesianGrid strokeDasharray="6 8" stroke="#eef3f8" vertical={false} />
              <XAxis dataKey="ts" tick={{ fontSize: 11, fill: "#7b8a9d", fontWeight: 600 }} axisLine={false} tickLine={false} dy={6}
                tickFormatter={(v: string) => { try { return new Date(v).toLocaleDateString(undefined, { month: "short", day: "numeric" }); } catch { return v; } }} />
              <YAxis tick={{ fontSize: 11, fill: "#7b8a9d", fontWeight: 600 }} axisLine={false} tickLine={false} dx={-6} />
              <Tooltip
                contentStyle={{ background: "rgba(16,32,51,0.92)", border: "none", borderRadius: 12, fontSize: 12, color: "#fff", backdropFilter: "blur(12px)", boxShadow: "0 16px 40px rgba(0,0,0,0.18)" }}
                labelStyle={{ color: "#7dd3fc", fontWeight: 700, marginBottom: 4 }}
                cursor={{ stroke: "#0f766e", strokeDasharray: "4 6", strokeOpacity: 0.35 }}
              />
              <Area type="monotone" dataKey="delivered" stroke="#0f766e" strokeWidth={2.8} strokeLinecap="round" strokeLinejoin="round" fillOpacity={1} fill="url(#colorDelivered2)" filter="url(#shadowDelivered)" dot={false} activeDot={{ r: 5, fill: "#fff", stroke: "#0f766e", strokeWidth: 2.2 }} animationDuration={900} />
              <Area type="monotone" dataKey="blocked"   stroke="#f43f5e" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round" fillOpacity={1} fill="url(#colorBlocked2)" filter="url(#shadowBlocked)" dot={false} activeDot={{ r: 4.5, fill: "#fff", stroke: "#f43f5e", strokeWidth: 2 }} animationDuration={900} />
            </AreaChart>
          </ResponsiveContainer>
          <div style={{ display: "flex", gap: 14, justifyContent: "center", padding: "8px 0 14px", fontSize: 11, fontWeight: 700, color: "#607086" }}>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><span style={{ width: 10, height: 10, borderRadius: 999, background: "#0f766e" }} />Delivered</span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><span style={{ width: 10, height: 10, borderRadius: 999, background: "#f43f5e" }} />Blocked</span>
          </div>
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
        <div style={{ ...s.card, padding: 0, overflow: "hidden" }}>
          <div style={{ padding: "18px 22px 4px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div style={s.sectionTitle}>Requests by Provider</div>
            <span style={{ fontSize: 10, fontWeight: 800, color: "#8a9bb0", letterSpacing: "0.06em", textTransform: "uppercase" }}> Donut · smooth </span>
          </div>
          <ResponsiveContainer width="100%" height={250}>
            <PieChart>
              <defs>
                <filter id="pieShadow" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="8" stdDeviation="10" floodOpacity="0.12" /></filter>
              </defs>
              <Pie data={provider_usage} dataKey="count" nameKey="backend" cx="50%" cy="50%" innerRadius={68} outerRadius={92} paddingAngle={4} cornerRadius={8} stroke="#fff" strokeWidth={2} filter="url(#pieShadow)" animationDuration={900}>
                {provider_usage.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={["#0f766e", "#3b82f6", "#14b8a6", "#8b5cf6", "#f59e0b"][index % 5]} />
                ))}
              </Pie>
              <Tooltip contentStyle={{ background: "rgba(16,32,51,0.92)", border: "none", borderRadius: 10, fontSize: 12, color: "#fff", backdropFilter: "blur(10px)", boxShadow: "0 16px 32px rgba(0,0,0,0.18)" }} />
              <Legend wrapperStyle={{ fontSize: 11, color: "#7b8a9d", paddingTop: 10 }} iconType="circle" />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div style={{ ...s.card, padding: 0, overflow: "hidden" }}>
          <div style={{ padding: "18px 22px 4px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div style={s.sectionTitle}>Tokens by Model</div>
            <span style={{ fontSize: 10, fontWeight: 800, color: "#8a9bb0", letterSpacing: "0.06em", textTransform: "uppercase" }}> Rounded · gradient </span>
          </div>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={provider_usage} margin={{ top: 8, right: 16, left: -10, bottom: 0 }} maxBarSize={44} barCategoryGap="22%">
              <defs>
                <linearGradient id="barGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#14b8a6" stopOpacity={0.98} />
                  <stop offset="100%" stopColor="#0f766e" stopOpacity={0.98} />
                </linearGradient>
                <filter id="barShadow2" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="6" stdDeviation="8" floodColor="#0f766e" floodOpacity="0.14" /></filter>
              </defs>
              <CartesianGrid strokeDasharray="6 8" stroke="#eef3f8" vertical={false} />
              <XAxis dataKey="model" tick={{ fontSize: 11, fill: "#7b8a9d", fontWeight: 600 }} tickLine={false} axisLine={false} dy={6} />
              <YAxis tick={{ fontSize: 11, fill: "#7b8a9d", fontWeight: 600 }} tickLine={false} axisLine={false} dx={-6} />
              <Tooltip contentStyle={{ background: "rgba(16,32,51,0.92)", border: "none", borderRadius: 10, fontSize: 12, color: "#fff", backdropFilter: "blur(10px)" }} cursor={{ fill: "rgba(15,118,110,0.06)", radius: 8 } as unknown as Record<string, unknown>} />
              <Bar dataKey="tokens" fill="url(#barGrad)" radius={[10, 10, 0, 0]} filter="url(#barShadow2)" animationDuration={900} />
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

