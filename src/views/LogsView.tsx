import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, BASE_URL, formatApiError, getAuthToken } from "../utils/api";
import { Badge, Button, Dialog, EmptyState, Field, LoadingState, Notice, PageHeader, Panel, TableWrap } from "../components/ui";
import type { Tone } from "../components/ui";
import type { RequestLogItem, LogsResponse } from "../api-supplementary";
import "../styles/observability.css";

type SortColumn = keyof RequestLogItem | "";
type FeedState = "connecting" | "live" | "fallback" | "paused";
const STATUS_FILTERS = ["", "delivered", "input_blocked", "output_blocked", "rate_limited", "error"];
const statusLabel = (status: string) => status.replaceAll("_", " ");
const statusTone = (status: string): Tone => status === "delivered" ? "success" : status === "error" ? "danger" : status.includes("blocked") ? "warning" : status === "rate_limited" ? "info" : "neutral";
const errorMessage = (error: unknown) => error instanceof Error ? error.message : String(error);

function feedSocketUrl(token: string): string {
  const base = import.meta.env.DEV ? import.meta.env.VITE_FEED_WS_URL || "ws://localhost:4000" : `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}`;
  const url = new URL(`${base.replace(/\/$/, "")}/live-feed/websocket`);
  url.searchParams.set("token", token); url.searchParams.set("vsn", "2.0.0");
  return url.toString();
}

function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [state, setState] = useState<"idle" | "copied" | "error">("idle");
  useEffect(() => { if (state === "idle") return; const timer = window.setTimeout(() => setState("idle"), 2200); return () => window.clearTimeout(timer); }, [state]);
  async function copy() { try { await navigator.clipboard.writeText(text); setState("copied"); } catch { setState("error"); } }
  return <Button variant="ghost" icon={state === "copied" ? "check" : "copy"} onClick={() => void copy()} aria-live="polite">{state === "copied" ? "Copied" : state === "error" ? "Copy failed; retry" : label}</Button>;
}

function RequestDetails({ log }: { log: RequestLogItem }) {
  const fullPrompt = (log as Omit<RequestLogItem, "full_prompt"> & { full_prompt?: string | null }).full_prompt;
  return <div className="obs-log-details">
    <div className="obs-detail-toolbar"><Badge tone={statusTone(log.status)}>{statusLabel(log.status)}</Badge><CopyButton text={log.request_id || log.id} label="Copy request ID" /><CopyButton text={JSON.stringify(log, null, 2)} label="Copy JSON" /></div>
    <dl className="obs-properties obs-detail-properties"><div><dt>Request ID</dt><dd className="obs-mono">{log.request_id || log.id}</dd></div><div><dt>Recorded</dt><dd>{new Date(log.created_at).toLocaleString()}</dd></div><div><dt>Provider / model</dt><dd className="obs-mono">{log.backend} / {log.model || "Not called"}</dd></div><div><dt>Latency</dt><dd>{log.latency_ms.toLocaleString()} ms</dd></div><div><dt>Input tokens</dt><dd>{(log.input_tokens || 0).toLocaleString()}</dd></div><div><dt>Output tokens</dt><dd>{(log.output_tokens || 0).toLocaleString()}</dd></div><div><dt>Input check</dt><dd>{log.status === "rate_limited" ? "Not run" : log.input_passed ? "Passed" : "Not passed"}</dd></div><div><dt>Output check</dt><dd>{["input_blocked", "rate_limited"].includes(log.status) ? "Not run" : log.output_passed ? "Passed" : "Not passed"}</dd></div><div><dt>Fired rule</dt><dd className="obs-mono">{log.fired_rule || "None recorded"}</dd></div></dl>
    {log.input_block_reason && <Notice tone="warning"><strong>Input decision:</strong> {log.input_block_reason}</Notice>}{log.output_block_reason && <Notice tone="warning"><strong>Output decision:</strong> {log.output_block_reason}</Notice>}
    <h3>{fullPrompt ? "Stored prompt" : "Prompt preview"}</h3><pre className="obs-prompt-preview">{fullPrompt || log.prompt_preview || "No preview retained."}</pre>
    {!fullPrompt && <p className="obs-footnote">The dashboard receives a redacted preview. Full prompts are not exposed by this endpoint.</p>}
  </div>;
}

