import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, BASE_URL, formatApiError, getAuthToken } from "../utils/api";
import { Badge, Button, EmptyState, LoadingState, Notice, PageHeader, Panel, TableWrap } from "../components/ui";
import type { components, UserUsageStat } from "../api-types";
import "../styles/observability.css";

type DashboardData = components["schemas"]["AnalyticsDashboard"];
type TimeSeriesPoint = components["schemas"]["TimeSeriesPoint"];
const formatNumber = (value: number | null | undefined) => Number(value ?? 0).toLocaleString();
const dateLabel = (value: string) => new Date(`${value.slice(0, 10)}T12:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });

function TrafficChart({ series }: { series: TimeSeriesPoint[] }) {
  if (!series.length) return <EmptyState icon="chart" title="No traffic in this period" description="Choose a longer window or run a request in the Playground." />;
  return <>
    <div className="obs-chart" role="img" aria-label={`Daily request volume for ${series.length} reporting days. A data table is available below.`}>
      <ResponsiveContainer width="100%" height="100%"><LineChart data={series} margin={{ top: 12, right: 20, bottom: 6, left: -12 }} accessibilityLayer>
        <CartesianGrid vertical={false} stroke="var(--gr-border)" strokeDasharray="3 5" />
        <XAxis dataKey="ts" tickFormatter={dateLabel} tick={{ fill: "var(--gr-muted)", fontSize: 11 }} tickLine={false} axisLine={false} minTickGap={34} />
        <YAxis tick={{ fill: "var(--gr-muted)", fontSize: 11 }} tickLine={false} axisLine={false} allowDecimals={false} />
        <Tooltip labelFormatter={(label) => dateLabel(String(label))} formatter={(value) => Number(value).toLocaleString()} contentStyle={{ background: "var(--gr-surface)", border: "1px solid var(--gr-border)", borderRadius: 8, fontSize: 12, color: "var(--gr-ink)" }} />
        <Legend iconType="plainline" wrapperStyle={{ fontSize: 11, paddingTop: 14, color: "var(--gr-muted)" }} />
        <Line type="linear" dataKey="total" name="All requests" stroke="var(--gr-accent)" strokeWidth={2} dot={series.length < 15} activeDot={{ r: 4 }} isAnimationActive={false} />
        <Line type="linear" dataKey="delivered" name="Delivered" stroke="var(--gr-info)" strokeWidth={1.7} strokeDasharray="5 4" dot={false} isAnimationActive={false} />
        <Line type="linear" dataKey="blocked" name="Not delivered" stroke="var(--gr-warning)" strokeWidth={1.7} dot={false} isAnimationActive={false} />
      </LineChart></ResponsiveContainer>
    </div>
    <details className="obs-chart-data"><summary>View daily data table</summary><TableWrap label="Daily request volume"><table className="obs-table"><thead><tr><th>Date</th><th>All requests</th><th>Delivered</th><th>Not delivered</th></tr></thead><tbody>{series.map((point) => <tr key={point.ts}><td>{dateLabel(point.ts)}</td><td>{formatNumber(point.total)}</td><td>{formatNumber(point.delivered)}</td><td>{formatNumber(point.blocked)}</td></tr>)}</tbody></table></TableWrap></details>
  </>;
}

export default function AnalyticsView() {
  const [days, setDays] = useState(30);
  const [dash, setDash] = useState<DashboardData | null>(null);
  const [users, setUsers] = useState<UserUsageStat[]>([]);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState("");
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const [sortCol, setSortCol] = useState<keyof UserUsageStat>("requests");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const sequence = useRef(0);
  const load = useCallback(async () => {
    const request = ++sequence.current;
    setLoading(true); setError("");
    const params = new URLSearchParams({ days: String(days) });
    const results = await Promise.allSettled([api<DashboardData>(`/analytics/dashboard?${params}`), api<UserUsageStat[]>(`/analytics/users?${params}`)]);
    if (request !== sequence.current) return;
    if (results[0].status === "fulfilled") setDash(results[0].value); else setDash(null);
    if (results[1].status === "fulfilled") setUsers(results[1].value); else setUsers([]);
    setError(results.flatMap((result, index) => result.status === "rejected" ? [`${index ? "User usage" : "Traffic analytics"}: ${result.reason instanceof Error ? result.reason.message : String(result.reason)}`] : []).join(" "));
    if (results.every((result) => result.status === "fulfilled")) setUpdatedAt(new Date());
    setLoading(false);
  }, [days]);
  useEffect(() => { void load(); return () => { sequence.current++; }; }, [load]);
  function toggleSort(column: keyof UserUsageStat) { if (sortCol === column) setSortDir((direction) => direction === "asc" ? "desc" : "asc"); else { setSortCol(column); setSortDir(column === "email" ? "asc" : "desc"); } }
  const sortedUsers = useMemo(() => [...users].sort((a, b) => {
    const left = a[sortCol] ?? 0; const right = b[sortCol] ?? 0;
    const comparison = typeof left === "string" && typeof right === "string" ? left.localeCompare(right) : Number(left) - Number(right);
    return sortDir === "asc" ? comparison : -comparison;
  }), [users, sortCol, sortDir]);
  async function exportCsv() {
    setExporting(true); setError("");
    try {
      const token = await getAuthToken();
      if (!token) throw new Error("Sign in to export request logs.");
      const response = await fetch(`${BASE_URL}/analytics/export?days=${days}`, { headers: { Authorization: `Bearer ${token}` } });
      if (!response.ok) { const detail = await response.json().catch(() => ({ detail: response.statusText })); throw new Error(formatApiError(detail.detail)); }
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a"); link.href = url; link.download = `guardrails-logs-${days}d.csv`; document.body.appendChild(link); link.click(); link.remove(); window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (failure) { setError(failure instanceof Error ? failure.message : String(failure)); }
    finally { setExporting(false); }
  }
  const summary = dash?.summary;
  const blocked = summary ? summary.input_blocked + summary.output_blocked : 0;
  const metrics = summary ? [
    { label: "Total requests", value: formatNumber(summary.total_requests), note: `${days}-day window` },
    { label: "Delivered", value: formatNumber(summary.delivered), note: `${summary.total_requests ? ((summary.delivered / summary.total_requests) * 100).toFixed(1) : "0"}% delivered`, tone: "success" },
    { label: "Policy blocked", value: formatNumber(blocked), note: `${formatNumber(summary.input_blocked)} input · ${formatNumber(summary.output_blocked)} output`, tone: "warning" },
    { label: "Block rate", value: `${summary.block_rate_pct}%`, note: "Includes rate-limited requests" },
    { label: "Average latency", value: `${formatNumber(summary.avg_latency_ms)} ms`, note: "Mean request latency" },
    { label: "Estimated cost", value: `$${Number(summary.estimated_cost_usd || 0).toFixed(4)}`, note: "Provider pricing estimate · USD" },
    { label: "Total tokens", value: formatNumber(summary.total_tokens), note: "Input and output combined" },
    { label: "Gateway errors", value: formatNumber(summary.error_count), note: `${formatNumber(summary.rate_limited)} requests rate limited` },
  ] : [];

  return <div className="obs-page">
    <PageHeader eyebrow="OBSERVABILITY" title="Analytics" description="Understand request volume, policy decisions, and the cost of your AI traffic." actions={<><Button icon="refresh" loading={loading} onClick={() => void load()}>Refresh</Button><Button variant="primary" icon="external" loading={exporting} onClick={() => void exportCsv()}>Export CSV</Button></>} />
    <div className="obs-period-toolbar"><div className="ui-tabs" aria-label="Analytics time window">{[7, 14, 30, 60, 90].map((period) => <button type="button" key={period} aria-pressed={days === period} className={days === period ? "is-active" : ""} onClick={() => setDays(period)}>{period} days</button>)}</div><span className="obs-updated">{updatedAt ? `Last updated ${updatedAt.toLocaleTimeString()}` : "Organization activity"}</span></div>
    {error && <Notice tone="danger">{error}</Notice>}
    {loading ? <LoadingState label="Loading analytics" /> : <>
      {summary && <div className="obs-metrics">{metrics.map((metric) => <div className={`obs-metric${metric.tone ? ` is-${metric.tone}` : ""}`} key={metric.label}><span>{metric.label}</span><strong>{metric.value}</strong><small>{metric.note}</small></div>)}</div>}
      {dash && <>
        <Panel title="Daily request volume" description="Not delivered includes blocked, rate-limited, and failed requests." actions={<Badge>{dash.time_series.length} reporting days</Badge>}><TrafficChart series={dash.time_series} /></Panel>
        <div className="obs-analytics-panels">
          <Panel title="Rules that fired" description="Most frequent policy rules in the selected window.">
            {!dash.top_rules.length ? <EmptyState icon="shield" title="No rules fired" description="No policy rule was recorded for this period." /> : <div className="obs-rules">{dash.top_rules.map((rule) => { const percent = summary?.total_requests ? rule.count / summary.total_requests * 100 : 0; return <div className="obs-rule" key={rule.rule}><div><code>{rule.rule}</code><strong>{formatNumber(rule.count)}</strong><span>{percent.toFixed(1)}%</span></div><progress value={Math.min(percent, 100)} max={100} aria-label={`${rule.rule}: ${percent.toFixed(1)} percent of requests`} /></div>; })}</div>}
          </Panel>
          <Panel title="Delivery outcomes" description="Every request outcome reported by the gateway.">
            <dl className="obs-properties">{summary && [["Delivered", summary.delivered], ["Input blocked", summary.input_blocked], ["Output blocked", summary.output_blocked], ["Rate limited", summary.rate_limited || 0], ["Errors", summary.error_count]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd className="obs-mono">{formatNumber(Number(value))}</dd></div>)}</dl>
          </Panel>
        </div>
        {(dash.provider_usage || []).length > 0 && <Panel title="Provider usage" description="Delivered requests grouped by provider and model."><TableWrap label="Provider usage"><table className="obs-table"><thead><tr><th>Provider</th><th>Model</th><th>Requests</th><th>Tokens</th></tr></thead><tbody>{dash.provider_usage.map((provider) => <tr key={`${provider.backend}-${provider.model}`}><td className="obs-mono">{provider.backend}</td><td className="obs-mono">{provider.model}</td><td>{formatNumber(provider.count)}</td><td>{formatNumber(provider.tokens)}</td></tr>)}</tbody></table></TableWrap></Panel>}
      </>}
      <Panel title="Usage by teammate" description="Request counts follow the selected window. Token use is lifetime; balance is current." actions={<Badge>{sortedUsers.length} users</Badge>}>
        {!sortedUsers.length ? <EmptyState icon="team" title="No teammate usage to show" description="Invite teammates or run a request in the Playground." /> : <TableWrap label="Per-user usage"><table className="obs-table"><thead><tr>{([["email", "Teammate"], ["requests", "Requests"], ["blocked", "Not delivered"], ["tokens_used_lifetime", "Lifetime tokens"], ["tokens_balance", "Current balance"]] as [keyof UserUsageStat, string][]).map(([column, label]) => <th key={column} aria-sort={sortCol === column ? sortDir === "asc" ? "ascending" : "descending" : "none"}><button type="button" className="obs-sort-button" onClick={() => toggleSort(column)}>{label}<span aria-hidden="true">{sortCol === column ? sortDir === "asc" ? "↑" : "↓" : "↕"}</span></button></th>)}</tr></thead><tbody>{sortedUsers.map((user) => <tr key={user.id}><td><strong>{user.full_name || user.email}</strong>{user.full_name && <span className="obs-cell-secondary">{user.email}</span>}</td><td>{formatNumber(user.requests)}</td><td>{formatNumber(user.blocked)} <span className="obs-cell-secondary">{user.requests ? (user.blocked / user.requests * 100).toFixed(0) : "0"}%</span></td><td>{formatNumber(user.tokens_used_lifetime)}</td><td><Badge tone={user.tokens_balance < 500 ? "warning" : "neutral"}>{formatNumber(user.tokens_balance)}</Badge></td></tr>)}</tbody></table></TableWrap>}
      </Panel>
    </>}
  </div>;
}
