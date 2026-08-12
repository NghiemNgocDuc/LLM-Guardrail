import React, { useState, useEffect, useCallback } from "react";
import { api } from "../utils/api";
import { s } from "../styles/theme";
import type { components, UserUsageStat } from "../api-types";

type UsageSummary = components["schemas"]["UsageSummary"];
type TimeSeriesPoint = components["schemas"]["TimeSeriesPoint"];
type TopFiredRule = components["schemas"]["TopFiredRule"];

interface DashboardData {
  summary: UsageSummary;
  time_series: TimeSeriesPoint[];
  top_rules: TopFiredRule[];
}

function MiniChart({ series }: { series: TimeSeriesPoint[] }) {
  if (!series || series.length === 0) return null;
  const W = 600, H = 120, PAD = 8;
  const maxTotal = Math.max(...series.map(p => p.total), 1);
  const pts = series.map((p, i) => {
    const x = PAD + (i / Math.max(series.length - 1, 1)) * (W - PAD * 2);
    const y = H - PAD - (p.total / maxTotal) * (H - PAD * 2);
    return [x, y];
  });
  const blocked = series.map((p, i) => {
    const x = PAD + (i / Math.max(series.length - 1, 1)) * (W - PAD * 2);
    const y = H - PAD - (p.blocked / maxTotal) * (H - PAD * 2);
    return [x, y];
  });

  const poly = (arr: number[][]) => arr.map(p => p.join(",")).join(" ");
  const fill = (arr: number[][]) => {
    const first = arr[0];
    const last = arr[arr.length - 1];
    return `${poly(arr)} ${last[0]},${H - PAD} ${first[0]},${H - PAD}`;
  };

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: H, display: "block" }}>
      <polyline points={fill(pts)} fill="#e0f2fe" stroke="none" />
      <polyline points={poly(pts)} fill="none" stroke="#0ea5e9" strokeWidth={2} />
      <polyline points={fill(blocked)} fill="#fee2e2" stroke="none" />
      <polyline points={poly(blocked)} fill="none" stroke="#f87171" strokeWidth={1.5} />
    </svg>
  );
}

