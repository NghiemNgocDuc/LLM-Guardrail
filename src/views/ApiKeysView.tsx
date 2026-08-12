import React, { useState, useEffect, useCallback, useRef } from "react";
import { api, maskGatewayKey } from "../utils/api";
import { trackEvent } from "../utils/analytics";
import { s } from "../styles/theme";
import type { components } from "../api-types";

type APIKeyOut = components["schemas"]["APIKeyOut"];

interface ScopeOption { label: string; color: string; bg: string; border: string }

const DEFAULT_SCOPE_OPTIONS: ScopeOption[] = [
  { label: "chat",          color: "#6366f1", bg: "#eef2ff",  border: "#c7d2fe" },
  { label: "policy:read",   color: "#0f766e", bg: "#ccfbf1",  border: "#99f6e4" },
  { label: "policy:write",  color: "#0f766e", bg: "#ccfbf1",  border: "#99f6e4" },
  { label: "logs:read",     color: "#1d4ed8", bg: "#dbeafe",  border: "#bfdbfe" },
  { label: "analytics",     color: "#7c3aed", bg: "#f5f3ff",  border: "#ddd6fe" },
  { label: "skills:read",   color: "#b45309", bg: "#fef9c3",  border: "#fde68a" },
  { label: "skills:write",  color: "#b45309", bg: "#fef9c3",  border: "#fde68a" },
  { label: "admin",         color: "#be123c", bg: "#fff1f2",  border: "#fecdd3" },
];

function scopeStyle(label: string): React.CSSProperties {
  const found = DEFAULT_SCOPE_OPTIONS.find((o) => o.label === label);
  if (found) return { color: found.color, background: found.bg, border: `1px solid ${found.border}` };
  return { color: "#405166", background: "#eef3f8", border: "1px solid #dce7f0" };
}

