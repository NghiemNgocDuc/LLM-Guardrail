import React, { useState, useEffect, useCallback, useMemo } from "react";
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

// -- Smooth bezier helpers --------------------------------------------------
function smoothPath(points: number[][], tension = 0.35): string {
  if (points.length < 2) return "";
  if (points.length === 2) return `M ${points[0].join(",")} L ${points[1].join(",")}`;
  let d = `M ${points[0].join(",")}`;
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[i - 1] || points[0];
    const p1 = points[i];
    const p2 = points[i + 1];
    const p3 = points[i + 2] || p2;
    const cp1x = p1[0] + (p2[0] - p0[0]) * tension / 6;
    const cp1y = p1[1] + (p2[1] - p0[1]) * tension / 6;
    const cp2x = p2[0] - (p3[0] - p1[0]) * tension / 6;
    const cp2y = p2[1] - (p3[1] - p1[1]) * tension / 6;
    d += ` C ${cp1x},${cp1y} ${cp2x},${cp2y} ${p2.join(",")}`;
  }
  return d;
}
function smoothAreaPath(points: number[][], H: number, PAD: number): string {
  if (points.length === 0) return "";
  const line = smoothPath(points);
  const last = points[points.length - 1];
  const first = points[0];
  return `${line} L ${last[0]},${H - PAD} L ${first[0]},${H - PAD} Z`;
}

