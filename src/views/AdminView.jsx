import React, { useState, useEffect, useCallback, useRef } from "react";
import { api, getToken, setTokens, clearTokens, getGatewayKey, setGatewayKey, maskGatewayKey, gatewayKeyInputProps, formatApiError } from "../utils/api";
import { s } from "../styles/theme";
export default function AdminView() {
  const [users, setUsers] = useState([]);
  const [keys, setKeys] = useState([]);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    Promise.all([api("/admin/users"), api("/admin/api-keys")])
      .then(([u, k]) => { setUsers(u); setKeys(k); })
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => { load(); }, [load]);

  async function patchUser(user, body) {
    setError("");
    try {
      await api("/admin/users/" + user.id, { method: "PATCH", body });
      load();
    } catch (e) { setError(e.message); }
  }

  async function revokeKey(id) {
    if (!confirm("Revoke this organization key?")) return;
    setError("");
    try {
      await api("/admin/api-keys/" + id, { method: "DELETE" });
      load();
    } catch (e) { setError(e.message); }
  }

  return (
    <div>
      <div style={s.heroPanel}>
        <div style={{ ...s.pageTitle, marginBottom: 8 }}>Admin Controls</div>
        <div style={{ color: "#405166", fontSize: 15, lineHeight: 1.6 }}>
          Manage organization users and revoke keys when access should be removed.
        </div>
      </div>
      {error && <div style={s.alert("error")}>{error}</div>}

      <div style={{ ...s.card, marginBottom: 24 }}>
        <div style={s.sectionTitle}>Organization Users</div>
        <table style={s.table}>
          <thead>
            <tr>{["Email","Name","Role","Status","Created",""].map(h => <th key={h} style={s.th}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {users.map(u => (
              <tr key={u.id}>
                <td style={s.td}>{u.email}</td>
                <td style={s.td}>{u.full_name}</td>
                <td style={s.td}>{u.is_admin ? "admin" : "member"}</td>
                <td style={s.td}><span style={s.badge(u.is_active ? "delivered" : "error")}>{u.is_active ? "active" : "disabled"}</span></td>
                <td style={s.td}>{new Date(u.created_at).toLocaleDateString()}</td>
                <td style={s.td}>
                  <button style={s.btn("secondary")} onClick={() => patchUser(u, { is_admin: !u.is_admin })}>
                    {u.is_admin ? "MEMBER" : "ADMIN"}
                  </button>
                  <button style={{ ...s.btn(u.is_active ? "danger" : "secondary"), marginLeft: 8 }}
                    onClick={() => patchUser(u, { is_active: !u.is_active })}>
                    {u.is_active ? "DISABLE" : "ENABLE"}
                  </button>
                </td>
              </tr>
            ))}
            {users.length === 0 && (
              <tr><td colSpan={6} style={s.td}>No users found</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div style={s.card}>
        <div style={s.sectionTitle}>Organization API Keys</div>
        <table style={s.table}>
          <thead>
            <tr>{["Name","Prefix","Requests","Blocked","Status",""].map(h => <th key={h} style={s.th}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {keys.map(k => (
              <tr key={k.id}>
                <td style={s.td}>{k.name}</td>
                <td style={{ ...s.td, fontFamily: "monospace", color: "#0f766e", fontWeight: 800 }}>
                  {maskGatewayKey(k.key_prefix + "0".repeat(24))}
                </td>
                <td style={s.td}>{k.total_requests.toLocaleString()}</td>
                <td style={s.td}>{k.total_blocked.toLocaleString()}</td>
                <td style={s.td}><span style={s.badge(k.is_active ? "delivered" : "error")}>{k.is_active ? "active" : "revoked"}</span></td>
                <td style={s.td}>{k.is_active && <button style={s.btn("danger")} onClick={() => revokeKey(k.id)}>Revoke</button>}</td>
              </tr>
            ))}
            {keys.length === 0 && (
              <tr><td colSpan={6} style={s.td}>No organization keys found</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