/** Per-key row with its own scope state */
function ApiKeyRow({ k, toggling, onToggle, onRevoke }: {
  k: APIKeyOut;
  toggling: string | null;
  onToggle: () => void;
  onRevoke: () => void;
}) {
  const [scopes, setScopes] = useState<string[]>(k.is_active ? ["chat", "logs:read"] : []);
  const [addingScope, setAddingScope] = useState(false);
  const [scopeInput, setScopeInput] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  function removeScope(sc: string) { setScopes((prev) => prev.filter((x) => x !== sc)); }

  function addScope(val: string) {
    const v = val.trim();
    if (!v || scopes.includes(v)) { setScopeInput(""); setAddingScope(false); return; }
    setScopes((prev) => [...prev, v]);
    setScopeInput("");
    setAddingScope(false);
  }

  function openAdder() {
    setAddingScope(true);
    setTimeout(() => inputRef.current?.focus(), 40);
  }

  return (
    <tr>
      <td style={s.td}>{k.name}</td>
      <td style={{ ...s.td, fontFamily: "monospace", color: "#0f766e", fontWeight: 800 }}>
        {maskGatewayKey(k.key_prefix + "0".repeat(24))}
      </td>
      <td style={s.td}>{k.total_requests.toLocaleString()}</td>
      <td style={s.td}>{k.total_blocked.toLocaleString()}</td>
      <td style={s.td}>{new Date(k.created_at).toLocaleDateString()}</td>

      {/* ── Enabled / Scopes column ── */}
      <td style={{ ...s.td, minWidth: 260 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>

          {/* On/Off toggle */}
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <button
              style={s.toggle(k.is_active)}
              disabled={toggling === k.id}
              onClick={onToggle}
              title={k.is_active ? "Disable key" : "Enable key"}
              aria-label={k.is_active ? "Disable key" : "Enable key"}
            >
              <div style={s.toggleDot(k.is_active)} />
            </button>
            <span style={{ fontSize: 11, color: k.is_active ? "#0f766e" : "#9aabba", fontWeight: 750 }}>
              {k.is_active ? "Active" : "Disabled"}
            </span>
          </div>

          {/* Active scope chips + + button */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 5, alignItems: "center" }}>
            {scopes.map((sc) => (
              <span
                key={sc}
                style={{
                  ...scopeStyle(sc),
                  display: "inline-flex", alignItems: "center", gap: 4,
                  padding: "3px 7px", borderRadius: 999, fontSize: 11, fontWeight: 700,
                  fontFamily: "ui-monospace, monospace",
                }}
              >
                {sc}
                <button
                  onClick={() => removeScope(sc)}
                  title={`Remove ${sc}`}
                  style={{
                    background: "none", border: "none", cursor: "pointer", padding: 0,
                    lineHeight: 1, fontSize: 12, color: "inherit", opacity: 0.6,
                    display: "inline-flex", alignItems: "center",
                  }}
                  aria-label={`Remove scope ${sc}`}
                >×</button>
              </span>
            ))}

            {addingScope ? (
              <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
                <input
                  ref={inputRef}
                  value={scopeInput}
                  onChange={(e) => setScopeInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") addScope(scopeInput);
                    if (e.key === "Escape") { setScopeInput(""); setAddingScope(false); }
                  }}
                  placeholder="scope name…"
                  style={{
                    width: 110, padding: "3px 7px", fontSize: 11,
                    fontFamily: "ui-monospace, monospace",
                    border: "1px solid #6366f1", borderRadius: 999, outline: "none",
                    background: "#eef2ff", color: "#4338ca",
                  }}
                />
                <button
                  onClick={() => addScope(scopeInput)}
                  style={{ ...s.btn("primary"), padding: "3px 9px", fontSize: 11, borderRadius: 999 }}
                >↵</button>
                <button
                  onClick={() => { setScopeInput(""); setAddingScope(false); }}
                  style={{ ...s.btn("secondary"), padding: "3px 7px", fontSize: 11, borderRadius: 999 }}
                >✕</button>
              </div>
            ) : (
              <button
                onClick={openAdder}
                title="Add custom scope"
                aria-label="Add custom scope"
                style={{
                  width: 22, height: 22, borderRadius: "50%", border: "1.5px dashed #6366f1",
                  background: "#eef2ff", color: "#6366f1", fontSize: 15, fontWeight: 800,
                  display: "inline-flex", alignItems: "center", justifyContent: "center",
                  cursor: "pointer", lineHeight: 1, padding: 0, flexShrink: 0,
                }}
              >+</button>
            )}
          </div>

          {/* Quick-add preset scopes */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
            {DEFAULT_SCOPE_OPTIONS.filter((o) => !scopes.includes(o.label)).map((o) => (
              <button
                key={o.label}
                onClick={() => setScopes((prev) => [...prev, o.label])}
                title={`Add ${o.label}`}
                style={{
                  ...scopeStyle(o.label),
                  display: "inline-flex", alignItems: "center", gap: 3,
                  padding: "2px 7px", borderRadius: 999, fontSize: 10, fontWeight: 700,
                  fontFamily: "ui-monospace, monospace", cursor: "pointer",
                  opacity: 0.6, transition: "opacity 0.15s",
                }}
                onMouseEnter={(e) => { e.currentTarget.style.opacity = "1"; }}
                onMouseLeave={(e) => { e.currentTarget.style.opacity = "0.6"; }}
              >+ {o.label}</button>
            ))}
          </div>
        </div>
      </td>

      {/* Status + Revoke */}
      <td style={s.td}>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span style={s.badge(k.is_active ? "delivered" : "error")}>
            {k.is_active ? "active" : "disabled"}
          </span>
          {k.is_active && (
            <button
              style={{ ...s.btn("danger"), padding: "5px 10px", fontSize: 11 }}
              onClick={onRevoke}
            >Revoke</button>
          )}
        </div>
      </td>
    </tr>
  );
}

// API KEYS VIEW
export default function ApiKeysView() {
  const [keys, setKeys] = useState<APIKeyOut[]>([]);
  const [newName, setNewName] = useState("");
  const [rawKey, setRawKey] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [toggling, setToggling] = useState<string | null>(null);

  const load = useCallback(() => {
    api<APIKeyOut[]>("/api-keys").then(setKeys).catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => { load(); }, [load]);

  async function create() {
    if (!newName.trim()) return;
    setError(""); setLoading(true);
    try {
      const data = await api<components["schemas"]["APIKeyCreated"]>("/api-keys", { method: "POST", body: { name: newName.trim() } });
      trackEvent("api_key_created", { name: newName.trim() });
      setRawKey(data.raw_key);
      setNewName("");
      load();
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setLoading(false); }
  }

  async function revoke(id: string) {
    if (!confirm("Revoke this key? This cannot be undone.")) return;
    try {
      await api("/api-keys/" + id, { method: "DELETE" });
      trackEvent("api_key_revoked");
      load();
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  }

  async function toggleKey(k: APIKeyOut) {
    setToggling(k.id);
    setError("");
    try {
      await api("/api-keys/" + k.id, { method: "PATCH", body: { is_active: !k.is_active } });
      load();
    } catch (e) {
      setError("Toggle not supported by server yet — use Revoke to permanently remove.");
    } finally {
      setToggling(null);
    }
  }

  return (
    <div>
      <div style={s.heroPanel}>
        <div style={{ ...s.pageTitle, marginBottom: 8 }}>Gateway API Keys</div>
        <div style={{ color: "#405166", fontSize: 15, lineHeight: 1.6 }}>
          Create scoped keys for applications that need guardrail protection before calling the LLM provider.
          Toggle keys on/off without revoking, and manage per-key permission scopes inline.
        </div>
      </div>

      {error && <div style={s.alert("error")}>{error}</div>}
      {keys.length === 0 && !rawKey && (
        <div style={s.alert("info")}>
          Create a gateway API key before using Chat Tester or integrating an app.
        </div>
      )}
      {rawKey && (
        <div style={s.alert("success")}>
          <div style={{ marginBottom: 6 }}>
            Key created and saved for Chat Tester. Copy it once — it will not be shown again.
          </div>
          <code style={{ fontSize: 12, wordBreak: "break-all", color: "#067647", fontWeight: 800 }}>
            {maskGatewayKey(rawKey)}
          </code>
          <div style={{ marginTop: 8 }}>
            <button style={s.btn("secondary")} onClick={() => { navigator.clipboard.writeText(rawKey); }}>
              Copy key
            </button>
            <button style={{ ...s.btn("secondary"), marginLeft: 8 }} onClick={() => setRawKey("")}>
              Dismiss
            </button>
          </div>
        </div>
      )}

      <div style={{ ...s.card, marginBottom: 24 }}>
        <div style={s.sectionTitle}>Create new key</div>
        <div style={{ display: "flex", gap: 12 }}>
          <input style={{ ...s.input, flex: 1 }} placeholder="Key name (e.g. production)"
            value={newName} onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && create()} />
          <button style={s.btn("primary")} onClick={create} disabled={loading}>
            {loading ? "Creating..." : "Create"}
          </button>
        </div>
      </div>

      <div style={s.card}>
        <div style={{ overflowX: "auto" }}>
          <table style={{ ...s.table, minWidth: 920 }}>
            <thead>
              <tr>
                {["Name","Prefix","Requests","Blocked","Created","Enabled / Scopes","Status"].map(h => (
                  <th key={h} style={s.th}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {keys.map(k => (
                <ApiKeyRow
                  key={k.id}
                  k={k}
                  toggling={toggling}
                  onToggle={() => toggleKey(k)}
                  onRevoke={() => revoke(k.id)}
                />
              ))}
              {keys.length === 0 && (
                <tr><td colSpan={7} style={{ ...s.td, textAlign: "center", color: "#7b8a9d" }}>
                  No keys yet
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// LOGS VIEW
