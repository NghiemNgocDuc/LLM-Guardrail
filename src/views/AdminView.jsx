import React, { useState, useEffect, useCallback } from "react";
import { api, maskGatewayKey } from "../utils/api";
import { s } from "../styles/theme";

export default function AdminView() {
  const [stats, setStats] = useState([]);
  const [keys, setKeys] = useState([]);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const load = useCallback(() => {
    Promise.all([api("/admin/users/stats"), api("/admin/api-keys")])
      .then(([u, k]) => { setStats(u); setKeys(k); })
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => { load(); }, [load]);

  async function patchUser(userId, body) {
    setError(""); setSuccess("");
    try {
      await api("/admin/users/" + userId, { method: "PATCH", body });
      setSuccess("User updated.");
      load();
    } catch (e) { setError(e.message); }
  }

  async function removeUser(u) {
    if (!confirm(`Remove ${u.email} from the organisation? They will lose access but their account is not deleted.`)) return;
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

  const fmt = (n) => Number(n).toLocaleString();

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
        <div style={s.sectionTitle}>Organisation Members</div>
        <table style={s.table}>
          <thead>
            <tr>
              {["Email", "Name", "Role", "Status", "Last Login", "Tokens Used", "Balance", "Requests", "Blocked", ""].map(h => (
                <th key={h} style={s.th}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {stats.map(u => (
              <tr key={u.id}>
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
              <tr><td colSpan={10} style={s.td}>No users found</td></tr>
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
