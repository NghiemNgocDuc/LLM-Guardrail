import React, { useState, useEffect } from "react";
import { api } from "../utils/api";
import { s } from "../styles/theme";

export default function TeamView({ user }) {
  const [members, setMembers] = useState([]);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);

  // Invite form state
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteName, setInviteName] = useState("");
  const [inviteAdmin, setInviteAdmin] = useState(false);
  const [inviting, setInviting] = useState(false);

  useEffect(() => {
    if (user?.is_admin) fetchMembers();
  }, [user]);

  async function fetchMembers() {
    try {
      const data = await api("/admin/users");
      setMembers(data);
    } catch (e) {
      setError(e.message);
    }
  }

  async function handleInvite(e) {
    e.preventDefault();
    if (!inviteEmail.trim() || !inviteName.trim()) return;
    setInviting(true); setError(""); setSuccess("");
    try {
      await api("/admin/users/invite", {
        method: "POST",
        body: { email: inviteEmail.trim(), full_name: inviteName.trim(), is_admin: inviteAdmin }
      });
      setSuccess(`Invitation sent to ${inviteEmail}.`);
      setInviteEmail(""); setInviteName(""); setInviteAdmin(false);
      fetchMembers();
    } catch (e) {
      setError(e.message);
    } finally {
      setInviting(false);
    }
  }

  async function updateMember(userId, updates) {
    try {
      const updatedUser = await api(`/admin/users/${userId}`, {
        method: "PATCH",
        body: updates
      });
      setMembers(members.map(m => m.id === userId ? updatedUser : m));
      setSuccess("User updated successfully.");
      setTimeout(() => setSuccess(""), 3000);
    } catch (e) {
      setError(e.message);
    }
  }

  if (!user?.is_admin) {
    return (
      <div>
        <div style={s.heroPanel}>
          <div style={s.pageTitle}>Team & Access</div>
        </div>
        <div style={s.alert("error")}>You must be an Organization Administrator to view this page.</div>
      </div>
    );
  }

  return (
    <div>
      <div style={s.heroPanel}>
        <div style={{ ...s.pageTitle, marginBottom: 8 }}>Team Management</div>
        <div style={{ color: "#405166", fontSize: 15, lineHeight: 1.6 }}>
          Invite team members, manage their roles, and oversee organization access.
        </div>
      </div>
      
      {error && <div style={s.alert("error")}>{error}</div>}
      {success && <div style={s.alert("success")}>{success}</div>}

      <div style={{ display: "flex", gap: 24, alignItems: "flex-start" }}>
        
        {/* Members List */}
        <div style={{ ...s.card, flex: 2 }}>
          <div style={{ ...s.sectionTitle, display: "flex", justifyContent: "space-between" }}>
            Organization Members
            <span style={s.badge("delivered")}>{members.length} Users</span>
          </div>
          <table style={{ ...s.table, marginTop: 16 }}>
            <thead>
              <tr>
                <th style={s.th}>User</th>
                <th style={s.th}>Role</th>
                <th style={s.th}>Status</th>
                <th style={s.th}>Joined</th>
              </tr>
            </thead>
            <tbody>
              {members.map(m => (
                <tr key={m.id}>
                  <td style={s.td}>
                    <div style={{ fontWeight: 700, color: "#102033" }}>{m.full_name}</div>
                    <div style={{ fontSize: 12, color: "#7b8a9d" }}>{m.email}</div>
                  </td>
                  <td style={s.td}>
                    {m.id === user.id ? (
                      <span style={{ fontSize: 13, fontWeight: 700, color: "#0f766e" }}>Admin (You)</span>
                    ) : (
                      <select 
                        style={{ ...s.input, padding: "4px 8px", width: "auto" }}
                        value={m.is_admin ? "admin" : "member"}
                        onChange={(e) => updateMember(m.id, { is_admin: e.target.value === "admin" })}
                      >
                        <option value="member">Member</option>
                        <option value="admin">Admin</option>
                      </select>
                    )}
                  </td>
                  <td style={s.td}>
                    {m.id === user.id ? (
                      <span style={s.badge("delivered")}>Active</span>
                    ) : (
                      <button 
                        style={{ 
                          ...s.btn(m.is_active ? "secondary" : "primary"), 
                          padding: "4px 12px", fontSize: 12 
                        }}
                        onClick={() => updateMember(m.id, { is_active: !m.is_active })}
                      >
                        {m.is_active ? "Revoke Access" : "Restore Access"}
                      </button>
                    )}
                  </td>
                  <td style={s.td}>{new Date(m.created_at).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Invite Form */}
        <div style={{ ...s.card, flex: 1, background: "linear-gradient(to bottom right, #ffffff, #f0fdf4)" }}>
          <div style={s.sectionTitle}>Invite User</div>
          <form onSubmit={handleInvite}>
            <label style={s.label}>Full Name</label>
            <input 
              style={{ ...s.input, marginBottom: 12 }} 
              placeholder="e.g. Jane Doe"
              value={inviteName} onChange={e => setInviteName(e.target.value)}
              required
            />
            <label style={s.label}>Email Address</label>
            <input 
              type="email" style={{ ...s.input, marginBottom: 12 }} 
              placeholder="jane@company.com"
              value={inviteEmail} onChange={e => setInviteEmail(e.target.value)}
              required
            />
            <label style={{ ...s.label, display: "flex", alignItems: "center", gap: 8, cursor: "pointer", marginBottom: 20 }}>
              <input 
                type="checkbox" 
                checked={inviteAdmin} 
                onChange={e => setInviteAdmin(e.target.checked)} 
              />
              Make this user an Admin
            </label>
            <button style={{ ...s.btn("primary"), width: "100%" }} type="submit" disabled={inviting}>
              {inviting ? "Sending Invite..." : "Send Invitation"}
            </button>
          </form>
          <div style={{ fontSize: 11, color: "#64748b", marginTop: 16, lineHeight: 1.5 }}>
            Invited users will receive an email with a secure link to set their password and join your organization.
          </div>
        </div>
      </div>
    </div>
  );
}