function MiniChart({ series }: { series: TimeSeriesPoint[] }) {
  const [hover, setHover] = useState<number | null>(null);
  if (!series || series.length === 0) return null;
  const W = 780, H = 200, PAD_L = 40, PAD_R = 12, PAD_T = 14, PAD_B = 26;
  const plotW = W - PAD_L - PAD_R;
  const plotH = H - PAD_T - PAD_B;
  const maxTotal = Math.max(...series.map(p => Math.max(p.total, p.blocked)), 1);
  const xStep = plotW / Math.max(series.length - 1, 1);
  const pts = series.map((p, i) => {
    const x = PAD_L + i * xStep;
    const y = PAD_T + plotH - (p.total / maxTotal) * plotH;
    return [Math.round(x * 10) / 10, Math.round(y * 10) / 10] as [number, number];
  });
  const blocked = series.map((p, i) => {
    const x = PAD_L + i * xStep;
    const y = PAD_T + plotH - (p.blocked / maxTotal) * plotH;
    return [Math.round(x * 10) / 10, Math.round(y * 10) / 10] as [number, number];
  });
  const yTicks = [0, 0.5, 1].map(f => PAD_T + plotH - f * plotH);
  return (
    <div style={{ position: "relative" }}>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        style={{ width: "100%", height: H, display: "block", overflow: "visible" }}
        onMouseLeave={() => setHover(null)}
      >
        <defs>
          <linearGradient id="gTotal" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#0ea5e9" stopOpacity={0.28} />
            <stop offset="65%" stopColor="#0ea5e9" stopOpacity={0.06} />
            <stop offset="100%" stopColor="#0ea5e9" stopOpacity={0} />
          </linearGradient>
          <linearGradient id="gBlocked" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#f43f5e" stopOpacity={0.26} />
            <stop offset="70%" stopColor="#f43f5e" stopOpacity={0.05} />
            <stop offset="100%" stopColor="#f43f5e" stopOpacity={0} />
          </linearGradient>
          <linearGradient id="gStrokeTotal" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#0284c7" />
            <stop offset="100%" stopColor="#0ea5e9" />
          </linearGradient>
          <filter id="softShadow" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="6" stdDeviation="8" floodColor="#0ea5e9" floodOpacity="0.14" />
          </filter>
          <filter id="softShadowRed" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="4" stdDeviation="6" floodColor="#f43f5e" floodOpacity="0.16" />
          </filter>
        </defs>

        {/* grid */}
        {yTicks.map((y, i) => (
          <g key={i}>
            <line x1={PAD_L} x2={W - PAD_R} y1={y} y2={y} stroke="#e7eef6" strokeWidth={1} strokeDasharray={i === 0 ? undefined : "6 8"} opacity={i === 0 ? 1 : 0.9} />
            <text x={PAD_L - 8} y={y + 3} textAnchor="end" fontSize={10} fill="#8a9bb0" fontWeight={600}>
              {Math.round(maxTotal * (1 - (y - PAD_T) / plotH)).toLocaleString()}
            </text>
          </g>
        ))}
        {[0, 0.25, 0.5, 0.75].map(f => {
          const x = PAD_L + f * plotW;
          return <line key={f} x1={x} x2={x} y1={PAD_T} y2={PAD_T + plotH} stroke="#f1f5f9" strokeWidth={1} opacity={0.9} />;
        })}

        {/* areas */}
        <path d={smoothAreaPath(pts, H, PAD_B)} fill="url(#gTotal)" filter="url(#softShadow)" />
        <path d={smoothAreaPath(blocked, H, PAD_B)} fill="url(#gBlocked)" filter="url(#softShadowRed)" />

        {/* strokes — smooth cubic */}
        <path d={smoothPath(pts)} fill="none" stroke="url(#gStrokeTotal)" strokeWidth={2.6} strokeLinecap="round" strokeLinejoin="round" />
        <path d={smoothPath(blocked)} fill="none" stroke="#f43f5e" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round" opacity={0.96} />

        {/* points */}
        {pts.map(([x, y], i) => (
          <g key={`t-${i}`} onMouseEnter={() => setHover(i)} style={{ cursor: "pointer" }}>
            <circle cx={x} cy={y} r={hover === i ? 6 : 3.2} fill="#fff" stroke="#0ea5e9" strokeWidth={hover === i ? 2.4 : 1.8} style={{ transition: "all 0.16s" }} />
            <rect x={x - xStep / 2} y={PAD_T} width={xStep} height={plotH} fill="transparent" />
          </g>
        ))}
        {blocked.map(([x, y], i) => (
          <circle key={`b-${i}`} cx={x} cy={y} r={hover === i ? 5 : 2.6} fill="#fff" stroke="#f43f5e" strokeWidth={1.7} opacity={0.95} style={{ pointerEvents: "none" }} />
        ))}

        {/* x labels */}
        {series.map((p, i) => {
          if (series.length > 14 && i % Math.ceil(series.length / 7) !== 0 && i !== series.length - 1) return null;
          const x = PAD_L + i * xStep;
          const label = (p as unknown as { ts?: string; date?: string }).ts || (p as unknown as { date?: string }).date || "";
          const short = label ? new Date(label).toLocaleDateString(undefined, { month: "short", day: "numeric" }) : `D${i + 1}`;
          return <text key={i} x={x} y={H - 6} textAnchor="middle" fontSize={10} fill="#7b8a9d" fontWeight={600}>{short}</text>;
        })}

        {/* hover guide */}
        {hover !== null && (
          <line x1={PAD_L + hover * xStep} x2={PAD_L + hover * xStep} y1={PAD_T} y2={PAD_T + plotH} stroke="#0f766e" strokeWidth={1} strokeDasharray="4 6" opacity={0.35} />
        )}
      </svg>

      {hover !== null && series[hover] && (
        <div
          style={{
            position: "absolute",
            left: `calc(${(hover / Math.max(series.length - 1, 1)) * 100}% - 72px)`,
            top: 8,
            background: "rgba(16,32,51,0.92)",
            color: "#fff",
            borderRadius: 10,
            padding: "10px 12px",
            fontSize: 12,
            lineHeight: 1.45,
            pointerEvents: "none",
            boxShadow: "0 12px 32px rgba(0,0,0,0.18)",
            backdropFilter: "blur(10px)",
            minWidth: 144,
            transform: hover > series.length - 3 ? "translateX(-28px)" : hover < 2 ? "translateX(28px)" : undefined,
          }}
        >
          <div style={{ fontWeight: 800, marginBottom: 4, color: "#7dd3fc" }}>{new Date((series[hover] as unknown as { ts?: string }).ts || Date.now()).toLocaleDateString()}</div>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}><span style={{ opacity: 0.7 }}>Total</span><span style={{ fontWeight: 800 }}>{series[hover].total.toLocaleString()}</span></div>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}><span style={{ opacity: 0.7 }}>Blocked</span><span style={{ fontWeight: 800, color: "#fda4af" }}>{series[hover].blocked.toLocaleString()}</span></div>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}><span style={{ opacity: 0.7 }}>Delivered</span><span style={{ fontWeight: 700 }}>{(series[hover].total - series[hover].blocked).toLocaleString()}</span></div>
        </div>
      )}

      <div style={{ display: "flex", gap: 14, marginTop: 10, justifyContent: "center", flexWrap: "wrap", fontSize: 11, fontWeight: 700, color: "#607086" }}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><span style={{ width: 10, height: 10, borderRadius: 999, background: "#0ea5e9", display: "inline-block" }} />Total</span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><span style={{ width: 10, height: 10, borderRadius: 999, background: "#f43f5e", display: "inline-block" }} />Blocked</span>
        <span style={{ color: "#8a9bb0", fontWeight: 600 }}>{series.length} days · max {maxTotal.toLocaleString()}</span>
      </div>
    </div>
  );
}

