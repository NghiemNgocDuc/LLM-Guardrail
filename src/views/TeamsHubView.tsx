import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { api } from "../utils/api";
import type { components } from "../api-types";
import { Badge, Button, Dialog, EmptyState, Field, LoadingState, Notice, PageHeader } from "../components/ui";
import AppIcon from "../components/AppIcon";
import "../styles/accounts.css";

type Organization = components["schemas"]["OrgOut"];
type User = components["schemas"]["UserOut"];
const errorMessage = (reason: unknown) => reason instanceof Error ? reason.message : String(reason);

export default function TeamsHubView({ user, onSwitch, onBack, onUserUpdate }: { user: User | null; onSwitch?: (org: Organization) => void; onBack?: () => void; onUserUpdate?: (user: User) => void }) {
  const [teams, setTeams] = useState<Organization[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);
  const [switching, setSwitching] = useState<string | null>(null);
  const [renameTarget, setRenameTarget] = useState<Organization | null>(null);
  const [editName, setEditName] = useState("");
  const [renaming, setRenaming] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Organization | null>(null);
  const [signature, setSignature] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [dialogError, setDialogError] = useState("");

  const fetchTeams = useCallback(async () => {
    setLoading(true); setError("");
    try { setTeams(await api<Organization[]>("/org/list")); }
    catch (reason) {
      try { setTeams([await api<Organization>("/org")]); setError("The team list could not be loaded. Showing your current workspace only."); }
      catch { setError(errorMessage(reason)); }
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { void fetchTeams(); }, [fetchTeams]);

  async function create(event: FormEvent) {
    event.preventDefault(); setCreating(true); setDialogError("");
    try {
      const org = await api<Organization>("/org", { method: "POST", body: newName.trim() ? { name: newName.trim() } : {} });
      setCreateOpen(false); setNewName(""); setSuccess(`Created ${org.name}.`); await fetchTeams();
      if (onSwitch) onSwitch(org); else onUserUpdate?.(await api<User>("/auth/me"));
    } catch (reason) { setDialogError(errorMessage(reason)); } finally { setCreating(false); }
  }

  async function switchTeam(org: Organization) {
    setSwitching(org.id); setError(""); setSuccess("");
    try {
      const switched = await api<Organization>("/org/switch", { method: "POST", body: { org_id: org.id } });
      if (onSwitch) onSwitch(switched); else { onUserUpdate?.(await api<User>("/auth/me")); setSuccess(`Now working in ${switched.name}.`); }
    } catch (reason) { setError(errorMessage(reason)); } finally { setSwitching(null); }
  }

  async function rename(event: FormEvent) {
    event.preventDefault(); if (!renameTarget) return;
    setRenaming(true); setDialogError("");
    try {
      const updated = await api<Organization>(`/org/${renameTarget.id}`, { method: "PATCH", body: { name: editName.trim() } });
      setTeams((current) => current.map((team) => team.id === updated.id ? updated : team));
      setRenameTarget(null); setSuccess(`Renamed to ${updated.name}.`);
    } catch (reason) { setDialogError(errorMessage(reason)); } finally { setRenaming(false); }
  }

  async function deleteTeam(event: FormEvent) {
    event.preventDefault(); if (!deleteTarget || !user || signature.trim() !== user.full_name.trim()) return;
    setDeleting(true); setDialogError("");
    try {
      await api(`/org/${deleteTarget.id}`, { method: "DELETE", body: { full_name: signature.trim() } });
      const name = deleteTarget.name;
      const deletedCurrent = user.org_id === deleteTarget.id;
      setDeleteTarget(null); setSignature(""); setSuccess(`Deleted ${name}.`);
      if (deletedCurrent) { const updated = await api<User>("/auth/me"); if (onUserUpdate) onUserUpdate(updated); else window.location.reload(); }
      await fetchTeams();
    } catch (reason) { setDialogError(errorMessage(reason)); } finally { setDeleting(false); }
  }

  return <div className="accounts-page">
    <PageHeader eyebrow="Shared workspaces" title="Good work happens together." description="Choose a team, create a fresh workspace, or manage the spaces you belong to." actions={<><Button variant="secondary" icon="refresh" loading={loading} onClick={() => void fetchTeams()}>Refresh</Button><Button variant="primary" icon="plus" onClick={() => { setCreateOpen(true); setNewName(""); setDialogError(""); }}>Create team</Button></>} />
    {onBack && <div><Button variant="ghost" onClick={onBack}>Back to team details</Button></div>}
    {error && <Notice tone="danger">{error}</Notice>}{success && <Notice tone="success">{success}</Notice>}
    <div className="accounts-section-heading"><div><h2>Your teams</h2><p>Each workspace has its own policies, skills, and request logs.</p></div><Badge>{teams.length} {teams.length === 1 ? "team" : "teams"}</Badge></div>
    {loading && !teams.length ? <LoadingState label="Loading your teams" /> : !teams.length ? <EmptyState icon="team" title="Your first team starts here" description="Create a workspace and bring your model traffic and teammates together." action={<Button variant="primary" icon="plus" onClick={() => { setCreateOpen(true); setDialogError(""); }}>Create a team</Button>} /> : <div className="accounts-team-grid">{teams.map((org) => <article className={`accounts-team-card${user?.org_id === org.id ? " accounts-team-current" : ""}`} key={org.id}>
      <div className="accounts-team-card-top"><span className="accounts-team-mark"><AppIcon name="team" size={21} /></span>{user?.org_id === org.id && <Badge tone="success">Current workspace</Badge>}</div>
      <h3>{org.name}</h3><p className="accounts-mono accounts-copy">{org.slug}</p><p className="accounts-copy">Created <time dateTime={org.created_at}>{new Date(org.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}</time></p>
      <Button variant={user?.org_id === org.id ? "secondary" : "primary"} icon="arrow" loading={switching === org.id} disabled={Boolean(switching)} onClick={() => void switchTeam(org)}>{user?.org_id === org.id ? "Open team" : "Switch workspace"}</Button>
      <div className="accounts-team-card-footer"><Button variant="ghost" onClick={() => { setRenameTarget(org); setEditName(org.name); setDialogError(""); }} aria-label={`Rename ${org.name}`}>Rename</Button><Button variant="ghost" className="accounts-danger-text" onClick={() => { setDeleteTarget(org); setSignature(""); setDialogError(""); }} aria-label={`Delete ${org.name}`}>Delete team</Button></div>
    </article>)}</div>}
    <Dialog open={createOpen} onClose={() => setCreateOpen(false)} title="Create a team" description="You will become an administrator of the new workspace." dismissible={!creating} footer={<><Button onClick={() => setCreateOpen(false)} disabled={creating}>Cancel</Button><Button variant="primary" type="submit" form="accounts-create-team" loading={creating}>Create team</Button></>}>
      <form id="accounts-create-team" className="ui-form" onSubmit={create}><Field label="Team name" hint="Optional. Leave empty to use the next available Team number."><input className="ui-input" value={newName} onChange={(event) => setNewName(event.target.value)} maxLength={120} placeholder="e.g. Product engineering" autoFocus /></Field>{dialogError && <Notice tone="danger">{dialogError}</Notice>}</form>
    </Dialog>
    <Dialog open={Boolean(renameTarget)} onClose={() => setRenameTarget(null)} title="Rename team" description="Team administrators can update the workspace name." dismissible={!renaming} footer={<><Button onClick={() => setRenameTarget(null)} disabled={renaming}>Cancel</Button><Button variant="primary" type="submit" form="accounts-rename-team" loading={renaming}>Save name</Button></>}>
      <form id="accounts-rename-team" className="ui-form" onSubmit={rename}><Field label="Team name"><input className="ui-input" value={editName} onChange={(event) => setEditName(event.target.value)} required minLength={2} maxLength={120} autoFocus /></Field>{dialogError && <Notice tone="danger">{dialogError}</Notice>}</form>
    </Dialog>
    <Dialog open={Boolean(deleteTarget)} onClose={() => setDeleteTarget(null)} title={`Delete ${deleteTarget?.name || "team"}?`} description="This permanently removes the team and its memberships, policies, and skills. Only a team administrator can delete it." dismissible={!deleting} footer={<><Button onClick={() => setDeleteTarget(null)} disabled={deleting}>Keep team</Button><Button variant="danger" type="submit" form="accounts-delete-team" loading={deleting} disabled={!user?.full_name || signature.trim() !== user.full_name.trim()}>Delete team</Button></>}>
      <form id="accounts-delete-team" className="ui-form" onSubmit={deleteTeam}><Field label="Confirm with your full name" hint={<>Type <strong>{user?.full_name}</strong> exactly to confirm.</>}><input className="ui-input" value={signature} onChange={(event) => setSignature(event.target.value)} autoComplete="off" required minLength={2} maxLength={120} autoFocus /></Field>{dialogError && <Notice tone="danger">{dialogError}</Notice>}</form>
    </Dialog>
  </div>;
}
