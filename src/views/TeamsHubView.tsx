import React, { useState, useEffect } from "react";
import { api } from "../utils/api";
import { s } from "../styles/theme";
import type { components } from "../api-types";
type OrgOut = components["schemas"]["OrgOut"];
type UserOut = components["schemas"]["UserOut"];

export default function TeamsHubView({ user, onSwitch, onBack }: { user: UserOut | null; onSwitch?: (org: OrgOut) => void; onBack?: () => void }) {
  const [teams, setTeams] = useState<OrgOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<OrgOut | null>(null);
  const [deleteFullName, setDeleteFullName] = useState("");
  const [deleting, setDeleting] = useState(false);

  async function fetchTeams() {
    setLoading(true); setError("");
    try {
      const data = await api<OrgOut[]>("/org/list");
      setTeams(data);
    } catch (e) {
      // fallback to current org single
      try {
        const cur = await api<OrgOut>("/org");
        setTeams([cur]);
      } catch { setError(e instanceof Error ? e.message : String(e)); }
    } finally { setLoading(false); }
  }
  useEffect(() => { fetchTeams(); }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true); setError(""); setSuccess("");
    try {
      const body: any = {};
      if (newName.trim()) body.name = newName.trim();
      const org = await api<OrgOut>("/org", { method: "POST", body });
      setSuccess(`Created ${org.name}`);
      setNewName("");
      fetchTeams();
      if (onSwitch) onSwitch(org);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setCreating(false); }
  }

  async function handleSwitch(org: OrgOut) {
    setError(""); setSuccess("");
    try {
      const switched = await api<OrgOut>("/org/switch", { method: "POST", body: { org_id: org.id } });
      setSuccess(`Switched to ${switched.name}`);
      if (onSwitch) onSwitch(switched);
      else window.location.reload();
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  }

  async function handleRename(org: OrgOut) {
    if (!editName.trim()) return;
    try {
      const updated = await api<OrgOut>(`/org/${org.id}`, { method: "PATCH", body: { name: editName.trim() } });
      setTeams(teams.map(t => t.id === org.id ? updated : t));
      setEditingId(null); setSuccess(`Renamed to ${updated.name}`);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  }

  async function handleDeleteConfirm() {
    if (!deleteTarget || !user) return;
    if (deleteFullName.trim() !== user.full_name.trim()) {
      setError(`Full name does not match — type '${user.full_name}' exactly to confirm`);
      return;
    }
    setDeleting(true); setError("");
    try {
      await api(`/org/${deleteTarget.id}`, { method: "DELETE", body: { full_name: deleteFullName.trim() } });
      setSuccess(`Deleted ${deleteTarget.name}`);
      setDeleteTarget(null); setDeleteFullName("");
      fetchTeams();
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setDeleting(false); }
  }

  return (
    <div style={{ maxWidth: 900, margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
        {onBack && <button onClick={onBack} style={{ ...s.btn("secondary"), padding: "8px 14px", borderRadius: 10 }}>← Back</button>}
        <div style={s.pageTitle}>Your Teams</div>
        <span style={{ background: "#f1f5f9", border: "1px solid #e2e8f0", padding: "4px 10px", borderRadius: 999, fontSize: 11, fontWeight: 700, color: "#475569" }}>{teams.length} / 500 project{teams.length !== 1 ? "s" : ""}</span>
        <span style={{ marginLeft: "auto", fontSize: 11, color: "#7b8a9d" }}>Leader can join multiple — click a team to work there • Cap 500 teams/user</span>
      </div>

      <div style={{ ...s.heroPanel, background: "linear-gradient(135deg,#fff 0%,#f8fafc 60%,#f0fdfa 100%)", border: "1px solid #e2e8f0", marginBottom: 16 }}>
        <div style={{ color: "#405166", fontSize: 13, lineHeight: 1.6 }}>Choose a project to work with. Each team has its own skills, policy, and audit logs. Create <strong>Team 1, Team 2…</strong> by default — rename easily.</div>
      </div>

      {error && <div style={{ ...s.alert("error"), marginBottom: 12 }}>{error}</div>}
      {success && <div style={{ ...s.alert("success"), marginBottom: 12 }}>{success}</div>}

      {/* Create new team */}
      <form onSubmit={handleCreate} style={{ ...s.card, display: "flex", gap: 10, flexWrap: "wrap", alignItems: "end", marginBottom: 16, background: "linear-gradient(135deg,#fff 0%,#f0fdfa 100%)", borderColor: "#99f6e4" }}>
        <div style={{ flex: "1 1 260px" }}>
          <label style={s.label}>New team name (optional — defaults to Team 1, Team 2)</label>
          <input style={s.input} placeholder="Team 1" value={newName} onChange={e => setNewName(e.target.value)} maxLength={120} />
        </div>
        <button type="submit" disabled={creating} style={{ ...s.btn("primary"), height: 42, padding: "0 18px" }}>{creating ? "Creating…" : "+ Create team"}</button>
      </form>

      {/* Teams grid */}
      {loading ? <div style={s.muted}>Loading teams…</div> : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(240px,1fr))", gap: 14 }}>
          {teams.map(org => {
            const isCurrent = user?.org_id === org.id;
            const isEditing = editingId === org.id;
            return (
              <div key={org.id} style={{ ...s.card, padding: 16, borderColor: isCurrent ? "#0f766e" : "#e2e8f0", background: isCurrent ? "#ecfdf5" : "#fff", position: "relative" }}>
                {isCurrent && <span style={{ position: "absolute", top: 10, right: 10, background: "#0f766e", color: "#fff", fontSize: 10, fontWeight: 800, padding: "3px 8px", borderRadius: 999 }}>Current</span>}
                <div style={{ fontSize: 11, color: "#7b8a9d", fontWeight: 700, letterSpacing: "0.04em", textTransform: "uppercase" }}>Team</div>
                {isEditing ? (
                  <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
                    <input style={{ ...s.input, flex: 1, padding: "6px 10px", fontSize: 13 }} value={editName} onChange={e => setEditName(e.target.value)} autoFocus onKeyDown={e => e.key === "Enter" && handleRename(org)} />
                    <button onClick={() => handleRename(org)} style={{ ...s.btn("primary"), padding: "6px 10px", fontSize: 11 }}>Save</button>
                    <button onClick={() => setEditingId(null)} style={{ ...s.btn("secondary"), padding: "6px 10px", fontSize: 11 }}>Cancel</button>
                  </div>
                ) : (
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 4 }}>
                    <div style={{ fontSize: 18, fontWeight: 900, color: "#102033", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{org.name}</div>
                    <button onClick={() => { setEditingId(org.id); setEditName(org.name); }} style={{ background: "none", border: "1px solid #e2e8f0", borderRadius: 6, padding: "4px 8px", fontSize: 11, cursor: "pointer", color: "#475569" }}>Rename</button>
                  </div>
                )}
                <div style={{ fontSize: 11, color: "#7b8a9d", marginTop: 4, fontFamily: "ui-monospace, monospace" }}>{org.slug} • {new Date(org.created_at).toLocaleDateString()}</div>
                <button onClick={() => handleSwitch(org)} style={{ ...s.btn(isCurrent ? "secondary" : "primary"), width: "100%", marginTop: 12, padding: "10px 12px", borderRadius: 10 }}>
                  {isCurrent ? "Working here ✓" : `Open ${org.name} →`}
                </button>
                {/* Delete project — last button, leader only, requires full name signature */}
                <button onClick={() => { setDeleteTarget(org); setDeleteFullName(""); setError(""); }} style={{ ...s.btn("danger"), width: "100%", marginTop: 8, padding: "8px 12px", borderRadius: 10, fontSize: 11 }}>Delete project</button>
              </div>
            );
          })}
          {teams.length === 0 && !loading && <div style={{ ...s.card, textAlign: "center", color: "#7b8a9d", padding: 24 }}>No teams yet — create Team 1 above.</div>}
        </div>
      )}

      {/* Delete confirm modal — sign full name */}
      {deleteTarget && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(16,32,51,0.5)", display: "grid", placeItems: "center", zIndex: 50, padding: 16 }} onClick={() => setDeleteTarget(null)}>
          <div style={{ ...s.card, maxWidth: 440, width: "100%", background: "#fff" }} onClick={e => e.stopPropagation()}>
            <div style={{ fontSize: 16, fontWeight: 900, color: "#be123c" }}>Delete project — {deleteTarget.name}?</div>
            <div style={{ fontSize: 13, color: "#475569", lineHeight: 1.6, marginTop: 8 }}>This will delete the team, its memberships, and policies. This action cannot be undone.</div>
            <div style={{ fontSize: 13, color: "#102033", fontWeight: 700, marginTop: 12 }}>Type your full name <code style={{ background: "#fef2f2", border: "1px solid #fecdd3", padding: "2px 6px", borderRadius: 6, fontSize: 12 }}>{user?.full_name}</code> to confirm:</div>
            <input style={{ ...s.input, marginTop: 8 }} placeholder={user?.full_name || "Full name"} value={deleteFullName} onChange={e => setDeleteFullName(e.target.value)} autoFocus onKeyDown={e => e.key === "Enter" && handleDeleteConfirm()} />
            <div style={{ display: "flex", gap: 8, marginTop: 12, justifyContent: "flex-end" }}>
              <button onClick={() => setDeleteTarget(null)} style={{ ...s.btn("secondary"), padding: "8px 14px" }} disabled={deleting}>Cancel</button>
              <button onClick={handleDeleteConfirm} disabled={deleting || deleteFullName.trim() !== (user?.full_name.trim() || "")} style={{ ...s.btn("danger"), padding: "8px 14px", opacity: (deleting || deleteFullName.trim() !== (user?.full_name.trim() || "")) ? 1 : 0.6 }}>Delete</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