function StatCard({ label, value, sub, color, icon }: {
  label: string; value: string | number; sub?: string; color?: string; icon?: string;
}) {
  return (
    <div style={{ ...s.card, flex: "1 1 168px", minWidth: 168, padding: 0, overflow: "hidden", position: "relative" }}>
      <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: 3, background: color ? `linear-gradient(90deg, ${color}, ${color}88)` : "linear-gradient(90deg, #0f766e, #14b8a6)" , opacity: 0.95 }} />
      <div style={{ padding: "18px 18px 16px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 10, marginBottom: 10 }}>
          <div style={{ fontSize: 11, fontWeight: 800, color: color || "#607086", textTransform: "uppercase", letterSpacing: "0.07em", lineHeight: 1.2 }}>{label}</div>
          {icon && <span style={{ width: 28, height: 28, borderRadius: 8, display: "grid", placeItems: "center", background: `${color || "#0f766e"}12`, border: `1px solid ${color || "#0f766e"}18`, fontSize: 13 }}>{icon}</span>}
        </div>
        <div style={{ fontSize: 28, fontWeight: 900, color: "#102033", lineHeight: 1, letterSpacing: "-0.02em" }}>{value}</div>
        {sub && <div style={{ fontSize: 12, color: "#8a9bb0", marginTop: 6, fontWeight: 600 }}>{sub}</div>}
      </div>
    </div>
  );
}

