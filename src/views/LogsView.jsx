import React, { useState, useEffect, useCallback, useRef } from "react";
import { api, getToken, setTokens, clearTokens, getGatewayKey, setGatewayKey, maskGatewayKey, gatewayKeyInputProps, formatApiError } from "../utils/api";
import { s } from "../styles/theme";
export default function LogsView() {
  const [logs, setLogs] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [filter, setFilter] = useState("");
  const [error, setError] = useState("");
  const [expandedLog, setExpandedLog] = useState(null);

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
              <React.Fragment key={log.id}>
                <tr onClick={() => setExpandedLog(expandedLog === log.id ? null : log.id)} style={{ cursor: "pointer", background: expandedLog === log.id ? "#f8fbff" : "transparent" }}>
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
                {expandedLog === log.id && (
                  <tr>
                    <td colSpan="7" style={{ padding: "16px 20px", background: "#f8fbff", borderBottom: "1px solid #e7eef6" }}>
                      <div style={{ fontSize: 12, fontWeight: 800, color: "#405166", marginBottom: 8, display: "flex", justifyContent: "space-between" }}>
                        <span>Full Prompt Details</span>
                        <span style={{ fontWeight: "normal", color: "#64748b" }}>ID: {log.id}</span>
                      </div>
                      {log.full_prompt ? (
                        <div style={{
                          background: "#ffffff", border: "1px solid #dce7f0", borderRadius: 8, padding: 12,
                          fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
                          fontSize: 12, color: "#102033", whiteSpace: "pre-wrap", wordBreak: "break-word",
                          lineHeight: 1.5, maxHeight: 400, overflowY: "auto"
                        }}>
                          {log.full_prompt}
                        </div>
                      ) : (
                        <div style={{
                          background: "#fffbeb", border: "1px solid #fde68a", borderRadius: 8, padding: 12,
                          fontSize: 12, color: "#92400e", display: "flex", gap: 8, alignItems: "flex-start"
                        }}>
                          <div style={{ fontSize: 16 }}>🔒</div>
                          <div>
                            <strong>Full prompt logging was disabled.</strong>
                            <div style={{ marginTop: 4, color: "#b45309" }}>
                              Only the 120-character preview was retained for privacy. To capture full prompts, enable "Full Prompt Logging" in the Policy settings.
                            </div>
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
