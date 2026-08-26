import React, { useState, useEffect, useCallback } from "react";
import { api, getAuthToken } from "../utils/api";
import { s } from "../styles/theme";
import type { RequestLogItem, LogsResponse } from "../api-types";

type SortCol = "" | keyof RequestLogItem;

type FeedEvent = {
  id: string;
  org_id?: string | null;
  status?: string | null;
  fired_rule?: string | null;
  created_at?: string;
};

function feedSocketUrl(): string | null {
  if (import.meta.env.DEV) {
    return (import.meta.env.VITE_FEED_WS_URL || "ws://localhost:4000") + "/live-feed/websocket";
  }
  const scheme = location.protocol === "https:" ? "wss://" : "ws://";
  return scheme + location.host + "/live-feed/websocket";
}

function padEvent(ev: FeedEvent): RequestLogItem {
  return {
    id: ev.id,
    status: ev.status || "error",
    prompt_preview: "(new request)",
    full_prompt: null,
    model: "",
    backend: "live",
    latency_ms: 0,
    input_passed: true,
    output_passed: true,
    input_block_reason: null,
    output_block_reason: null,
    fired_rule: ev.fired_rule || null,
    input_tokens: 0,
    output_tokens: 0,
    created_at: ev.created_at || new Date().toISOString(),
    request_id: ev.id,
  };
}

