import React, { useEffect, useMemo, useState } from "react";
import { api } from "../utils/api";
import AppIcon from "../components/AppIcon";
import RequestJourney from "../components/RequestJourney";
import type { components } from "../api-types";
import type { RecentLogItem, SuspiciousLogItem } from "../api-supplementary";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import "../styles/dashboard.css";

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

const count = (value: number) => value.toLocaleString();
const compactCount = (value: number) => Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 }).format(value);
const readableStatus = (status: string) => status.replaceAll("_", " ");

function dateLabel(value: string) {
  const date = new Date(value.length === 10 ? `${value}T12:00:00` : value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function requestTime(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

function ArrowIcon() {
  return <AppIcon name="arrow" size={16} />;
}

function RefreshIcon() {
  return <AppIcon name="refresh" size={16} />;
}

function EmptyState({ title, children, link, action }: { title: string; children: React.ReactNode; link?: string; action?: string }) {
  return <div className="gr-dash-empty"><div className="gr-dash-empty-mark" aria-hidden="true"><AppIcon name="chart" size={22} /></div><h3>{title}</h3><p>{children}</p>{link && action && <a href={link} className="gr-dash-text-link">{action}<ArrowIcon /></a>}</div>;
}

function StatusBadge({ status }: { status: string }) {
  const kind = status === "delivered" ? "delivered" : status === "error" ? "error" : "blocked";
  return <span className={`gr-dash-status gr-dash-status-${kind}`}><span aria-hidden="true" />{readableStatus(status)}</span>;
}

function ChartTooltip({ active, payload, label }: { active?: boolean; payload?: readonly { name?: string | number; value?: unknown; color?: string }[]; label?: React.ReactNode }) {
  if (!active || !payload?.length) return null;
  return <div className="gr-dash-tooltip"><strong>{typeof label === "string" && /^\d{4}-\d{2}-\d{2}$/.test(label) ? dateLabel(label) : label}</strong>{payload.map((item, index) => <div key={index}><span className="gr-dash-tooltip-label"><i style={{ background: item.color }} />{item.name}</span><span>{typeof item.value === "number" ? count(item.value) : String(item.value ?? "")}</span></div>)}</div>;
}

function LoadingDashboard() {
  return <div role="status" aria-live="polite" className="gr-dash-loading"><span className="gr-dash-sr-only">Loading workspace activity.</span><div className="gr-dash-metrics" aria-hidden="true">{Array.from({ length: 4 }, (_, index) => <div className="gr-dash-metric gr-dash-skeleton-card" key={index}><span className="gr-dash-skeleton gr-dash-skeleton-label" /><span className="gr-dash-skeleton gr-dash-skeleton-value" /><span className="gr-dash-skeleton gr-dash-skeleton-label" /></div>)}</div><div className="gr-dash-primary-grid" aria-hidden="true"><div className="gr-dash-panel gr-dash-skeleton-panel" /><div className="gr-dash-panel gr-dash-skeleton-panel" /></div></div>;
}

export default function DashboardView() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState("");
  const [days, setDays] = useState(7);
  const [reload, setReload] = useState(0);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);

  useEffect(() => {
    let current = true;
    setData(null);
    setError("");
    setUpdatedAt(null);
    api<DashboardData>(`/analytics/dashboard?days=${days}`)
      .then((result) => { if (current) { setData(result); setUpdatedAt(new Date()); } })
      .catch((reason: Error) => { if (current) setError(reason.message); });
    return () => { current = false; };
  }, [days, reload]);

  const providerCounts = useMemo(() => {
    const totals = new Map<string, number>();
    for (const item of data?.provider_usage ?? []) totals.set(item.backend, (totals.get(item.backend) ?? 0) + item.count);
    return [...totals].map(([backend, requests]) => ({ backend, requests })).sort((a, b) => b.requests - a.requests);
  }, [data]);

  const modelTokens = useMemo(() => {
    const totals = new Map<string, number>();
    for (const item of data?.provider_usage ?? []) totals.set(item.model, (totals.get(item.model) ?? 0) + item.tokens);
    return [...totals].map(([model, tokens]) => ({ model, tokens })).sort((a, b) => b.tokens - a.tokens);
  }, [data]);

  const summary = data?.summary;
  const blockedTotal = summary ? summary.input_blocked + summary.output_blocked + (summary.rate_limited ?? 0) : 0;
  const topRules = data?.top_rules ?? [];
  const maxRule = Math.max(...topRules.map((rule) => rule.count), 1);
  const providerTotal = providerCounts.reduce((total, item) => total + item.requests, 0);
  const recentSuspicious = data?.recent_suspicious ?? [];
  const recentLogs = data?.recent_logs ?? [];
  const timeSeries = data?.time_series ?? [];
  const gridStyle = { stroke: "var(--gr-border)", strokeDasharray: "3 5", vertical: false };
  const tickStyle = { fontSize: 11, fill: "var(--gr-muted)", fontFamily: "var(--gr-font)" };

  return <div className="gr-dashboard">
    <header className="gr-dash-welcome">
      <div className="gr-dash-welcome-copy">
        <p className="gr-dash-welcome-eyebrow"><AppIcon name="sparkles" size={16} /> SMALL CHECKS. MORE CONFIDENCE.</p>
        <h1>Welcome to your <span>AI workspace.</span></h1>
        <p>Ask a question. Check what happens. Make AI work a little better for you.</p>
        <div className="gr-dash-welcome-actions">
          <a className="gr-dash-primary-link" href="?view=chat">Try a question<ArrowIcon /></a>
          <a className="gr-dash-text-link" href="?view=about">Show me around<AppIcon name="help" size={16} /></a>
        </div>
        <p className="gr-dash-welcome-note">New here? The example walks you through it.</p>
      </div>
      <RequestJourney compact />
    </header>

    <div className="gr-dash-header gr-dash-activity-header">
      <div><div className="gr-dash-eyebrow">Your workspace activity</div><h2>Every request, accounted for.</h2><p>Real requests and the decisions your guardrails make.</p></div>
      <div className="gr-dash-header-actions"><label className="gr-dash-range-label"><span className="gr-dash-sr-only">Activity period</span><select value={days} onChange={(event) => setDays(Number(event.target.value))}><option value={7}>Last 7 days</option><option value={30}>Last 30 days</option><option value={90}>Last 90 days</option></select></label><button className="gr-dash-button" onClick={() => setReload((value) => value + 1)} disabled={!data && !error}><RefreshIcon /><span>Refresh</span></button></div>
    </div>

    {error ? <section className="gr-dash-error" role="alert"><div><h2>Activity could not be loaded</h2><p>{error}</p></div><button className="gr-dash-button" onClick={() => setReload((value) => value + 1)}>Try again<ArrowIcon /></button></section> : !data || !summary ? <LoadingDashboard /> : <>
      <section className="gr-dash-metrics" aria-label="Request metrics">
        <article className="gr-dash-metric"><div className="gr-dash-metric-label">Total requests<span className="gr-dash-metric-index">01</span></div><strong>{count(summary.total_requests)}</strong><p><span>{count(summary.delivered)}</span> delivered to your models</p></article>
        <article className="gr-dash-metric gr-dash-metric-accent"><div className="gr-dash-metric-label">Prevented requests<span className="gr-dash-metric-index">02</span></div><strong>{count(blockedTotal)}</strong><p><span>{summary.block_rate_pct.toLocaleString(undefined, { maximumFractionDigits: 2 })}%</span> blocked or rate limited</p></article>
        <article className="gr-dash-metric"><div className="gr-dash-metric-label">Average latency<span className="gr-dash-metric-index">03</span></div><strong>{summary.avg_latency_ms.toLocaleString(undefined, { maximumFractionDigits: 1 })}<small>ms</small></strong><p>Across all logged requests</p></article>
        <article className="gr-dash-metric"><div className="gr-dash-metric-label">Tokens used<span className="gr-dash-metric-index">04</span></div><strong title={count(summary.total_tokens)}>{compactCount(summary.total_tokens)}</strong><p>Input + output tokens</p></article>
      </section>

      <section className="gr-dash-outcomes" aria-label="Additional request outcomes"><div><span>Input blocked</span><strong>{count(summary.input_blocked)}</strong></div><div><span>Output blocked</span><strong>{count(summary.output_blocked)}</strong></div><div><span>Rate limited</span><strong>{count(summary.rate_limited ?? 0)}</strong></div><div><span>Failed requests</span><strong>{count(summary.error_count)}</strong></div>{updatedAt && <p>Updated <time dateTime={updatedAt.toISOString()}>{updatedAt.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}</time></p>}</section>

      <div className="gr-dash-primary-grid">
        <section className="gr-dash-panel gr-dash-traffic" aria-labelledby="gr-traffic-title"><div className="gr-dash-panel-heading"><div><div className="gr-dash-eyebrow">Request activity</div><h2 id="gr-traffic-title">Traffic over time</h2></div><span className="gr-dash-period">Daily / {days} days</span></div>
          <div className="gr-dash-chart-legend"><span><i className="gr-dash-delivered-key" />Delivered</span><span><i className="gr-dash-blocked-key" />Not delivered</span></div>
          {timeSeries.length === 0 ? <EmptyState title="Your traffic starts here" link="?view=chat" action="Open the playground">Send a request through the gateway to see its path.</EmptyState> : <>
            <div className="gr-dash-chart" role="group" aria-label="Daily delivered and non-delivered requests"><ResponsiveContainer width="100%" height={244}><AreaChart accessibilityLayer data={timeSeries} margin={{ top: 14, right: 8, left: -18, bottom: 2 }}>
              <CartesianGrid {...gridStyle} /><XAxis dataKey="ts" tick={tickStyle} tickLine={false} axisLine={false} tickFormatter={dateLabel} minTickGap={28} dy={8} /><YAxis tick={tickStyle} tickLine={false} axisLine={false} allowDecimals={false} tickFormatter={compactCount} />
              <Tooltip content={<ChartTooltip />} cursor={{ stroke: "var(--gr-muted)", strokeDasharray: "3 3" }} />
              <Area name="Delivered" type="linear" dataKey="delivered" stroke="var(--gr-accent)" strokeWidth={2} fill="var(--gr-accent-soft)" fillOpacity={0.65} dot={timeSeries.length === 1} activeDot={{ r: 4, strokeWidth: 2 }} isAnimationActive={false} />
              <Area name="Not delivered" type="linear" dataKey="blocked" stroke="var(--gr-dash-warning)" strokeDasharray="4 3" strokeWidth={1.8} fill="var(--gr-dash-warning-soft)" fillOpacity={0.5} dot={timeSeries.length === 1} activeDot={{ r: 4, strokeWidth: 2 }} isAnimationActive={false} />
            </AreaChart></ResponsiveContainer></div><p className="gr-dash-chart-note">Not delivered includes blocked, rate-limited, and failed requests.</p>
            <details className="gr-dash-data-details"><summary>View chart data</summary><div className="gr-dash-table-wrap" role="region" aria-label="Traffic chart data" tabIndex={0}><table><caption className="gr-dash-sr-only">Daily request activity over the last {days} days</caption><thead><tr><th scope="col">Date</th><th scope="col">Delivered</th><th scope="col">Not delivered</th><th scope="col">Total</th></tr></thead><tbody>{timeSeries.map((point) => <tr key={point.ts}><th scope="row">{dateLabel(point.ts)}</th><td>{count(point.delivered)}</td><td>{count(point.blocked)}</td><td>{count(point.total)}</td></tr>)}</tbody></table></div></details>
          </>}
        </section>

        <section className="gr-dash-panel gr-dash-rules" aria-labelledby="gr-rules-title"><div className="gr-dash-panel-heading"><div><div className="gr-dash-eyebrow">Policy signals</div><h2 id="gr-rules-title">Most triggered rules</h2></div><a className="gr-dash-icon-link" href="?view=policy" aria-label="Manage your policies"><ArrowIcon /></a></div>
          {topRules.length === 0 ? <EmptyState title="No rules triggered" link="?view=policy" action="Review your policies">Rule activity will appear when a request matches your policy.</EmptyState> : <ol className="gr-dash-rule-list">{topRules.map((rule, index) => <li key={rule.rule}><div className="gr-dash-rule-label"><span className="gr-dash-rule-position">{String(index + 1).padStart(2, "0")}</span><span title={rule.rule}>{readableStatus(rule.rule)}</span><strong>{count(rule.count)}</strong></div><div className="gr-dash-rule-track" aria-hidden="true"><span style={{ width: `${rule.count / maxRule * 100}%` }} /></div></li>)}</ol>}
          <div className="gr-dash-panel-footer"><a href="?view=policy" className="gr-dash-text-link">Manage policies<ArrowIcon /></a><span>Last {days} days</span></div>
        </section>
      </div>

      <div className="gr-dash-secondary-grid">
        <section className="gr-dash-panel" aria-labelledby="gr-provider-title"><div className="gr-dash-panel-heading"><div><div className="gr-dash-eyebrow">Model routing</div><h2 id="gr-provider-title">Delivered by provider</h2></div><span className="gr-dash-period">Requests</span></div>
          {providerTotal === 0 ? <EmptyState title="No provider traffic yet">Delivered requests will show which providers you use.</EmptyState> : <><div className="gr-dash-provider-list">{providerCounts.map((item) => <div className="gr-dash-provider-row" key={item.backend}><div><span className="gr-dash-provider-name">{item.backend}</span><strong>{count(item.requests)} <small>{Math.round(item.requests / providerTotal * 100)}%</small></strong></div><div className="gr-dash-provider-track" aria-hidden="true"><span style={{ width: `${item.requests / providerTotal * 100}%` }} /></div></div>)}</div><p className="gr-dash-chart-note">Share of delivered traffic across your top 10 provider/model combinations.</p></>}
        </section>

        <section className="gr-dash-panel" aria-labelledby="gr-tokens-title"><div className="gr-dash-panel-heading"><div><div className="gr-dash-eyebrow">Model usage</div><h2 id="gr-tokens-title">Tokens by model</h2></div><span className="gr-dash-period">Input + output</span></div>
          {modelTokens.length === 0 ? <EmptyState title="No token usage yet">Compare model usage after requests are delivered.</EmptyState> : <><div className="gr-dash-chart" role="group" aria-label="Tokens used by model"><ResponsiveContainer width="100%" height={210}><BarChart accessibilityLayer data={modelTokens} layout="vertical" margin={{ top: 0, right: 16, bottom: 0, left: 0 }} barSize={14}>
            <CartesianGrid stroke="var(--gr-border)" strokeDasharray="3 5" horizontal={false} /><XAxis type="number" tick={tickStyle} tickLine={false} axisLine={false} tickFormatter={compactCount} /><YAxis type="category" dataKey="model" tick={{ ...tickStyle, fontSize: 10 }} tickLine={false} axisLine={false} width={110} tickFormatter={(model: string) => model.length > 17 ? `${model.slice(0, 16)}…` : model} /><Tooltip content={<ChartTooltip />} cursor={{ fill: "var(--gr-accent-soft)", fillOpacity: 0.4 }} /><Bar name="Tokens" dataKey="tokens" fill="var(--gr-accent)" radius={[0, 3, 3, 0]} isAnimationActive={false} />
          </BarChart></ResponsiveContainer></div><details className="gr-dash-data-details"><summary>View model data</summary><div className="gr-dash-table-wrap" role="region" aria-label="Model token data" tabIndex={0}><table><caption className="gr-dash-sr-only">Delivered token usage by model</caption><thead><tr><th scope="col">Model</th><th scope="col">Tokens</th></tr></thead><tbody>{modelTokens.map((item) => <tr key={item.model}><th scope="row">{item.model}</th><td>{count(item.tokens)}</td></tr>)}</tbody></table></div></details></>}
        </section>
      </div>

      <section className="gr-dash-panel gr-dash-table-panel" aria-labelledby="gr-review-title"><div className="gr-dash-panel-heading"><div><div className="gr-dash-eyebrow">Attention queue</div><h2 id="gr-review-title">Requests to review</h2><p>Blocked, rate-limited, and failed requests.</p></div><a className="gr-dash-text-link" href="?view=logs">Open request logs<ArrowIcon /></a></div>
        {recentSuspicious.length === 0 ? <EmptyState title="Nothing to review in this period">Requests that need attention will appear here with their reason.</EmptyState> : <div className="gr-dash-table-wrap" role="region" aria-label="Requests to review" tabIndex={0}><table><caption className="gr-dash-sr-only">Recent blocked, rate-limited, and failed requests</caption><thead><tr><th scope="col">Outcome</th><th scope="col">Prompt preview</th><th scope="col">Reason</th><th scope="col">Time</th></tr></thead><tbody>{recentSuspicious.map((log) => <tr key={log.id}><td><StatusBadge status={log.status} /></td><td className="gr-dash-prompt-cell">{log.prompt_preview || "No preview available"}</td><td className="gr-dash-reason-cell">{log.reason || log.fired_rule || "No reason recorded"}</td><td className="gr-dash-time-cell"><time dateTime={log.created_at}>{requestTime(log.created_at)}</time></td></tr>)}</tbody></table></div>}
      </section>

      <section className="gr-dash-panel gr-dash-table-panel" aria-labelledby="gr-recent-title"><div className="gr-dash-panel-heading"><div><div className="gr-dash-eyebrow">Request ledger</div><h2 id="gr-recent-title">Recent requests</h2><p>Your latest {Math.min(recentLogs.length, 10)} requests in this period.</p></div><a className="gr-dash-text-link" href="?view=logs">View all logs<ArrowIcon /></a></div>
        {recentLogs.length === 0 ? <EmptyState title="Ready for your first request" link="?view=chat" action="Try the playground">Send a prompt to see your guardrails in action.</EmptyState> : <div className="gr-dash-table-wrap" role="region" aria-label="Recent requests" tabIndex={0}><table><caption className="gr-dash-sr-only">Latest requests through the gateway</caption><thead><tr><th scope="col">Outcome</th><th scope="col">Prompt preview</th><th scope="col">Rule</th><th scope="col">Provider</th><th scope="col" className="gr-dash-numeric">Latency</th><th scope="col">Time</th></tr></thead><tbody>{recentLogs.slice(0, 10).map((log) => <tr key={log.id}><td><StatusBadge status={log.status} /></td><td className="gr-dash-prompt-cell">{log.prompt_preview || "No preview available"}</td><td className="gr-dash-rule-cell">{log.fired_rule ? readableStatus(log.fired_rule) : "—"}</td><td><span className="gr-dash-provider-name">{log.backend}</span></td><td className="gr-dash-numeric gr-dash-time-cell">{count(log.latency_ms)} <span className="gr-dash-unit">ms</span></td><td className="gr-dash-time-cell"><time dateTime={log.created_at}>{requestTime(log.created_at)}</time></td></tr>)}</tbody></table></div>}
      </section>
    </>}
  </div>;
}
