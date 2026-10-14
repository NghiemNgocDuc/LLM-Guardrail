import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { api } from "../utils/api";
import type { components } from "../api-types";
import { Badge, Button, Dialog, EmptyState, Field, LoadingState, Notice, PageHeader, Panel, TableWrap, useConfirmation } from "../components/ui";
import "../styles/accounts.css";

type User = components["schemas"]["UserOut"];
type Member = components["schemas"]["AdminUserStats"];
const message = (reason: unknown) => reason instanceof Error ? reason.message : String(reason);
const number = (value: number) => value.toLocaleString();

export default function TeamView({ user, onUserUpdate }: { user: User | null; onUserUpdate?: (user: User) => void }) {
  const [members, setMembers] = useState<Member[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [addMode, setAddMode] = useState<"invite" | "existing">("invite");
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteName, setInviteName] = useState("");
  const [inviteAdmin, setInviteAdmin] = useState(false);
  const [lookupEmail, setLookupEmail] = useState("");
  const [lookupResult, setLookupResult] = useState<User | null>(null);
  const [dialogError, setDialogError] = useState("");
  const { confirm, dialog } = useConfirmation();

  const fetchMembers = useCallback(async () => {
    if (!user?.is_admin || !user.org_id) { setLoading(false); return; }
    setLoading(true); setError("");
    try { setMembers(await api<Member[]>("/admin/users/stats")); }
    catch (reason) { setError(message(reason)); } finally { setLoading(false); }
  }, [user?.is_admin, user?.org_id]);
  useEffect(() => { void fetchMembers(); }, [fetchMembers]);

  async function refreshIdentity() {
    const updated = await api<User>("/auth/me");
    if (onUserUpdate) onUserUpdate(updated); else window.location.reload();
  }

  async function invite(event: FormEvent) {
    event.preventDefault(); setBusy("invite"); setDialogError(""); setSuccess("");
    try {
      await api("/admin/users/invite", { method: "POST", body: { email: inviteEmail.trim(), full_name: inviteName.trim(), is_admin: inviteAdmin } });
      setSuccess(`Invitation created for ${inviteEmail.trim()} as ${inviteAdmin ? "an administrator" : "a member"}.`);
      setAddOpen(false); setInviteEmail(""); setInviteName(""); setInviteAdmin(false); await fetchMembers();
    } catch (reason) { setDialogError(message(reason)); } finally { setBusy(null); }
  }

  async function lookup(event: FormEvent) {
    event.preventDefault(); setBusy("lookup"); setDialogError(""); setLookupResult(null);
    try { setLookupResult(await api<User>(`/admin/users/lookup?email=${encodeURIComponent(lookupEmail.trim())}`)); }
    catch (reason) { setDialogError(message(reason)); } finally { setBusy(null); }
  }

  async function addExisting() {
    if (!lookupResult) return;
    setBusy("add"); setDialogError(""); setSuccess("");
    try { await api("/admin/users/add-existing", { method: "POST", body: { email: lookupResult.email } }); setSuccess(`${lookupResult.email} added to this team.`); setAddOpen(false); setLookupEmail(""); setLookupResult(null); await fetchMembers(); }
    catch (reason) { setDialogError(message(reason)); } finally { setBusy(null); }
  }

  async function updateMember(member: Member, changes: Record<string, unknown>) {
    setBusy(member.id); setError(""); setSuccess("");
    try { await api(`/admin/users/${member.id}`, { method: "PATCH", body: changes }); setSuccess(`Updated access for ${member.email}.`); await fetchMembers(); }
    catch (reason) { setError(message(reason)); } finally { setBusy(null); }
  }

  async function removeMember(member: Member) {
    if (!await confirm({ title: `Remove ${member.full_name || member.email}?`, description: `${member.email} will lose membership in this team. If they are the only administrator, the service assigns a replacement.`, confirmLabel: "Remove member", danger: true })) return;
    setBusy(member.id); setError(""); setSuccess("");
    try { await api(`/admin/users/${member.id}`, { method: "DELETE" }); setSuccess(`${member.email} removed from this team.`); await fetchMembers(); }
    catch (reason) { setError(message(reason)); } finally { setBusy(null); }
  }

  async function declineRole() {
    if (!user || !await confirm({ title: "Step down as administrator?", description: "You will become a member. At least one other administrator must remain to manage the team.", confirmLabel: "Become a member" })) return;
    setBusy("role"); setError("");
    try { await api(`/admin/users/${user.id}`, { method: "PATCH", body: { is_admin: false } }); await refreshIdentity(); setSuccess("You are now a member of this team."); }
    catch (reason) { setError(message(reason)); } finally { setBusy(null); }
  }

  async function leaveTeam() {
    if (!await confirm({ title: "Leave this team?", description: "You will lose access to this workspace. If you are its only administrator, assign another administrator before leaving.", confirmLabel: "Leave team", danger: true })) return;
    setBusy("leave"); setError("");
    try { await api("/org/leave", { method: "POST" }); await refreshIdentity(); setSuccess("You have left the team."); }
    catch (reason) { setError(message(reason)); } finally { setBusy(null); }
  }

  const filtered = members.filter((member) => (!query || member.email.toLowerCase().includes(query.toLowerCase())) && (filter !== "admin" || member.is_admin) && (filter !== "member" || !member.is_admin) && (filter !== "active" || member.is_active));
  const leaders = members.filter((member) => member.is_admin).length;
  const canManage = Boolean(user?.is_admin && user.org_id);

  return <div className="accounts-page">
    <PageHeader eyebrow="Team access" title="Your people. Their permissions." description="Manage membership, access, and usage in your current workspace." actions={canManage ? <><Button variant="secondary" icon="refresh" loading={loading} onClick={() => void fetchMembers()}>Refresh</Button><Button variant="primary" icon="plus" onClick={() => { setAddOpen(true); setDialogError(""); }}>Add member</Button></> : <a className="accounts-link" href="?view=teams">Choose a workspace →</a>} />
    {error && <Notice tone="danger">{error}</Notice>}{success && <Notice tone="success">{success}</Notice>}
    {!canManage ? <Panel><EmptyState icon="team" title={user?.org_id ? "An administrator manages team access" : "Choose a team to get started"} description={user?.org_id ? "Ask a workspace administrator to invite people or update permissions." : "Create or open a workspace to manage your teammates."} action={<a className="accounts-link" href="?view=teams">Open your teams →</a>} /></Panel> : <>
      <div className="accounts-summary-grid"><div><span>Total members</span><strong>{number(members.length)}</strong></div><div><span>Administrators</span><strong>{number(leaders)}</strong></div><div><span>Active accounts</span><strong>{number(members.filter((member) => member.is_active).length)}</strong></div></div>
      <Panel title="Team members" description="A team can have multiple administrators. Last sign-in does not indicate online presence." actions={<Badge>{filtered.length} shown</Badge>}>
        <div className="accounts-filter-bar"><Field label="Filter by email"><input className="ui-input" type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="name@company.com" /></Field><Field label="Show"><select className="ui-input" value={filter} onChange={(event) => setFilter(event.target.value)}><option value="">All members</option><option value="admin">Administrators</option><option value="member">Members</option><option value="active">Active accounts</option></select></Field></div>
        {loading && !members.length ? <LoadingState label="Loading team members" /> : filtered.length ? <TableWrap label="Team members and permissions"><table className="ui-table accounts-table"><thead><tr><th scope="col">Member</th><th scope="col">Role</th><th scope="col">Last sign-in</th><th scope="col">Tokens</th><th scope="col">Requests</th><th scope="col">Access</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead><tbody>{filtered.map((member) => <tr key={member.id}>
          <td><div className="accounts-member"><span className="accounts-member-avatar" aria-hidden="true">{(member.full_name || member.email).split(/\s+/).map((part) => part[0]).join("").slice(0, 2).toUpperCase()}</span><div><strong className="accounts-table-name">{member.full_name || member.email}{member.id === user?.id && <span className="accounts-you">You</span>}</strong><span className="accounts-secondary">{member.email}</span></div></div></td>
          <td>{member.id === user?.id ? <Badge tone="info">Administrator</Badge> : <select className="ui-input accounts-table-select" value={member.is_admin ? "admin" : "member"} disabled={Boolean(busy)} aria-label={`Role for ${member.email}`} onChange={(event) => void updateMember(member, { is_admin: event.target.value === "admin" })}><option value="member">Member</option><option value="admin">Administrator</option></select>}</td>
          <td className="accounts-nowrap accounts-small">{member.last_login ? <time dateTime={member.last_login}>{new Date(member.last_login).toLocaleString()}</time> : "Never"}</td><td className="accounts-mono"><span>{number(member.tokens_used)} used</span><span className="accounts-secondary">{number(member.tokens_balance)} remaining</span></td><td className="accounts-mono"><span>{number(member.total_requests)}</span><span className="accounts-secondary">{number(member.total_blocked)} blocked</span></td>
          <td><Badge tone={member.is_active ? "success" : "neutral"}>{member.is_active ? "Active" : "Disabled"}</Badge>{member.id !== user?.id && <Button variant="ghost" loading={busy === member.id} disabled={Boolean(busy)} onClick={() => void updateMember(member, { is_active: !member.is_active })}>{member.is_active ? "Disable" : "Enable"}</Button>}</td><td>{member.id !== user?.id && <Button variant="ghost" className="accounts-danger-text" disabled={Boolean(busy)} onClick={() => void removeMember(member)}>Remove</Button>}</td>
        </tr>)}</tbody></table></TableWrap> : <EmptyState icon="team" title={members.length ? "No members match" : error ? "Members are unavailable" : "No members found"} description={members.length ? "Try a different email or show all members." : error ? "Refresh to try loading the team again." : "Invite someone or add an existing account to this workspace."} action={members.length ? <Button variant="secondary" onClick={() => { setQuery(""); setFilter(""); }}>Clear filters</Button> : undefined} />}
      </Panel>
    </>}
    {user?.org_id && <Panel title="Your membership" description="Manage your own role and your access to this workspace."><div className="accounts-session-row"><p className="accounts-copy">{canManage ? "You are an administrator in this workspace." : "You are a member in this workspace."}</p><div className="accounts-actions">{canManage && leaders > 1 && <Button variant="secondary" loading={busy === "role"} disabled={Boolean(busy)} onClick={() => void declineRole()}>Step down as administrator</Button>}<Button variant="danger" loading={busy === "leave"} disabled={Boolean(busy)} onClick={() => void leaveTeam()}>Leave team</Button></div></div></Panel>}
    <Dialog open={addOpen} onClose={() => setAddOpen(false)} title="Bring someone into the team" description="Invite a new account or add someone already using AI Guardrails." dismissible={!busy} footer={<><Button onClick={() => setAddOpen(false)} disabled={Boolean(busy)}>Cancel</Button>{addMode === "invite" ? <Button variant="primary" type="submit" form="accounts-invite-member" loading={busy === "invite"} disabled={Boolean(busy)}>Send invitation</Button> : lookupResult && <Button variant="primary" loading={busy === "add"} disabled={Boolean(busy)} onClick={() => void addExisting()}>Add to team</Button>}</>}>
      <div className="accounts-add-options" role="group" aria-label="How to add a member"><Button variant={addMode === "invite" ? "primary" : "secondary"} aria-pressed={addMode === "invite"} disabled={Boolean(busy)} onClick={() => { setAddMode("invite"); setDialogError(""); }}>Invite a new user</Button><Button variant={addMode === "existing" ? "primary" : "secondary"} aria-pressed={addMode === "existing"} disabled={Boolean(busy)} onClick={() => { setAddMode("existing"); setDialogError(""); }}>Add an existing user</Button></div>
      {addMode === "invite" ? <form className="ui-form" id="accounts-invite-member" onSubmit={invite}><Field label="Full name"><input className="ui-input" value={inviteName} onChange={(event) => setInviteName(event.target.value)} autoComplete="name" required minLength={1} maxLength={120} /></Field><Field label="Email address"><input className="ui-input" type="email" value={inviteEmail} onChange={(event) => setInviteEmail(event.target.value)} autoComplete="email" required /></Field><Field label="Workspace role" hint="Adding an administrator does not change your own role."><select className="ui-input" value={inviteAdmin ? "admin" : "member"} onChange={(event) => setInviteAdmin(event.target.value === "admin")}><option value="member">Member</option><option value="admin">Administrator</option></select></Field></form> : <div className="ui-stack"><form className="ui-form" onSubmit={lookup}><Field label="Exact email address" hint="Look up an existing account before adding it."><input className="ui-input" type="email" value={lookupEmail} onChange={(event) => { setLookupEmail(event.target.value); setLookupResult(null); }} autoComplete="off" required /></Field><div><Button type="submit" variant="secondary" icon="search" loading={busy === "lookup"} disabled={Boolean(busy)}>Find account</Button></div></form>{lookupResult && <div className="accounts-lookup-result"><strong>{lookupResult.full_name || lookupResult.email}</strong><p>{lookupResult.email}</p><Badge tone={lookupResult.email_verified ? "success" : "warning"}>{lookupResult.email_verified ? "Email verified" : "Email unverified"}</Badge></div>}</div>}
      {dialogError && <Notice tone="danger">{dialogError}</Notice>}
    </Dialog>{dialog}
  </div>;
}
