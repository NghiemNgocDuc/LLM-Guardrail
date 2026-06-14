import React, { useState, useEffect, useCallback } from "react";
import { api } from "../utils/api";
import { s } from "../styles/theme";

function CopyBtn({ text }) {
  const [copied, setCopied] = useState(false);
  function copy(e) {
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
  const [logs, setLogs] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState("");
  const [keyword, setKeyword] = useState("");
  const [keywordInput, setKeywordInput] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [backendFilter, setBackendFilter] = useState("");
  const [error, setError] = useState("");
  const [expandedLog, setExpandedLog] = useState(null);
  const [sortCol, setSortCol] = useState("");
  const [sortDir, setSortDir] = useState("desc");

  const load = useCallback(() => {
    const params = new URLSearchParams({ page, page_size: 25 });
    if (statusFilter) params.set("status_filter", statusFilter);
    if (keyword) params.set("keyword", keyword);
    if (dateFrom) params.set("date_from", dateFrom);
    if (dateTo) params.set("date_to", dateTo);
    if (backendFilter) params.set("backend_filter", backendFilter);
    api("/analytics/logs?" + params)
      .then(d => { setLogs(d.items); setTotal(d.total); })
      .catch(e => setError(e.message));
  }, [page, statusFilter, keyword, dateFrom, dateTo, backendFilter]);

  useEffect(() => { load(); }, [load]);

  function applySearch(e) {
    e.preventDefault();
    setKeyword(keywordInput);
    setPage(1);
  }

  function clearFilters() {
    setKeyword(""); setKeywordInput(""); setDateFrom(""); setDateTo("");
    setBackendFilter(""); setStatusFilter(""); setPage(1);
  }

  function toggleSort(col) {
    if (sortCol === col) setSortDir(d => d === "asc" ? "desc" : "asc");
    else { setSortCol(col); setSortDir("asc"); }
  }

  const sorted = sortCol ? [...logs].sort((a, b) => {
    const av = a[sortCol] ?? ""; const bv = b[sortCol] ?? "";
    if (av < bv) return sortDir === "asc" ? -1 : 1;
    if (av > bv) return sortDir === "asc" ? 1 : -1;
    return 0;
  }) : logs;

  const SortArrow = ({ col }) => sortCol === col ? (sortDir === "asc" ? " ↑" : " ↓") : "";

  return (
    <div>
      <div style={s.heroPanel}>
        <div style={{ ...s.pageTitle, marginBottom: 8 }}>Request Logs</div>
        <div style={{ color: "#405166", fontSize: 15, lineHeight: 1.6 }}>
          Filter recent gateway activity and inspect blocked reasons, latency, tokens, and provider behavior.
        </div>
      </div>
      {error && <div style={s.alert("error")}>{error}</div>}

      {/* Search bar */}
      <form onSubmit={applySearch} style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
        <input
          style={{ ...s.input, flex: 2, minWidth: 200, marginBottom: 0 }}
          placeholder="Search prompts, rules, reasons..."
          value={keywordInput}
          onChange={e => setKeywordInput(e.target.value)}
        />
        <input type="date" style={{ ...s.input, flex: 1, minWidth: 140, marginBottom: 0 }}
          value={dateFrom} onChange={e => { setDateFrom(e.target.value); setPage(1); }} title="From date" />
        <input type="date" style={{ ...s.input, flex: 1, minWidth: 140, marginBottom: 0 }}
          value={dateTo} onChange={e => { setDateTo(e.target.value); setPage(1); }} title="To date" />
        <input
          style={{ ...s.input, flex: 1, minWidth: 120, marginBottom: 0 }}
          placeholder="Backend filter"
          value={backendFilter}
          onChange={e => { setBackendFilter(e.target.value); setPage(1); }}
        />
        <button style={s.btn("primary")} type="submit">Search</button>
        <button style={s.btn("secondary")} type="button" onClick={clearFilters}>Clear</button>
      </form>

      {/* Status chips */}
      <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
        {STATUS_FILTERS.map(f => (
          <div key={f} style={s.chip(statusFilter === f)} onClick={() => { setStatusFilter(f); setPage(1); }}>
            {f || "all"}
          </div>
        ))}
        <div style={{ marginLeft: "auto", fontSize: 12, color: "#607086", fontWeight: 750, alignSelf: "center" }}>
          {total} total
        </div>
      </div>

      <div style={s.card}>
        <table style={s.table}>
          <thead>
            <tr>
              {[
                ["status", "Status"],
                ["prompt_preview", "Prompt"],
                ["fired_rule", "Rule Fired"],
                ["backend", "Backend"],
                ["latency_ms", "Latency"],
                [null, "Tokens"],
                ["created_at", "Time"],
                [null, ""],
              ].map(([col, h]) => (
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
