import React, { useState, useEffect, useCallback } from "react";
import { api, maskGatewayKey } from "../utils/api";
import { s } from "../styles/theme";
import type { components } from "../api-types";

type AdminUserStats = components["schemas"]["AdminUserStats"];
type APIKeyOut = components["schemas"]["APIKeyOut"];
type SortCol = "" | keyof AdminUserStats;

type BanInfo = { type: string; id: string; retry_after: number; reason: string };

export default function AdminView() {
  const [stats, setStats] = useState<AdminUserStats[]>([]);
  const [keys, setKeys] = useState<APIKeyOut[]>([]);
  const [bans, setBans] = useState<BanInfo[]>([]);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [sortCol, setSortCol] = useState<SortCol>("");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [bulking, setBulking] = useState(false);

  const load = useCallback(() => {
    setSelected(new Set());
    Promise.all([api<AdminUserStats[]>("/admin/users/stats"), api<APIKeyOut[]>("/admin/api-keys"), api<BanInfo[]>("/admin/bans").catch(() => [] as BanInfo[])])
      .then(([u, k, b]) => { setStats(u); setKeys(k); setBans(b as BanInfo[]); })
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => { load(); }, [load]);

  function toggleSort(col: keyof AdminUserStats) {
    if (sortCol === col) setSortDir(d => d === "asc" ? "desc" : "asc");
    else { setSortCol(col); setSortDir("asc"); }
  }

  const sorted: AdminUserStats[] = sortCol ? [...stats].sort((a, b) => {
    const av = a[sortCol] ?? ""; const bv = b[sortCol] ?? "";
    if (av < bv) return sortDir === "asc" ? -1 : 1;
    if (av > bv) return sortDir === "asc" ? 1 : -1;
    return 0;
  }) : stats;

  const SortArrow = ({ col }: { col: keyof AdminUserStats }) => sortCol === col ? (sortDir === "asc" ? " " : " ") : "";

  function toggleSelect(id: string) {
    setSelected(s => {
      const next = new Set(s);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  function toggleAll() {
    if (selected.size === stats.length) setSelected(new Set());
    else setSelected(new Set(stats.map(u => u.id)));
  }

  async function bulkAction(action: "enable" | "disable" | "remove") {
    if (selected.size === 0) return;
    const verb: Record<string, string> = { enable: "enable", disable: "disable", remove: "remove from org" };
    if (!confirm(`${verb[action]} ${selected.size} selected user(s)?`)) return;
    setBulking(true); setError(""); setSuccess("");
    try {
      await api("/admin/users/bulk", { method: "POST", body: { action, user_ids: [...selected] } });
      setSuccess(`${selected.size} user(s) updated.`);
      load();
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBulking(false); }
  }

  async function patchUser(userId: string, body: Record<string, unknown>) {
    setError(""); setSuccess("");
    try {
      await api("/admin/users/" + userId, { method: "PATCH", body });
      setSuccess("User updated.");
      load();
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  }

  async function removeUser(u: AdminUserStats) {
    if (!confirm(`Remove ${u.email} from the organisation?`)) return;
    setError(""); setSuccess("");
    try {
      await api("/admin/users/" + u.id, { method: "DELETE" });
      setSuccess(`${u.email} removed from org.`);
      load();
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  }

  async function revokeKey(id: string) {
    if (!confirm("Revoke this organisation key?")) return;
    setError(""); setSuccess("");
    try {
      await api("/admin/api-keys/" + id, { method: "DELETE" });
      setSuccess("Key revoked.");
      load();
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  }

  async function unban(b: BanInfo) {
    if (!confirm(`Lift temporary ban for ${b.type} ${b.id.slice(0,8)}… (${b.reason})?`)) return;
    setError(""); setSuccess("");
    try {
      await api("/admin/bans/unban", { method: "POST", body: b.type === "api_key" ? { api_key_id: b.id } : { user_id: b.id } });
      setSuccess("Ban lifted.");
      load();
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  }

  const fmt = (n: number) => Number(n).toLocaleString();

  return (
    <div>
      <div style={s.heroPanel}>
        <div style={{ ...s.pageTitle, marginBottom: 8 }}>Admin Controls</div>
        <div style={{ color: "#405166", fontSize: 15, lineHeight: 1.6 }}>
          Manage organisation users, view usage, and revoke keys.
        </div>
      </div>
      {error && <div style={s.alert("error")}>{error}</div>}
      {success && <div style={s.alert("success")}>{success}</div>}

      {/* Users + usage */}
      <div style={{ ...s.card, marginBottom: 24, overflowX: "auto" }}>
        <div style={{ display: "flex", alignItems: "center", marginBottom: 12, gap: 10, flexWrap: "wrap" }}>
          <div style={s.sectionTitle}>Organisation Members</div>
          {selected.size > 0 && (
            <div style={{ display: "flex", gap: 8, marginLeft: "auto" }}>
              <span style={{ fontSize: 12, color: "#607086", alignSelf: "center" }}>{selected.size} selected</span>
              <button style={{ ...s.btn("secondary"), fontSize: 12 }} onClick={() => bulkAction("enable")} disabled={bulking}>Enable</button>
              <button style={{ ...s.btn("secondary"), fontSize: 12 }} onClick={() => bulkAction("disable")} disabled={bulking}>Disable</button>
              <button style={{ ...s.btn("danger"), fontSize: 12 }} onClick={() => bulkAction("remove")} disabled={bulking}>Remove</button>
            </div>
          )}
        </div>
        <table style={s.table}>
          <thead>
            <tr>
              <th style={{ ...s.th, width: 36 }}>
                <input type="checkbox"
                  checked={stats.length > 0 && selected.size === stats.length}
                  onChange={toggleAll}
                  style={{ cursor: "pointer" }}
                />
              </th>
              {([
                ["email", "Email"],
                ["full_name", "Name"],
                [null, "Role"],
                [null, "Status"],
                ["last_login", "Last Login"],
                ["tokens_used", "Tokens Used"],
                ["tokens_balance", "Balance"],
                ["total_requests", "Requests"],
                ["total_blocked", "Blocked"],
                [null, ""],
              ] as [keyof AdminUserStats | null, string][]).map(([col, h]) => (
                <th key={h} style={{ ...s.th, cursor: col ? "pointer" : "default", userSelect: "none" }}
                  onClick={col ? () => toggleSort(col) : undefined}>
                  {h}{col && <SortArrow col={col} />}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map(u => (
              <tr key={u.id} style={{ background: selected.has(u.id) ? "#f0fdf4" : "transparent" }}>
                <td style={s.td}>
                  <input type="checkbox" checked={selected.has(u.id)} onChange={() => toggleSelect(u.id)} style={{ cursor: "pointer" }} />
                </td>
                <td style={s.td}>{u.email}</td>
                <td style={s.td}>{u.full_name}</td>
                <td style={s.td}><span style={s.badge(u.is_admin ? "rate_limited" : "delivered")}>{u.is_admin ? "admin" : "member"}</span></td>
                <td style={s.td}><span style={s.badge(u.is_active ? "delivered" : "error")}>{u.is_active ? "active" : "disabled"}</span></td>
                <td style={{ ...s.td, whiteSpace: "nowrap", fontSize: 12 }}>
                  {u.last_login ? new Date(u.last_login).toLocaleString() : "Never"}
                </td>
                <td style={s.td}>{fmt(u.tokens_used)}</td>
                <td style={s.td}>{fmt(u.tokens_balance)}</td>
                <td style={s.td}>{fmt(u.total_requests)}</td>
                <td style={s.td}>{fmt(u.total_blocked)}</td>
                <td style={{ ...s.td, whiteSpace: "nowrap" }}>
                  <button style={{ ...s.btn("secondary"), fontSize: 12, padding: "5px 10px" }}
                    onClick={() => patchUser(u.id, { is_admin: !u.is_admin })}>
                    {u.is_admin ? "Demote" : "Promote"}
                  </button>
                  <button style={{ ...s.btn(u.is_active ? "danger" : "secondary"), fontSize: 12, padding: "5px 10px", marginLeft: 6 }}
                    onClick={() => patchUser(u.id, { is_active: !u.is_active })}>
                    {u.is_active ? "Disable" : "Enable"}
                  </button>
                  <button style={{ ...s.btn("danger"), fontSize: 12, padding: "5px 10px", marginLeft: 6 }}
                    onClick={() => removeUser(u)}>
                    Remove
                  </button>
                </td>
              </tr>
            ))}
            {stats.length === 0 && (
              <tr><td colSpan={11} style={s.td}>No users found</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Active exploit bans */}
      <div style={{ ...s.card, overflowX: "auto", borderColor: bans.length ? "#fecdd3" : undefined, background: bans.length ? "#fffbfb" : undefined }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
          <div style={s.sectionTitle}>Active Auto-Bans</div>
          {bans.length > 0 ? <span style={{ ...s.badge("error"), fontSize: 11 }}>{bans.length} active</span> : <span style={{ ...s.badge("delivered") }}>clean</span>}
          <button style={{ ...s.btn("secondary"), marginLeft: "auto", fontSize: 12, padding: "6px 12px" }} onClick={load}>Refresh</button>
        </div>
        <div style={{ fontSize: 12, color: "#7b8a9d", marginBottom: 12, lineHeight: 1.5 }}>
          Auto-ban triggers on <b>rpm burst &gt;{120}/min</b>, <b>token burn &gt;50k/5m</b>, <b>IP diversity &gt;=5/10m</b>, <b>blocked-ratio &gt;=80% /20 reqs</b> or <b>dedup abuse &gt;=6x/5m</b>. First ban 15 min, doubles to 24h cap. User + key both banned.
        </div>
        {bans.length === 0 ? (
          <div style={{ padding: 12, background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 8, fontSize: 13, color: "#065f46" }}>No active bans — no exploit activity detected.</div>
        ) : (
          <table style={s.table}>
            <thead><tr>{["Type", "ID", "Reason", "Retry after", ""].map(h => <th key={h} style={s.th}>{h}</th>)}</tr></thead>
            <tbody>
              {bans.map(b => (
                <tr key={b.type + b.id}>
                  <td style={s.td}><span style={s.badge(b.type === "api_key" ? "input_blocked" : "rate_limited")}>{b.type}</span></td>
                  <td style={{ ...s.td, fontFamily: "monospace", fontSize: 12 }}>{b.id.slice(0, 12)}…</td>
                  <td style={s.td}><code style={{ fontSize: 11, background: "#fff7ed", padding: "2px 6px", borderRadius: 4, border: "1px solid #fed7aa" }}>{b.reason}</code></td>
                  <td style={s.td}>{Math.floor(b.retry_after / 60)}m {b.retry_after % 60}s</td>
                  <td style={s.td}><button style={s.btn("secondary")} onClick={() => unban(b)}>Lift ban</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* API Keys */}
      <div style={{ ...s.card, overflowX: "auto" }}>
        <div style={s.sectionTitle}>Organisation API Keys</div>
        <table style={s.table}>
          <thead>
            <tr>{["Name", "Prefix", "Requests", "Blocked", "Status", ""].map(h => <th key={h} style={s.th}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {keys.map(k => (
              <tr key={k.id} style={{ opacity: bans.some(b => b.id === k.id) ? 0.6 : 1, background: bans.some(b => b.id === k.id) ? "#fff1f2" : undefined }}>
                <td style={s.td}>{k.name}</td>
                <td style={{ ...s.td, fontFamily: "monospace", color: "#0f766e", fontWeight: 800 }}>
                  {maskGatewayKey(k.key_prefix + "0".repeat(24))}
                </td>
                <td style={s.td}>{fmt(k.total_requests)}</td>
                <td style={s.td}>{fmt(k.total_blocked)}</td>
                <td style={s.td}>
                  {bans.some(b => b.id === k.id) ? <span style={s.badge("error")}>banned</span> : <span style={s.badge(k.is_active ? "delivered" : "error")}>{k.is_active ? "active" : "revoked"}</span>}
                </td>
                <td style={s.td}>{k.is_active && <button style={s.btn("danger")} onClick={() => revokeKey(k.id)}>Revoke</button>}</td>
              </tr>
            ))}
            {keys.length === 0 && (
              <tr><td colSpan={6} style={s.td}>No organisation keys found</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