export default function AnalyticsView() {
  const [days, setDays] = useState(30);
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

  const sortedUsers = useMemo(() => [...users].sort((a, b) => {
    const v = (x: UserUsageStat) => Number(x[sortCol] ?? 0);
    return sortDir === "asc" ? v(a) - v(b) : v(b) - v(a);
  }), [users, sortCol, sortDir]);

  const fmt = (n: number | null | undefined) => Number(n ?? 0).toLocaleString();
  const SortArrow = ({ col }: { col: keyof UserUsageStat }) => sortCol === col ? (sortDir === "asc" ? " " : " ") : "";

  function exportCsv() {
    const token = localStorage.getItem("guardrails_access_token");
    window.location.href = `/analytics/export?days=${days}&token=${token}`;
  }

  const kpis = useMemo(() => {
    if (!dash) return [];
    const blocked = dash.summary.input_blocked + dash.summary.output_blocked;
    const total = dash.summary.total_requests || 1;
    return [
      { label: "Total Requests", value: fmt(dash.summary.total_requests), sub: `${days}d window`, color: "#0f766e", icon: "" },
      { label: "Delivered", value: fmt(dash.summary.delivered), sub: `${((dash.summary.delivered / total) * 100).toFixed(1)}% pass`, color: "#059669", icon: "" },
      { label: "Blocked", value: fmt(blocked), sub: `${dash.summary.block_rate_pct}% of traffic`, color: "#dc2626", icon: "" },
      { label: "Block Rate", value: `${dash.summary.block_rate_pct}%`, sub: blocked > 0 ? "active" : "quiet", color: "#d97706", icon: "%" },
      { label: "Avg Latency", value: `${dash.summary.avg_latency_ms}ms`, sub: "p95 ", color: "#2563eb", icon: "" },
      { label: "Est. Cost", value: `$${(dash.summary.estimated_cost_usd || 0).toFixed(4)}`, sub: "USD", color: "#7c3aed", icon: "$" },
      { label: "Total Tokens", value: fmt(dash.summary.total_tokens), sub: "in + out", color: "#0e7490", icon: "" },
    ];
  }, [dash, days]);

  return (
    <div>
      <div style={{
        ...s.heroPanel,
        display: "flex", justifyContent: "space-between", gap: 16, alignItems: "flex-start", flexWrap: "wrap",
      }}>
        <div style={{ minWidth: 260 }}>
          <div style={{ ...s.pageTitle, marginBottom: 8 }}>Analytics</div>
          <div style={{ color: "#405166", fontSize: 15, lineHeight: 1.6, maxWidth: 560 }}>
            Request volume, guardrail activity, cost and per-user usage — one smooth timeline.
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 14, flexWrap: "wrap", alignItems: "center" }}>
            <span style={{ fontSize: 11, fontWeight: 800, color: "#0f766e", letterSpacing: "0.06em", textTransform: "uppercase" }}>Window</span>
            {[7, 14, 30, 60, 90].map(d => (
              <button key={d} onClick={() => setDays(d)} style={{
                padding: "7px 13px", borderRadius: 999, fontSize: 12, fontWeight: 800, cursor: "pointer",
                border: days === d ? "1px solid #0f766e" : "1px solid #dce7f0",
                background: days === d ? "#0f766e" : "#fff", color: days === d ? "#fff" : "#405166",
                boxShadow: days === d ? "0 6px 16px rgba(15,118,110,0.22)" : "none",
                transition: "all 0.18s",
              }}> {d}d </button>
            ))}
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, alignSelf: "flex-start" }}>
          <button style={{ ...s.btn("secondary"), borderRadius: 10 }} onClick={load}> Refresh</button>
          <button style={{ ...s.btn("primary"), borderRadius: 10 }} onClick={exportCsv}> Export CSV</button>
        </div>
      </div>

      {error && <div style={s.alert("error")}>{error}</div>}

      {loading ? (
        <div style={{ display: "grid", placeItems: "center", padding: 40, color: "#8a9bb0", gap: 10 }}>
          <div style={{ width: 28, height: 28, borderRadius: "50%", border: "3px solid #e7eef6", borderTopColor: "#0f766e", animation: "spin 0.85s linear infinite" } as React.CSSProperties} />
          <span style={{ fontSize: 13, fontWeight: 700 }}>Loading analytics…</span>
        </div>
      ) : dash ? (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(168px,1fr))", gap: 14, marginBottom: 20 }}>
            {kpis.map(k => <StatCard key={k.label} {...k} />)}
          </div>

          <div style={{ ...s.card, marginBottom: 20, padding: 0, overflow: "hidden" }}>
            <div style={{ padding: "18px 22px 0", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
              <div style={s.sectionTitle}>Daily Volume</div>
              <div style={{ fontSize: 11, fontWeight: 700, color: "#8a9bb0", letterSpacing: "0.04em", textTransform: "uppercase" }}>
                {dash.time_series.length} points · {days}d
              </div>
            </div>
            <div style={{ padding: "6px 14px 14px" }}>
              <MiniChart series={dash.time_series} />
              {dash.time_series.length === 0 && (
                <div style={{ color: "#8a9bb0", fontSize: 13, textAlign: "center", padding: 28, background: "#f8fbff", borderRadius: 12, border: "1px dashed #dce7f0" }}>No data for this period — try a larger window.</div>
              )}
            </div>
          </div>

          {dash.top_rules.length > 0 && (
            <div style={{ ...s.card, marginBottom: 20, padding: 0, overflow: "hidden" }}>
              <div style={{ padding: "18px 22px 14px", borderBottom: "1px solid #eef3f8", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div style={s.sectionTitle}>Top Fired Rules</div>
                <span style={{ fontSize: 11, color: "#8a9bb0", fontWeight: 700 }}>{dash.top_rules.length} rules</span>
              </div>
              <div style={{ padding: 10 }}>
                {dash.top_rules.map(r => {
                  const pct = dash.summary.total_requests > 0 ? (r.count / dash.summary.total_requests) * 100 : 0;
                  return (
                    <div key={r.rule} style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 12px", borderRadius: 10, transition: "background 0.15s" }} onMouseEnter={e => (e.currentTarget.style.background = "#f8fbff")} onMouseLeave={e => (e.currentTarget.style.background = "transparent")}>
                      <span style={{ ...s.badge("input_blocked"), minWidth: 0, flexShrink: 0 }}>{r.rule}</span>
                      <div style={{ flex: 1, minWidth: 120, height: 8, background: "#eef3f8", borderRadius: 999, overflow: "hidden", position: "relative" }}>
                        <div style={{ height: "100%", width: `${Math.max(6, pct * 6)}%`, background: "linear-gradient(90deg,#0f766e,#14b8a6)", borderRadius: 999, transition: "width 0.6s cubic-bezier(0.22,1,0.36,1)" }} />
                      </div>
                      <span style={{ fontSize: 13, fontWeight: 850, color: "#102033", minWidth: 36, textAlign: "right" }}>{fmt(r.count)}</span>
                      <span style={{ fontSize: 12, fontWeight: 750, color: "#0f766e", background: "#ecfdf5", border: "1px solid #a7f3d0", padding: "2px 7px", borderRadius: 999, minWidth: 48, textAlign: "center" }}>{pct.toFixed(1)}%</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </>
      ) : null}

      <div style={{ ...s.card, overflow: "hidden", padding: 0 }}>
        <div style={{ padding: "18px 22px 0", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
          <div style={s.sectionTitle}>Per-User Breakdown</div>
          <span style={{ fontSize: 11, fontWeight: 700, color: "#8a9bb0", letterSpacing: "0.04em", textTransform: "uppercase" }}>{sortedUsers.length} users</span>
        </div>
        <div style={{ overflowX: "auto", marginTop: 14 }}>
          <table style={{ ...s.table, minWidth: 640 }}>
            <thead style={{ position: "sticky", top: 0, background: "#f8fbff", zIndex: 1 }}>
              <tr>
                {([
                  ["email", "User"],
                  ["requests", "Requests"],
                  ["blocked", "Blocked"],
                  ["tokens_used_lifetime", "Tokens Used"],
                  ["tokens_balance", "Balance"],
                ] as [keyof UserUsageStat, string][]).map(([col, label]) => (
                  <th key={col} style={{ ...s.th, cursor: "pointer", userSelect: "none", whiteSpace: "nowrap" }}
                    onClick={() => toggleSort(col)}>
                    {label}<SortArrow col={col} />
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sortedUsers.map(u => {
                const blockPct = (u.requests || 1) > 0 ? (u.blocked / Math.max(u.requests, 1)) * 100 : 0;
                return (
                  <tr key={u.id} style={{ transition: "background 0.12s" }} onMouseEnter={e => (e.currentTarget.style.background = "#f8fbff")} onMouseLeave={e => (e.currentTarget.style.background = "transparent")}>
                    <td style={s.td}>
                      <div style={{ fontWeight: 750, color: "#102033" }}>{u.email}</div>
                      {u.full_name && <div style={{ fontSize: 11, color: "#8a9bb0", fontWeight: 600 }}>{u.full_name}</div>}
                    </td>
                    <td style={s.td}><span style={{ fontWeight: 750 }}>{fmt(u.requests)}</span></td>
                    <td style={s.td}>
                      <span style={{ fontWeight: 750 }}>{fmt(u.blocked)}</span>
                      <span style={{ marginLeft: 6, fontSize: 11, fontWeight: 700, color: blockPct > 15 ? "#dc2626" : "#7b8a9d", background: blockPct > 15 ? "#fef2f2" : "#f1f5f9", padding: "1px 6px", borderRadius: 999 }}>{blockPct.toFixed(0)}%</span>
                    </td>
                    <td style={s.td}>{fmt(u.tokens_used_lifetime)}</td>
                    <td style={{ ...s.td, fontWeight: 750, color: (u.tokens_balance || 0) < 500 ? "#b45309" : "#405166" }}>{fmt(u.tokens_balance)}</td>
                  </tr>
                );
              })}
              {sortedUsers.length === 0 && !loading && (
                <tr><td colSpan={5} style={{ ...s.td, textAlign: "center", color: "#8a9bb0", padding: 28 }}>No data — invite teammates or send a test prompt in Playground.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
