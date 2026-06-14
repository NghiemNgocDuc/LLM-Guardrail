import React, { useState, useEffect, useCallback } from "react";
import { api, maskGatewayKey } from "../utils/api";
import { s } from "../styles/theme";

export default function AdminView() {
  const [stats, setStats] = useState([]);
  const [keys, setKeys] = useState([]);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [selected, setSelected] = useState(new Set());
  const [sortCol, setSortCol] = useState("");
  const [sortDir, setSortDir] = useState("asc");
  const [bulking, setBulking] = useState(false);

  const load = useCallback(() => {
    setSelected(new Set());
    Promise.all([api("/admin/users/stats"), api("/admin/api-keys")])
      .then(([u, k]) => { setStats(u); setKeys(k); })
      .catch(e => setError(e.message));
  }, []);

  useEffect(() => { load(); }, [load]);

  function toggleSort(col) {
    if (sortCol === col) setSortDir(d => d === "asc" ? "desc" : "asc");
    else { setSortCol(col); setSortDir("asc"); }
  }

  const sorted = sortCol ? [...stats].sort((a, b) => {
    const av = a[sortCol] ?? ""; const bv = b[sortCol] ?? "";
    if (av < bv) return sortDir === "asc" ? -1 : 1;
    if (av > bv) return sortDir === "asc" ? 1 : -1;
    return 0;
  }) : stats;

  const SortArrow = ({ col }) => sortCol === col ? (sortDir === "asc" ? " ↑" : " ↓") : "";

  function toggleSelect(id) {
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

  async function bulkAction(action) {
    if (selected.size === 0) return;
    const verb = { enable: "enable", disable: "disable", remove: "remove from org" }[action];
    if (!confirm(`${verb} ${selected.size} selected user(s)?`)) return;
    setBulking(true); setError(""); setSuccess("");
    try {
      await api("/admin/users/bulk", { method: "POST", body: { action, user_ids: [...selected] } });
      setSuccess(`${selected.size} user(s) updated.`);
      load();
    } catch (e) { setError(e.message); }
    finally { setBulking(false); }
  }

  async function patchUser(userId, body) {
    setError(""); setSuccess("");
    try {
      await api("/admin/users/" + userId, { method: "PATCH", body });
      setSuccess("User updated.");
      load();
    } catch (e) { setError(e.message); }
  }

  async function removeUser(u) {
    if (!confirm(`Remove ${u.email} from the organisation?`)) return;
    setError(""); setSuccess("");
    try {
      await api("/admin/users/" + u.id, { method: "DELETE" });
      setSuccess(`${u.email} removed from org.`);
      load();
    } catch (e) { setError(e.message); }
  }

  async function revokeKey(id) {
    if (!confirm("Revoke this organisation key?")) return;
    setError(""); setSuccess("");
    try {
      await api("/admin/api-keys/" + id, { method: "DELETE" });
      setSuccess("Key revoked.");
      load();
    } catch (e) { setError(e.message); }
  }

  const fmt = n => Number(n).toLocaleString();

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
              {[
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
              ].map(([col, h]) => (
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

      {/* API Keys */}
      <div style={{ ...s.card, overflowX: "auto" }}>
        <div style={s.sectionTitle}>Organisation API Keys</div>
        <table style={s.table}>
          <thead>
            <tr>{["Name", "Prefix", "Requests", "Blocked", "Status", ""].map(h => <th key={h} style={s.th}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {keys.map(k => (
              <tr key={k.id}>
                <td style={s.td}>{k.name}</td>
                <td style={{ ...s.td, fontFamily: "monospace", color: "#0f766e", fontWeight: 800 }}>
                  {maskGatewayKey(k.key_prefix + "0".repeat(24))}
                </td>
                <td style={s.td}>{fmt(k.total_requests)}</td>
                <td style={s.td}>{fmt(k.total_blocked)}</td>
                <td style={s.td}><span style={s.badge(k.is_active ? "delivered" : "error")}>{k.is_active ? "active" : "revoked"}</span></td>
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