function CopyBtn({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  function copy(e: React.MouseEvent) {
    e.stopPropagation();
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }).catch(() => {});
  }
  return (
    <button
      onClick={copy}
      title="Copy to clipboard"
      style={{
        border: "1px solid #dce7f0", borderRadius: 5, background: copied ? "#dcfce7" : "#f8fbff",
        color: copied ? "#059669" : "#607086", cursor: "pointer", fontSize: 11,
        padding: "2px 7px", fontWeight: 700, whiteSpace: "nowrap",
      }}
    >
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

const STATUS_FILTERS = ["", "delivered", "input_blocked", "output_blocked", "rate_limited", "error"];

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
  const [expandedLog, setExpandedLog] = useState<string | null>(null);
  const [sortCol, setSortCol] = useState<SortCol>("");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [feedLive, setFeedLive] = useState(false);

  const load = useCallback(() => {
    const params = new URLSearchParams({ page: String(page), page_size: "25" });
    if (statusFilter) params.set("status_filter", statusFilter);
    if (keyword) params.set("keyword", keyword);
    if (dateFrom) params.set("date_from", dateFrom);
    if (dateTo) params.set("date_to", dateTo);
    if (backendFilter) params.set("backend_filter", backendFilter);
    api<LogsResponse>("/analytics/logs?" + params)
      .then(d => { setLogs(d.items); setTotal(d.total); })
      .catch((e: Error) => setError(e.message));
  }, [page, statusFilter, keyword, dateFrom, dateTo, backendFilter]);

  useEffect(() => { load(); }, [load]);

  // Live feed: per-org Phoenix channel (Elixir relay of pg_notify). Any
  // failure degrades silently to the polling above.
  useEffect(() => {
    let ws: WebSocket | null = null;
    let heartbeat: number | undefined;
    let joinRef: string | undefined;
    let disposed = false;

    function teardown() {
      if (heartbeat) window.clearInterval(heartbeat);
      heartbeat = undefined;
      setFeedLive(false);
      try { ws?.close(); } catch { /* ignore */ }
      ws = null;
    }

    async function connectFeed() {
      if (disposed) return;
      const token = await getAuthToken();
      if (!token) return;
      const me = await api<{ org_id?: string | null }>("/auth/me").catch(() => null);
      if (!me?.org_id || disposed) return;
      const url = feedSocketUrl();
      if (!url) return;

      ws = new WebSocket(url);
      ws.onopen = () => {
        joinRef = String(Math.floor(Math.random() * 1_000_000));
        ws?.send(JSON.stringify([null, joinRef, "requests:org_" + me!.org_id, "phx_join", {}]));
        heartbeat = window.setInterval(() => {
          ws?.send(JSON.stringify([null, "1", "phoenix", "phx_heartbeat", {}]));
        }, 15_000);
      };
      ws.onmessage = (ev) => {
        try {
          const [, ref, , event, payload] = JSON.parse(ev.data) as unknown[];
          if (event === "phx_reply" && ref === joinRef && (payload as { status?: string })?.status === "ok") {
            setFeedLive(true);
          } else if (event === "new_request" && typeof payload === "object" && payload !== null) {
            const feedEvt = payload as FeedEvent;
            if (!feedEvt?.id) return;
            setLogs(prev => [padEvent(feedEvt), ...prev.filter(l => l.id !== feedEvt.id)]);
            setTotal(t => t + 1);
          }
        } catch { /* malformed frame — ignore */ }
      };
      ws.onerror = () => { try { ws?.close(); } catch { /* ignore */ } };
      ws.onclose = () => { if (!disposed) teardown(); };
    }

    connectFeed();
    return () => { disposed = true; teardown(); };
  }, []);

  function applySearch(e: React.FormEvent) {
    e.preventDefault();
    setKeyword(keywordInput);
    setPage(1);
  }

  function clearFilters() {
    setKeyword(""); setKeywordInput(""); setDateFrom(""); setDateTo("");
    setBackendFilter(""); setStatusFilter(""); setPage(1);
  }

  function toggleSort(col: keyof RequestLogItem) {
    if (sortCol === col) setSortDir(d => d === "asc" ? "desc" : "asc");
    else { setSortCol(col); setSortDir("asc"); }
  }

  const sorted: RequestLogItem[] = sortCol ? [...logs].sort((a, b) => {
    const av = a[sortCol] ?? ""; const bv = b[sortCol] ?? "";
    if (av < bv) return sortDir === "asc" ? -1 : 1;
    if (av > bv) return sortDir === "asc" ? 1 : -1;
    return 0;
  }) : logs;

  const SortArrow = ({ col }: { col: keyof RequestLogItem }) => sortCol === col ? (sortDir === "asc" ? " " : " ") : "";

  const [showFilters, setShowFilters] = useState(false);
  return (
    <div>
      <div style={{ ...s.heroPanel, display: "flex", justifyContent: "space-between", gap: 16, alignItems: "flex-start", flexWrap: "wrap" }}>
        <div style={{ minWidth: 260 }}>
          <div style={{ ...s.pageTitle, marginBottom: 8 }}>Request Logs</div>
          <div style={{ color: "#405166", fontSize: 15, lineHeight: 1.6, maxWidth: 560 }}>
            Filter recent gateway activity and inspect blocked reasons, latency, tokens, and provider behavior.
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, alignSelf: "flex-start" }}>
          {feedLive && (
            <span style={{ display: "inline-flex", alignItems: "center", gap: 6, background: "#ecfdf5", border: "1px solid #a7f3d0", color: "#065f46", padding: "6px 12px", borderRadius: 999, fontSize: 12, fontWeight: 800 }}>
              <span style={{ width: 7, height: 7, borderRadius: "50%", background: "#059669", boxShadow: "0 0 0 4px rgba(16,185,129,0.18)", display: "inline-block" }} />
              live
            </span>
          )}
          <span style={{ fontSize: 12, fontWeight: 800, color: "#607086", background: "#fff", border: "1px solid #dce7f0", padding: "6px 12px", borderRadius: 999 }}>{total.toLocaleString()} total</span>
        </div>
      </div>
      {error && <div style={s.alert("error")}>{error}</div>}

      {/* Primary search */}
      <form onSubmit={applySearch} style={{ display: "flex", gap: 10, marginBottom: 14, alignItems: "center", flexWrap: "wrap" }}>
        <div style={{ position: "relative", flex: "1 1 320px", minWidth: 260 }}>
          <span style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: "#8a9bb0", fontSize: 14 }}></span>
          <input
            style={{ ...s.input, paddingLeft: 36, marginBottom: 0, borderRadius: 12, boxShadow: "0 4px 14px rgba(15,118,110,0.06)", border: "1px solid #cfe4de" }}
            placeholder="Search prompts, rules, reasons…  ( to search)"
            value={keywordInput}
            onChange={e => setKeywordInput(e.target.value)}
          />
        </div>
        <button style={{ ...s.btn("primary"), borderRadius: 12, padding: "11px 18px" }} type="submit">Search</button>
        <button style={{ ...s.btn("secondary"), borderRadius: 12 }} type="button" onClick={clearFilters}>Clear</button>
        <button
          type="button"
          onClick={() => setShowFilters(v => !v)}
          style={{ ...s.btn(showFilters ? "primary" : "secondary"), borderRadius: 12, marginLeft: "auto" }}
        >
          {showFilters ? " Hide filters" : " Filters"}
          {(statusFilter || dateFrom || dateTo || backendFilter) && <span style={{ marginLeft: 6, background: "#0f766e", color: "#fff", padding: "1px 7px", borderRadius: 999, fontSize: 10 }}>{[statusFilter, dateFrom, dateTo, backendFilter].filter(Boolean).length}</span>}
        </button>
      </form>

      {/* Status segmented + advanced filters */}
      <div style={{ display: "flex", gap: 8, marginBottom: 14, flexWrap: "wrap", alignItems: "center" }}>
        <div style={{ display: "flex", background: "#eef3f8", borderRadius: 999, padding: 3, gap: 2, flexWrap: "wrap" }}>
          {STATUS_FILTERS.map(f => (
            <button
              key={f || "all"}
              onClick={() => { setStatusFilter(f); setPage(1); }}
              style={{
                padding: "6px 13px", borderRadius: 999, border: "none", cursor: "pointer", fontSize: 12, fontWeight: 800,
                background: statusFilter === f ? "#0f766e" : "transparent",
                color: statusFilter === f ? "#fff" : "#405166",
                boxShadow: statusFilter === f ? "0 4px 12px rgba(15,118,110,0.2)" : "none",
                transition: "all 0.16s",
              }}
            >
              {f || "all"}
            </button>
          ))}
        </div>
      </div>
      {showFilters && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 10, marginBottom: 16, background: "#f8fbff", border: "1px solid #dce7f0", borderRadius: 14, padding: 14 }}>
          <div>
            <label style={{ ...s.label, fontSize: 11 }}>From date</label>
            <input type="date" style={{ ...s.input, marginBottom: 0 }} value={dateFrom} onChange={e => { setDateFrom(e.target.value); setPage(1); }} />
          </div>
          <div>
            <label style={{ ...s.label, fontSize: 11 }}>To date</label>
            <input type="date" style={{ ...s.input, marginBottom: 0 }} value={dateTo} onChange={e => { setDateTo(e.target.value); setPage(1); }} />
          </div>
          <div>
            <label style={{ ...s.label, fontSize: 11 }}>Backend</label>
            <input style={{ ...s.input, marginBottom: 0 }} placeholder="e.g. groq / openai" value={backendFilter} onChange={e => { setBackendFilter(e.target.value); setPage(1); }} />
          </div>
          <div style={{ display: "flex", alignItems: "flex-end" }}>
            <button style={{ ...s.btn("secondary"), width: "100%", borderRadius: 10 }} type="button" onClick={clearFilters}>Reset filters</button>
          </div>
        </div>
      )}

      <div style={s.card}>
        <table style={s.table}>
          <thead>
            <tr>
              {([
                ["status", "Status"],
                ["prompt_preview", "Prompt"],
                ["fired_rule", "Rule Fired"],
                ["backend", "Backend"],
                ["latency_ms", "Latency"],
                [null, "Tokens"],
                ["created_at", "Time"],
                [null, ""],
              ] as [keyof RequestLogItem | null, string][]).map(([col, h]) => (
                <th key={h} style={{ ...s.th, cursor: col ? "pointer" : "default", userSelect: "none" }}
                  onClick={col ? () => toggleSort(col) : undefined}>
                  {h}{col && <SortArrow col={col} />}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map(log => (
              <React.Fragment key={log.id}>
                <tr
                  onClick={() => setExpandedLog(expandedLog === log.id ? null : log.id)}
                  style={{ cursor: "pointer", background: expandedLog === log.id ? "#f8fbff" : "transparent" }}
                >
                  <td style={s.td}><span style={s.badge(log.status)}>{log.status}</span></td>
                  <td style={{ ...s.td, maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                    title={log.input_block_reason || log.output_block_reason || ""}>
                    {log.prompt_preview}
                  </td>
                  <td style={s.td}>{log.fired_rule || "-"}</td>
                  <td style={s.td}>{log.backend}</td>
                  <td style={s.td}>{log.latency_ms}ms</td>
                  <td style={s.td}>{((log.input_tokens || 0) + (log.output_tokens || 0)).toLocaleString()}</td>
                  <td style={{ ...s.td, whiteSpace: "nowrap", fontSize: 12 }}>{new Date(log.created_at).toLocaleString()}</td>
                  <td style={s.td} onClick={e => e.stopPropagation()}>
                    <CopyBtn text={JSON.stringify({
                      id: log.id, status: log.status,
                      prompt: log.prompt_preview,
                      fired_rule: log.fired_rule,
                      reason: log.input_block_reason || log.output_block_reason,
                      backend: log.backend, latency_ms: log.latency_ms,
                      created_at: log.created_at,
                    }, null, 2)} />
                  </td>
                </tr>
                {expandedLog === log.id && (
                  <tr>
                    <td colSpan={8} style={{ padding: "16px 20px", background: "#f8fbff", borderBottom: "1px solid #e7eef6" }}>
                      <div style={{ fontSize: 12, fontWeight: 800, color: "#405166", marginBottom: 8, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <span>Full Prompt Details</span>
                        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                          <span style={{ fontWeight: "normal", color: "#64748b", fontFamily: "monospace" }}>ID: {log.id}</span>
                          <CopyBtn text={log.id} />
                        </div>
                      </div>
                      {log.input_block_reason && (
                        <div style={{ marginBottom: 8, padding: "8px 12px", background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 6, fontSize: 12, color: "#991b1b" }}>
                          Block reason: {log.input_block_reason}
                        </div>
                      )}
                      {log.output_block_reason && (
                        <div style={{ marginBottom: 8, padding: "8px 12px", background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 6, fontSize: 12, color: "#991b1b" }}>
                          Output block reason: {log.output_block_reason}
                        </div>
                      )}
                      {log.full_prompt ? (
                        <div style={{
                          background: "#fff", border: "1px solid #dce7f0", borderRadius: 8, padding: 12,
                          fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
                          fontSize: 12, color: "#102033", whiteSpace: "pre-wrap", wordBreak: "break-word",
                          lineHeight: 1.5, maxHeight: 400, overflowY: "auto",
                        }}>
                          {log.full_prompt}
                        </div>
                      ) : (
                        <div style={{
                          background: "#fffbeb", border: "1px solid #fde68a", borderRadius: 8, padding: 12,
                          fontSize: 12, color: "#92400e",
                        }}>
                          <strong>Full prompt logging was disabled.</strong>
                          <div style={{ marginTop: 4, color: "#b45309" }}>
                            Only the 120-character preview was retained. Enable "Full Prompt Logging" in Policy settings to capture full prompts.
                          </div>
                        </div>
                      )}
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>

        <div style={{ display: "flex", justifyContent: "center", gap: 8, marginTop: 16, alignItems: "center" }}>
          <button style={s.btn("secondary")} disabled={page === 1} onClick={() => setPage(p => p - 1)}>Previous</button>
          <span style={{ fontSize: 11, color: "#6b7280" }}>Page {page} of {Math.ceil(total / 25) || 1}</span>
          <button style={s.btn("secondary")} disabled={page * 25 >= total} onClick={() => setPage(p => p + 1)}>Next</button>
        </div>
      </div>
    </div>
  );
}