function StatCard({ label, value, sub, color }: {
  label: string; value: string | number; sub?: string; color?: string;
}) {
  return (
    <div style={{ ...s.card, flex: 1, minWidth: 140, padding: "18px 20px" }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: color || "#607086", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: 900, color: "#102033", lineHeight: 1 }}>{value}</div>
      {sub && <div style={{ fontSize: 12, color: "#8a9bb0", marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

export default function AnalyticsView() {
  const [days, setDays] = useState(30);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [dash, setDash] = useState<DashboardData | null>(null);
  const [users, setUsers] = useState<UserUsageStat[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [sortCol, setSortCol] = useState<keyof UserUsageStat>("requests");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const load = useCallback(() => {
    setLoading(true); setError("");
    const params = new URLSearchParams({ days: String(days) });
    Promise.all([
      api<DashboardData>("/analytics/dashboard?" + params),
      api<UserUsageStat[]>("/analytics/users?" + params),
    ])
      .then(([d, u]) => { setDash(d); setUsers(u); })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [days]);

  useEffect(() => { load(); }, [load]);

  function toggleSort(col: keyof UserUsageStat) {
    if (sortCol === col) setSortDir(d => d === "asc" ? "desc" : "asc");
    else { setSortCol(col); setSortDir("desc"); }
  }

  const sortedUsers = [...users].sort((a, b) => {
    const v = (x: UserUsageStat) => Number(x[sortCol] ?? 0);
    return sortDir === "asc" ? v(a) - v(b) : v(b) - v(a);
  });

  const fmt = (n: number | null | undefined) => Number(n ?? 0).toLocaleString();
  const SortArrow = ({ col }: { col: keyof UserUsageStat }) => sortCol === col ? (sortDir === "asc" ? " ↑" : " ↓") : "";

  function exportCsv() {
    const token = localStorage.getItem("guardrails_access_token");
    window.location.href = `/analytics/export?days=${days}&token=${token}`;
  }

  return (
    <div>
      <div style={s.heroPanel}>
        <div style={{ ...s.pageTitle, marginBottom: 8 }}>Analytics</div>
        <div style={{ color: "#405166", fontSize: 15, lineHeight: 1.6 }}>
          Request volume, guardrail activity, cost estimates, and per-user breakdown.
        </div>
      </div>

      {error && <div style={s.alert("error")}>{error}</div>}

      {/* Controls */}
      <div style={{ display: "flex", gap: 10, marginBottom: 20, flexWrap: "wrap", alignItems: "center" }}>
        {[7, 14, 30, 60, 90].map(d => (
          <div key={d} style={s.chip(days === d)} onClick={() => setDays(d)}>Last {d}d</div>
        ))}
        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          <button style={s.btn("secondary")} onClick={load}>Refresh</button>
          <button style={s.btn("primary")} onClick={exportCsv}>Export CSV</button>
        </div>
      </div>

      {loading && <div style={{ color: "#8a9bb0", padding: 16 }}>Loading...</div>}

      {dash && (
        <>
          {/* Summary cards */}
          <div style={{ display: "flex", gap: 14, marginBottom: 20, flexWrap: "wrap" }}>
            <StatCard label="Total Requests" value={fmt(dash.summary.total_requests)} />
            <StatCard label="Delivered" value={fmt(dash.summary.delivered)} color="#059669" />
            <StatCard label="Blocked" value={fmt(dash.summary.input_blocked + dash.summary.output_blocked)} color="#dc2626" />
            <StatCard label="Block Rate" value={dash.summary.block_rate_pct + "%"} color="#d97706" />
            <StatCard label="Avg Latency" value={dash.summary.avg_latency_ms + "ms"} />
            <StatCard label="Est. Cost" value={"$" + (dash.summary.estimated_cost_usd || 0).toFixed(4)} sub="USD" />
            <StatCard label="Total Tokens" value={fmt(dash.summary.total_tokens)} />
          </div>

          {/* Time-series chart */}
          <div style={{ ...s.card, marginBottom: 20, padding: "18px 20px" }}>
            <div style={{ ...s.sectionTitle, marginBottom: 12 }}>Daily Volume (blue = total, red = blocked)</div>
            <MiniChart series={dash.time_series} />
            {dash.time_series.length === 0 && (
              <div style={{ color: "#8a9bb0", fontSize: 13, textAlign: "center", padding: 20 }}>No data for this period</div>
            )}
          </div>

          {/* Top rules */}
          {dash.top_rules.length > 0 && (
            <div style={{ ...s.card, marginBottom: 20 }}>
              <div style={s.sectionTitle}>Top Fired Rules</div>
              <table style={s.table}>
                <thead>
                  <tr>
                    <th style={s.th}>Rule</th>
                    <th style={s.th}>Count</th>
                    <th style={s.th}>Share</th>
                  </tr>
                </thead>
                <tbody>
                  {dash.top_rules.map(r => (
                    <tr key={r.rule}>
                      <td style={s.td}><span style={s.badge("input_blocked")}>{r.rule}</span></td>
                      <td style={s.td}>{fmt(r.count)}</td>
                      <td style={s.td}>
                        {dash.summary.total_requests > 0
                          ? ((r.count / dash.summary.total_requests) * 100).toFixed(1) + "%"
                          : "0%"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {/* Per-user breakdown */}
      <div style={{ ...s.card, overflowX: "auto" }}>
        <div style={{ ...s.sectionTitle, marginBottom: 12 }}>Per-User Breakdown</div>
        <table style={s.table}>
          <thead>
            <tr>
              {([
                ["email", "User"],
                ["requests", "Requests"],
                ["blocked", "Blocked"],
                ["tokens_used_lifetime", "Tokens Used"],
                ["tokens_balance", "Balance"],
              ] as [keyof UserUsageStat, string][]).map(([col, label]) => (
                <th key={col} style={{ ...s.th, cursor: "pointer", userSelect: "none" }}
                  onClick={() => toggleSort(col)}>
                  {label}<SortArrow col={col} />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sortedUsers.map(u => (
              <tr key={u.id}>
                <td style={s.td}>
                  <div>{u.email}</div>
                  {u.full_name && <div style={{ fontSize: 11, color: "#8a9bb0" }}>{u.full_name}</div>}
                </td>
                <td style={s.td}>{fmt(u.requests)}</td>
                <td style={s.td}>{fmt(u.blocked)}</td>
                <td style={s.td}>{fmt(u.tokens_used_lifetime)}</td>
                <td style={s.td}>{fmt(u.tokens_balance)}</td>
              </tr>
            ))}
            {sortedUsers.length === 0 && !loading && (
              <tr><td colSpan={5} style={{ ...s.td, textAlign: "center", color: "#8a9bb0" }}>No data</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