export default function LogsView() {
  const [logs, setLogs] = useState<RequestLogItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState("");
  const [keyword, setKeyword] = useState("");
  const [keywordInput, setKeywordInput] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [backendFilter, setBackendFilter] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [selectedLog, setSelectedLog] = useState<RequestLogItem | null>(null);
  const [expandedLog, setExpandedLog] = useState<string | null>(null);
  const [sortColumn, setSortColumn] = useState<SortColumn>("");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");
  const [feedEnabled, setFeedEnabled] = useState(true);
  const [feedState, setFeedState] = useState<FeedState>("connecting");
  const [showFilters, setShowFilters] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const [exportDays, setExportDays] = useState(30);
  const [exporting, setExporting] = useState(false);
  const sequence = useRef(0);
  const fetching = useRef(false);
  const loadRef = useRef<(background?: boolean) => Promise<void>>(async () => {});
  const load = useCallback(async (background = false) => {
    if (background && fetching.current) return;
    const request = ++sequence.current; fetching.current = true;
    if (!background) setLoading(true); setError("");
    const params = new URLSearchParams({ page: String(page), page_size: "25" });
    if (statusFilter) params.set("status_filter", statusFilter); if (keyword) params.set("keyword", keyword);
    if (dateFrom) params.set("date_from", dateFrom); if (dateTo) params.set("date_to", dateTo); if (backendFilter) params.set("backend_filter", backendFilter);
    try { const data = await api<LogsResponse>(`/analytics/logs?${params}`); if (request === sequence.current) { setLogs(data.items); setTotal(data.total); setUpdatedAt(new Date()); } }
    catch (failure) { if (request === sequence.current) setError(errorMessage(failure)); }
    finally { if (request === sequence.current) { fetching.current = false; setLoading(false); } }
  }, [page, statusFilter, keyword, dateFrom, dateTo, backendFilter]);
  loadRef.current = load;
  useEffect(() => { void load(); return () => { sequence.current++; fetching.current = false; }; }, [load]);
  useEffect(() => {
    if (!feedEnabled) { setFeedState("paused"); return; }
    let disposed = false; let socket: WebSocket | null = null; let heartbeat: number | undefined; let joinTimeout: number | undefined; let refreshTimer: number | undefined; let nextReference = 1;
    setFeedState("connecting");
    const clearTimers = () => { if (heartbeat) window.clearInterval(heartbeat); if (joinTimeout) window.clearTimeout(joinTimeout); if (refreshTimer) window.clearTimeout(refreshTimer); };
    async function connect() {
      try {
        const token = await getAuthToken(); if (!token) throw new Error("No session");
        const me = await api<{ org_id?: string | null }>("/auth/me"); if (!me.org_id) throw new Error("No organization"); if (disposed) return;
        const topic = `requests:${me.org_id}`; const joinReference = String(nextReference++);
        socket = new WebSocket(feedSocketUrl(token));
        joinTimeout = window.setTimeout(() => { if (!disposed) { setFeedState("fallback"); socket?.close(); } }, 10_000);
        socket.onopen = () => { if (disposed) return; socket?.send(JSON.stringify([null, joinReference, topic, "phx_join", {}])); heartbeat = window.setInterval(() => { if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify([null, String(nextReference++), "phoenix", "heartbeat", {}])); }, 15_000); };
        socket.onmessage = (event) => {
          if (disposed) return;
          try {
            const [, reference, eventTopic, eventName, payload] = JSON.parse(event.data) as [unknown, string, string, string, { status?: string; id?: string }];
            if (eventName === "phx_reply" && reference === joinReference) { if (payload?.status === "ok") { if (joinTimeout) window.clearTimeout(joinTimeout); setFeedState("live"); } else socket?.close(); }
            else if (eventName === "new_request" && eventTopic === topic && payload?.id) { if (refreshTimer) window.clearTimeout(refreshTimer); refreshTimer = window.setTimeout(() => void loadRef.current(true), 180); }
          } catch { /* Ignore malformed frames. */ }
        };
        socket.onerror = () => socket?.close();
        socket.onclose = () => { clearTimers(); if (!disposed) setFeedState("fallback"); };
      } catch { if (!disposed) setFeedState("fallback"); }
    }
    void connect();
    return () => { disposed = true; clearTimers(); socket?.close(); };
  }, [feedEnabled]);
  useEffect(() => { if (!feedEnabled || feedState === "live") return; const timer = window.setInterval(() => void loadRef.current(true), 15_000); return () => window.clearInterval(timer); }, [feedEnabled, feedState]);
  function clearFilters() { setKeyword(""); setKeywordInput(""); setDateFrom(""); setDateTo(""); setBackendFilter(""); setStatusFilter(""); setPage(1); }
  function toggleSort(column: keyof RequestLogItem) { if (sortColumn === column) setSortDirection((direction) => direction === "asc" ? "desc" : "asc"); else { setSortColumn(column); setSortDirection("asc"); } }
  const sorted = useMemo(() => sortColumn ? [...logs].sort((a, b) => { const left = a[sortColumn] ?? ""; const right = b[sortColumn] ?? ""; const comparison = typeof left === "number" && typeof right === "number" ? left - right : String(left).localeCompare(String(right)); return sortDirection === "asc" ? comparison : -comparison; }) : logs, [logs, sortColumn, sortDirection]);
  const hasFilters = !!(statusFilter || keyword || dateFrom || dateTo || backendFilter);
  const filterCount = [dateFrom, dateTo, backendFilter].filter(Boolean).length;
  async function exportCsv() {
    setExporting(true); setError("");
    try { const token = await getAuthToken(); if (!token) throw new Error("Sign in to export request logs."); const response = await fetch(`${BASE_URL}/analytics/export?days=${exportDays}`, { headers: { Authorization: `Bearer ${token}` } }); if (!response.ok) { const detail = await response.json().catch(() => ({ detail: response.statusText })); throw new Error(formatApiError(detail.detail)); } const url = URL.createObjectURL(await response.blob()); const link = document.createElement("a"); link.href = url; link.download = `guardrails-logs-${exportDays}d.csv`; document.body.appendChild(link); link.click(); link.remove(); window.setTimeout(() => URL.revokeObjectURL(url), 1000); }
    catch (failure) { setError(errorMessage(failure)); } finally { setExporting(false); }
  }

  return <div className="obs-page">
    <PageHeader eyebrow="REQUEST TRACE" title="Request logs" description="Follow each gateway request from policy decision to provider response." actions={<><Button icon="refresh" loading={loading} onClick={() => void load()}>Refresh</Button><Button icon="external" loading={exporting} onClick={() => void exportCsv()}>Export CSV</Button></>} />
    <div className="obs-log-toolbar"><div className="obs-live-controls"><label className="obs-checkbox"><input type="checkbox" checked={feedEnabled} onChange={(event) => setFeedEnabled(event.target.checked)} />Live updates</label><Badge tone={feedState === "live" ? "success" : "neutral"}>{feedState === "live" ? "Connected" : feedState === "connecting" ? "Connecting" : feedState === "paused" ? "Paused" : "Refreshing every 15s"}</Badge></div><span className="obs-updated">{total.toLocaleString()} matching requests{updatedAt ? ` · Updated ${updatedAt.toLocaleTimeString()}` : ""}</span></div>
    {error && <Notice tone="danger">{error}</Notice>}
    <Panel className="obs-log-filter-panel"><form className="obs-search-form" onSubmit={(event) => { event.preventDefault(); setKeyword(keywordInput.trim()); setPage(1); }}><Field label="Search request logs"><input className="ui-input" type="search" maxLength={200} placeholder="Search prompts, rules, or reasons" value={keywordInput} onChange={(event) => setKeywordInput(event.target.value)} /></Field><Button variant="primary" icon="search" type="submit">Search</Button><Button onClick={() => setShowFilters((current) => !current)} aria-expanded={showFilters} aria-controls="request-log-filters">Filters{filterCount ? ` (${filterCount})` : ""}</Button>{hasFilters && <Button variant="ghost" onClick={clearFilters}>Reset</Button>}</form><div className="ui-tabs obs-status-tabs" aria-label="Request status">{STATUS_FILTERS.map((status) => <button key={status || "all"} type="button" className={statusFilter === status ? "is-active" : ""} aria-pressed={statusFilter === status} onClick={() => { setStatusFilter(status); setPage(1); }}>{status ? statusLabel(status) : "All statuses"}</button>)}</div>{showFilters && <div id="request-log-filters" className="obs-advanced-filters"><Field label="From date"><input className="ui-input" type="date" value={dateFrom} max={dateTo || undefined} onChange={(event) => { setDateFrom(event.target.value); setPage(1); }} /></Field><Field label="To date"><input className="ui-input" type="date" value={dateTo} min={dateFrom || undefined} onChange={(event) => { setDateTo(event.target.value); setPage(1); }} /></Field><Field label="Provider"><input className="ui-input" value={backendFilter} placeholder="e.g. groq or openai" onChange={(event) => { setBackendFilter(event.target.value); setPage(1); }} /></Field><Field label="CSV export window" hint="Exports organization traffic for this window."><select className="ui-input" value={exportDays} onChange={(event) => setExportDays(Number(event.target.value))}>{[7, 14, 30, 60, 90].map((days) => <option value={days} key={days}>Last {days} days</option>)}</select></Field></div>}</Panel>
    <Panel title="Gateway activity" description="Open a request to inspect its guardrail decisions and recorded metadata.">
      {loading ? <LoadingState label="Loading request logs" /> : !sorted.length ? <EmptyState icon={error ? "activity" : hasFilters ? "search" : "logs"} title={error ? "Request logs unavailable" : hasFilters ? "No requests match your filters" : "No requests recorded yet"} description={error ? "Refresh to retry loading this activity." : hasFilters ? "Try a broader search or reset your filters." : "Run a request in the Playground to create your first trace."} action={error ? <Button onClick={() => void load()}>Retry</Button> : hasFilters ? <Button onClick={clearFilters}>Reset filters</Button> : undefined} /> : <>
        <div className="obs-log-desktop"><TableWrap label="Request logs"><table className="obs-table obs-log-table"><thead><tr>{([["status", "Status"], ["prompt_preview", "Prompt"], ["fired_rule", "Rule"], ["backend", "Provider"], ["latency_ms", "Latency"], [null, "Tokens"], ["created_at", "Recorded"]] as [keyof RequestLogItem | null, string][]).map(([column, label]) => <th key={label} aria-sort={column && sortColumn === column ? sortDirection === "asc" ? "ascending" : "descending" : undefined}>{column ? <button type="button" className="obs-sort-button" onClick={() => toggleSort(column)}>{label}<span aria-hidden="true">{sortColumn === column ? sortDirection === "asc" ? "↑" : "↓" : "↕"}</span></button> : label}</th>)}<th><span className="sr-only">Inspect request</span></th></tr></thead><tbody>{sorted.map((log) => <Fragment key={log.id}><tr className={expandedLog === log.id ? "is-selected" : ""}><td><Badge tone={statusTone(log.status)}>{statusLabel(log.status)}</Badge></td><td className="obs-log-preview" title={log.prompt_preview}>{log.prompt_preview}</td><td className="obs-mono">{log.fired_rule || "—"}</td><td className="obs-mono">{log.backend}</td><td className="obs-nowrap">{log.latency_ms.toLocaleString()} ms</td><td>{((log.input_tokens || 0) + (log.output_tokens || 0)).toLocaleString()}</td><td className="obs-nowrap">{new Date(log.created_at).toLocaleString()}</td><td><Button variant="ghost" onClick={() => setExpandedLog((current) => current === log.id ? null : log.id)} aria-expanded={expandedLog === log.id} aria-controls={`request-details-${log.id}`}>{expandedLog === log.id ? "Close" : "Details"}</Button></td></tr>{expandedLog === log.id && <tr><td colSpan={8} className="obs-expanded-cell"><div id={`request-details-${log.id}`}><RequestDetails log={log} /></div></td></tr>}</Fragment>)}</tbody></table></TableWrap></div>
        <div className="obs-log-mobile">{sorted.map((log) => <article className="obs-log-card" key={log.id}><div><Badge tone={statusTone(log.status)}>{statusLabel(log.status)}</Badge><time>{new Date(log.created_at).toLocaleString()}</time></div><p>{log.prompt_preview}</p><div className="obs-log-card-footer"><span>{log.backend} · {log.latency_ms.toLocaleString()} ms · {((log.input_tokens || 0) + (log.output_tokens || 0)).toLocaleString()} tokens</span><Button variant="ghost" onClick={() => setSelectedLog(log)}>Details</Button></div>{log.fired_rule && <code>{log.fired_rule}</code>}</article>)}</div>
      </>}
      <nav className="obs-pagination" aria-label="Request log pages"><Button disabled={loading || page === 1} onClick={() => setPage((current) => current - 1)}>Previous</Button><span>Page {page} of {Math.max(1, Math.ceil(total / 25))}</span><Button disabled={loading || page * 25 >= total} onClick={() => setPage((current) => current + 1)}>Next</Button></nav>
    </Panel><p className="obs-footnote">CSV export contains organization traffic from the last {exportDays} days; table filters apply to the on-screen request list.</p>
    <Dialog open={!!selectedLog} onClose={() => setSelectedLog(null)} title="Request details" size="lg">{selectedLog && <RequestDetails log={selectedLog} />}</Dialog>
  </div>;
}
