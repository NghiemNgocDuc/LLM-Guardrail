import React, { useState, useEffect, useCallback } from "react";
import { api } from "../utils/api";
import { s } from "../styles/theme";
import type { HealthDetailed, ServiceHealth } from "../api-types";

function StatusDot({ status }: { status: string }) {
  const color = status === "ok" ? "#10b981" : status === "not_configured" ? "#f59e0b" : "#ef4444";
  return (
    <span style={{
      display: "inline-block", width: 10, height: 10, borderRadius: "50%",
      background: color, marginRight: 8, flexShrink: 0,
    }} />
  );
}

function ServiceCard({ name, data }: { name: string; data?: ServiceHealth | null }) {
  if (!data) return null;
  const { status, latency_ms, detail, note, http_status } = data;
  const borderColor = status === "ok" ? "#10b981" : status === "not_configured" || status === "configured" ? "#f59e0b" : "#ef4444";
  const displayStatus = status === "configured" ? "configured" : status;
  return (
    <div style={{
      ...s.card, flex: 1, minWidth: 200, borderLeft: `4px solid ${borderColor}`,
      padding: "18px 20px",
    }}>
      <div style={{ display: "flex", alignItems: "center", marginBottom: 10 }}>
        <StatusDot status={status === "configured" ? "not_configured" : status} />
        <span style={{ fontWeight: 800, fontSize: 14, color: "#102033" }}>{name}</span>
        <span style={{ marginLeft: "auto", ...s.badge(status === "ok" ? "delivered" : status === "error" ? "error" : "rate_limited") }}>
          {displayStatus}
        </span>
      </div>
      {latency_ms !== undefined && (
        <div style={{ fontSize: 12, color: "#607086" }}>Latency: <strong>{latency_ms}ms</strong></div>
      )}
      {http_status !== undefined && (
        <div style={{ fontSize: 12, color: "#607086" }}>HTTP: {http_status}</div>
      )}
      {detail && (
        <div style={{ fontSize: 12, color: "#ef4444", marginTop: 6, wordBreak: "break-word" }}>{detail}</div>
      )}
      {note && (
        <div style={{ fontSize: 12, color: "#8a9bb0", marginTop: 6, fontStyle: "italic" }}>{note}</div>
      )}
    </div>
  );
}

export default function HealthView() {
  const [health, setHealth] = useState<HealthDetailed | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [lastChecked, setLastChecked] = useState<Date | null>(null);

  const check = useCallback(() => {
    setLoading(true); setError("");
    api<HealthDetailed>("/health/detailed")
      .then(d => { setHealth(d); setLastChecked(new Date()); })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    check();
    const interval = setInterval(check, 30_000);
    return () => clearInterval(interval);
  }, [check]);

  const overall = health?.overall;
  const overallColor = overall === "ok" ? "#10b981" : "#ef4444";

  return (
    <div>
      <div style={s.heroPanel}>
        <div style={{ ...s.pageTitle, marginBottom: 8 }}>System Health</div>
        <div style={{ color: "#405166", fontSize: 15, lineHeight: 1.6 }}>
          Live status of database, Redis, and LLM backend connectivity. Auto-refreshes every 30 seconds.
        </div>
      </div>

      {error && <div style={s.alert("error")}>{error}</div>}

      <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 20 }}>
        {health && (
          <div style={{
            padding: "8px 18px", borderRadius: 8, fontWeight: 800, fontSize: 14,
            background: overall === "ok" ? "#dcfce7" : "#fee2e2",
            color: overallColor,
          }}>
            Overall: {overall?.toUpperCase()}
          </div>
        )}
        {lastChecked && (
          <div style={{ fontSize: 12, color: "#8a9bb0" }}>
            Last checked: {lastChecked.toLocaleTimeString()}
          </div>
        )}
        <button style={{ ...s.btn("secondary"), marginLeft: "auto" }} onClick={check} disabled={loading}>
          {loading ? "Checking..." : "Refresh"}
        </button>
      </div>

      {health && (
        <>
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 20 }}>
            <ServiceCard name="Database (PostgreSQL)" data={health.database} />
            <ServiceCard name="Redis (Rate Limiting)" data={health.redis} />
          </div>

          <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 20 }}>
            {Object.entries(health.llm_backends || {}).map(([name, data]) => (
              <ServiceCard key={name} name={`LLM Backend: ${name}`} data={data} />
            ))}
          </div>

          <div style={s.card}>
            <div style={s.sectionTitle}>Configuration</div>
            <table style={s.table}>
              <tbody>
                <tr>
                  <td style={{ ...s.td, fontWeight: 700, width: "40%" }}>Default Backend</td>
                  <td style={s.td}>{health.default_backend}</td>
                </tr>
                <tr>
                  <td style={{ ...s.td, fontWeight: 700 }}>Environment</td>
                  <td style={s.td}><span style={s.badge(health.app_env === "production" ? "delivered" : "rate_limited")}>{health.app_env}</span></td>
                </tr>
                <tr>
                  <td style={{ ...s.td, fontWeight: 700 }}>Billing</td>
                  <td style={s.td}><span style={s.badge(health.billing_enabled ? "delivered" : "error")}>{health.billing_enabled ? "enabled" : "disabled"}</span></td>
                </tr>
              </tbody>
            </table>
          </div>
        </>
      )}

      {loading && !health && (
        <div style={{ color: "#8a9bb0", padding: 24, textAlign: "center" }}>Checking system status...</div>
      )}
    </div>
  );
}
