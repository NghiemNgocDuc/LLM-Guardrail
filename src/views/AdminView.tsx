import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, maskGatewayKey } from "../utils/api";
import type { components } from "../api-types";
import { Badge, Button, EmptyState, Field, LoadingState, Notice, PageHeader, Panel, TableWrap, useConfirmation } from "../components/ui";
import "../styles/accounts.css";

type Member = components["schemas"]["AdminUserStats"];
type User = components["schemas"]["UserOut"];
type Key = components["schemas"]["APIKeyOut"];
type Ban = { type: string; id: string; retry_after: number; reason: string };
type SortColumn = keyof Member;
const number = (value: number) => value.toLocaleString();
const message = (reason: unknown) => reason instanceof Error ? reason.message : String(reason);
const sortable: [SortColumn, string][] = [["email", "Email"], ["full_name", "Name"], ["last_login", "Last sign-in"], ["tokens_used", "Tokens used"], ["tokens_balance", "Balance"], ["total_requests", "Requests"], ["total_blocked", "Blocked"]];

export default function AdminView({ user, onUserUpdate }: { user?: User; onUserUpdate?: (user: User) => void } = {}) {
  const [members, setMembers] = useState<Member[] | null>(null);
  const [keys, setKeys] = useState<Key[] | null>(null);
  const [bans, setBans] = useState<Ban[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [bansError, setBansError] = useState("");
  const [success, setSuccess] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");
  const [sortColumn, setSortColumn] = useState<SortColumn>("email");
  const [direction, setDirection] = useState<"asc" | "desc">("asc");
  const [busy, setBusy] = useState<string | null>(null);
  const selectAll = useRef<HTMLInputElement>(null);
  const { confirm, dialog } = useConfirmation();

  const load = useCallback(async () => {
    setLoading(true); setError(""); setBansError(""); setSelected(new Set());
    const [usersResult, keysResult, bansResult] = await Promise.allSettled([
      api<Member[]>("/admin/users/stats"), api<Key[]>("/admin/api-keys"), api<Ban[]>("/admin/bans"),
    ]);
    const errors: string[] = [];
    if (usersResult.status === "fulfilled") setMembers(usersResult.value); else { setMembers(null); errors.push(`Members: ${message(usersResult.reason)}`); }
    if (keysResult.status === "fulfilled") setKeys(keysResult.value); else { setKeys(null); errors.push(`API keys: ${message(keysResult.reason)}`); }
    if (bansResult.status === "fulfilled") setBans(bansResult.value); else { setBans(null); setBansError(message(bansResult.reason)); }
    setError(errors.join(" · ")); setLoading(false);
  }, []);
  useEffect(() => { void load(); }, [load]);

  const sorted = useMemo(() => (members || []).filter((member) => `${member.email} ${member.full_name}`.toLowerCase().includes(query.toLowerCase())).sort((a, b) => {
    const first = a[sortColumn] ?? "", second = b[sortColumn] ?? "";
    const comparison = typeof first === "number" && typeof second === "number" ? first - second : String(first).localeCompare(String(second));
    return direction === "asc" ? comparison : -comparison;
  }), [members, query, sortColumn, direction]);
  const selectable = sorted.filter((member) => member.id !== user?.id);
  const visibleSelected = selectable.filter((member) => selected.has(member.id)).length;
  useEffect(() => { if (selectAll.current) selectAll.current.indeterminate = visibleSelected > 0 && visibleSelected < selectable.length; }, [visibleSelected, selectable.length]);

  function toggle(id: string) { setSelected((current) => { const next = new Set(current); next.has(id) ? next.delete(id) : next.add(id); return next; }); }
  function toggleAll() { setSelected((current) => { const next = new Set(current); const clear = selectable.length > 0 && selectable.every((member) => next.has(member.id)); selectable.forEach((member) => clear ? next.delete(member.id) : next.add(member.id)); return next; }); }
  function sort(column: SortColumn) { if (column === sortColumn) setDirection((current) => current === "asc" ? "desc" : "asc"); else { setSortColumn(column); setDirection("asc"); } }

  async function mutate(id: string, request: () => Promise<unknown>, successMessage: string) {
    setBusy(id); setError(""); setSuccess("");
    try { await request(); setSuccess(successMessage); await load(); }
    catch (reason) { setError(message(reason)); } finally { setBusy(null); }
  }

  async function bulk(action: "enable" | "disable" | "remove") {
    const ids = [...selected]; if (!ids.length) return;
    const labels = { enable: "Enable", disable: "Disable", remove: "Remove" };
    if (!await confirm({ title: `${labels[action]} ${ids.length} selected accounts?`, description: action === "remove" ? "These users will lose membership in the current workspace." : action === "disable" ? "These users will be prevented from using their accounts." : "These accounts will be enabled again.", confirmLabel: `${labels[action]} accounts`, danger: action !== "enable" })) return;
    await mutate("bulk", () => api("/admin/users/bulk", { method: "POST", body: { action, user_ids: ids } }), "Bulk request completed. Review the refreshed accounts below.");
  }

  async function changeRole(member: Member) {
    if (!await confirm({ title: member.is_admin ? "Remove administrator access?" : "Grant administrator access?", description: `${member.email} will become ${member.is_admin ? "a member" : "an administrator"} of this workspace.`, confirmLabel: member.is_admin ? "Make member" : "Make administrator", danger: !member.is_admin })) return;
    if (member.id === user?.id) {
      setBusy(member.id); setError(""); setSuccess("");
      try { await api(`/admin/users/${member.id}`, { method: "PATCH", body: { is_admin: !member.is_admin } }); const updated = await api<User>("/auth/me"); if (onUserUpdate) onUserUpdate(updated); else window.location.reload(); }
      catch (reason) { setError(message(reason)); } finally { setBusy(null); }
    } else await mutate(member.id, () => api(`/admin/users/${member.id}`, { method: "PATCH", body: { is_admin: !member.is_admin } }), `Role updated for ${member.email}.`);
  }

  async function remove(member: Member) {
    if (!await confirm({ title: `Remove ${member.full_name || member.email}?`, description: `${member.email} will lose membership in this workspace.`, confirmLabel: "Remove member", danger: true })) return;
    await mutate(member.id, () => api(`/admin/users/${member.id}`, { method: "DELETE" }), `${member.email} removed from this workspace.`);
  }

  async function revoke(key: Key) {
    if (!await confirm({ title: `Revoke ${key.name}?`, description: "Applications using this key will no longer be able to send requests. This cannot be undone.", confirmLabel: "Revoke key", danger: true })) return;
    await mutate(key.id, () => api(`/admin/api-keys/${key.id}`, { method: "DELETE" }), `Revoked ${key.name}.`);
  }

  async function liftBan(ban: Ban) {
    if (!await confirm({ title: "Lift this temporary restriction?", description: <>The {ban.type.replaceAll("_", " ")} <span className="accounts-mono">{ban.id}</span> was restricted for {ban.reason}. Access can resume immediately.</>, confirmLabel: "Lift restriction" })) return;
    await mutate(ban.id, () => api("/admin/bans/unban", { method: "POST", body: ban.type === "api_key" ? { api_key_id: ban.id } : { user_id: ban.id } }), "Temporary restriction lifted.");
  }

  function sortHeading(column: SortColumn, label: string) {
    return <th scope="col" aria-sort={sortColumn === column ? direction === "asc" ? "ascending" : "descending" : "none"}><button className="accounts-sort-button" onClick={() => sort(column)} aria-label={`Sort by ${label}${sortColumn === column ? `, currently ${direction === "asc" ? "ascending" : "descending"}` : ""}`}>{label}<span aria-hidden="true">{sortColumn === column ? direction === "asc" ? "↑" : "↓" : "↕"}</span></button></th>;
  }

  return <div className="accounts-page">
    <PageHeader eyebrow="Administration" title="A clear view of access." description="Review workspace accounts, monitor usage, and manage temporary restrictions and API keys." actions={<Button variant="secondary" icon="refresh" loading={loading} disabled={Boolean(busy)} onClick={() => void load()}>Refresh records</Button>} />
    {error && <Notice tone="danger">{error}</Notice>}{success && <Notice tone="success">{success}</Notice>}
    <div className="accounts-summary-grid"><div><span>Workspace members</span><strong>{members ? number(members.length) : "—"}</strong></div><div><span>Enabled API keys</span><strong>{keys ? number(keys.filter((key) => key.is_active).length) : "—"}</strong></div><div><span>Temporary restrictions</span><strong>{bans ? number(bans.length) : "—"}</strong></div></div>
    <Panel title="Workspace accounts" description="Sort usage, select accounts, and update permissions." actions={<a className="accounts-link" href="?view=team">Manage invitations →</a>}>
      <div className="accounts-filter-bar"><Field label="Find a member"><input className="ui-input" type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Name or email" /></Field><Field label="Sort records"><select className="ui-input" value={sortColumn} onChange={(event) => { setSortColumn(event.target.value as SortColumn); setDirection("asc"); }}>{sortable.map(([column, label]) => <option key={column} value={column}>{label}</option>)}</select></Field><Button variant="secondary" onClick={() => setDirection((current) => current === "asc" ? "desc" : "asc")}>{direction === "asc" ? "Ascending ↑" : "Descending ↓"}</Button></div>
      {selected.size > 0 && <div className="accounts-bulk-bar" role="region" aria-label="Actions for selected accounts"><strong>{selected.size} selected</strong><div className="accounts-actions"><Button variant="secondary" disabled={Boolean(busy)} onClick={() => void bulk("enable")}>Enable</Button><Button variant="secondary" disabled={Boolean(busy)} onClick={() => void bulk("disable")}>Disable</Button><Button variant="danger" loading={busy === "bulk"} disabled={Boolean(busy)} onClick={() => void bulk("remove")}>Remove</Button><Button variant="ghost" disabled={Boolean(busy)} onClick={() => setSelected(new Set())}>Clear selection</Button></div></div>}
      {loading && members === null ? <LoadingState label="Loading workspace accounts" /> : members === null ? <EmptyState icon="team" title="Accounts could not be loaded" description="Refresh the records to try again." /> : !sorted.length ? <EmptyState icon="team" title={members.length ? "No matching accounts" : "No workspace accounts"} description={members.length ? "Try another name or email." : "Workspace members will appear here."} /> : <TableWrap label="Workspace account usage and permissions"><table className="ui-table accounts-table"><thead><tr><th scope="col"><input ref={selectAll} type="checkbox" checked={selectable.length > 0 && visibleSelected === selectable.length} onChange={toggleAll} aria-label="Select all eligible visible members" disabled={Boolean(busy) || !selectable.length} /></th>{sortHeading("email", "Email")}{sortHeading("full_name", "Name")}<th scope="col">Role</th><th scope="col">Access</th>{sortHeading("last_login", "Last sign-in")}{sortHeading("tokens_used", "Tokens used")}{sortHeading("tokens_balance", "Balance")}{sortHeading("total_requests", "Requests")}{sortHeading("total_blocked", "Blocked")}<th scope="col"><span className="sr-only">Actions</span></th></tr></thead><tbody>{sorted.map((member) => <tr key={member.id} data-selected={selected.has(member.id)}>
        <td><input type="checkbox" checked={selected.has(member.id)} onChange={() => toggle(member.id)} aria-label={`Select ${member.email}`} disabled={Boolean(busy) || member.id === user?.id} /></td><td className="accounts-nowrap">{member.email}</td><td>{member.full_name}</td><td><Badge tone={member.is_admin ? "info" : "neutral"}>{member.is_admin ? "Admin" : "Member"}</Badge></td><td><Badge tone={member.is_active ? "success" : "neutral"}>{member.is_active ? "Enabled" : "Disabled"}</Badge></td><td className="accounts-small accounts-nowrap">{member.last_login ? new Date(member.last_login).toLocaleString() : "Never"}</td><td className="accounts-mono">{number(member.tokens_used)}</td><td className="accounts-mono">{number(member.tokens_balance)}</td><td className="accounts-mono">{number(member.total_requests)}</td><td className="accounts-mono">{number(member.total_blocked)}</td><td><div className="accounts-table-actions"><Button variant="ghost" disabled={Boolean(busy)} onClick={() => void changeRole(member)}>{member.is_admin ? "Make member" : "Make admin"}</Button><Button variant="ghost" disabled={Boolean(busy) || member.id === user?.id} loading={busy === member.id} onClick={() => void mutate(member.id, () => api(`/admin/users/${member.id}`, { method: "PATCH", body: { is_active: !member.is_active } }), `Access updated for ${member.email}.`)}>{member.is_active ? "Disable" : "Enable"}</Button><Button variant="ghost" className="accounts-danger-text" onClick={() => void remove(member)} disabled={Boolean(busy) || member.id === user?.id}>Remove</Button></div></td>
      </tr>)}</tbody></table></TableWrap>}
    </Panel>
    <Panel title="Temporary restrictions" description="Automatic restrictions reported by the gateway. Retry times reflect the latest refresh." actions={bans !== null && <Badge tone={bans.length ? "warning" : "neutral"}>{bans.length} active</Badge>}>
      {bansError ? <Notice tone="danger">Restrictions could not be loaded: {bansError}</Notice> : loading && bans === null ? <LoadingState label="Loading temporary restrictions" /> : bans?.length ? <TableWrap label="Active temporary restrictions"><table className="ui-table accounts-table"><thead><tr><th scope="col">Target</th><th scope="col">Reference</th><th scope="col">Reason</th><th scope="col">Retry after</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead><tbody>{bans.map((ban) => <tr key={ban.type + ban.id}><td><Badge tone="warning">{ban.type.replaceAll("_", " ")}</Badge></td><td className="accounts-mono" title={ban.id}>{ban.id.slice(0, 12)}…</td><td>{ban.reason}</td><td className="accounts-mono accounts-nowrap">{Math.floor(ban.retry_after / 60)}m {Math.round(ban.retry_after % 60)}s</td><td><Button variant="secondary" disabled={Boolean(busy)} loading={busy === ban.id} onClick={() => void liftBan(ban)}>Lift restriction</Button></td></tr>)}</tbody></table></TableWrap> : <EmptyState icon="shield" title="No active restrictions" description="The gateway has no temporary bans to report for this workspace." />}
    </Panel>
    <Panel title="Workspace API keys" description="Usage and configured access for keys in this workspace." actions={<a className="accounts-link" href="?view=keys">Manage API keys →</a>}>
      {loading && keys === null ? <LoadingState label="Loading workspace keys" /> : keys === null ? <EmptyState icon="key" title="Keys could not be loaded" description="Refresh to try again." /> : keys.length ? <TableWrap label="Workspace API keys"><table className="ui-table accounts-table"><thead><tr><th scope="col">Key</th><th scope="col">Prefix</th><th scope="col">Requests</th><th scope="col">Blocked</th><th scope="col">Access</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead><tbody>{keys.map((key) => <tr key={key.id}><td>{key.name}</td><td className="accounts-mono">{maskGatewayKey(key.key_prefix)}</td><td className="accounts-mono">{number(key.total_requests)}</td><td className="accounts-mono">{number(key.total_blocked)}</td><td><div className="accounts-actions"><Badge tone={key.is_active ? "success" : "neutral"}>{key.is_active ? "Enabled" : "Revoked"}</Badge>{bans?.some((ban) => ban.type === "api_key" && ban.id === key.id) && <Badge tone="warning">Temporarily banned</Badge>}</div></td><td>{key.is_active && <Button variant="ghost" className="accounts-danger-text" loading={busy === key.id} disabled={Boolean(busy)} onClick={() => void revoke(key)}>Revoke</Button>}</td></tr>)}</tbody></table></TableWrap> : <EmptyState icon="key" title="No workspace keys" description="Create a gateway key to connect your first application." action={<a className="accounts-link" href="?view=keys">Open API keys →</a>} />}
    </Panel>{dialog}
  </div>;
}
