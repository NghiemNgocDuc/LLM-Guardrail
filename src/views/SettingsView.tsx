import { useCallback, useEffect, useState } from "react";
import type { Dispatch, FormEvent, SetStateAction } from "react";
import { api } from "../utils/api";
import type { components } from "../api-types";
import { Badge, Button, Field, LoadingState, Notice, PageHeader, Panel, useConfirmation } from "../components/ui";
import "../styles/accounts.css";

type User = components["schemas"]["UserOut"];
type Organization = components["schemas"]["OrgOut"];
type Policy = components["schemas"]["PolicyOut"];
const message = (reason: unknown) => reason instanceof Error ? reason.message : String(reason);

export function Feedback({ error, success }: { error?: string; success?: string }) {
  return <>{error && <Notice tone="danger">{error}</Notice>}{success && <Notice tone="success">{success}</Notice>}</>;
}

export function useWorkspaceSettings(user: User | null) {
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [org, setOrg] = useState<Organization | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const orgId = user?.org_id;
  const admin = user?.is_admin;
  const reload = useCallback(async () => {
    if (!orgId || !admin) return;
    setLoading(true); setError("");
    try { const [nextPolicy, nextOrg] = await Promise.all([api<Policy>("/policy"), api<Organization>("/org")]); setPolicy(nextPolicy); setOrg(nextOrg); }
    catch (reason) { setError(message(reason)); }
    finally { setLoading(false); }
  }, [orgId, admin]);
  useEffect(() => { void reload(); }, [reload]);
  return { policy, setPolicy, org, setOrg, loading, error, reload };
}

export function ProfileForm({ user, onUserUpdate }: { user: User | null; onUserUpdate?: (user: User) => void }) {
  const [name, setName] = useState(user?.full_name || "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  useEffect(() => { setName(user?.full_name || ""); }, [user?.full_name]);
  async function save(event: FormEvent) {
    event.preventDefault(); setSaving(true); setError(""); setSuccess("");
    try { const updated = await api<User>("/auth/profile", { method: "PATCH", body: { full_name: name.trim() } }); onUserUpdate?.(updated); setSuccess("Your profile has been saved."); }
    catch (reason) { setError(message(reason)); } finally { setSaving(false); }
  }
  return <Panel title="Personal profile" description="The name your teammates see throughout the workspace."><form className="ui-form accounts-form" onSubmit={save}>
    <Field label="Display name"><input className="ui-input" value={name} onChange={(event) => setName(event.target.value)} autoComplete="name" required minLength={1} maxLength={120} /></Field>
    <Field label="Email address" hint="Your sign-in email cannot be changed here."><input className="ui-input" type="email" value={user?.email || ""} readOnly autoComplete="email" /></Field>
    <Feedback error={error} success={success} /><div><Button variant="primary" type="submit" loading={saving} disabled={!name.trim() || name.trim() === user?.full_name}>Save profile</Button></div>
  </form></Panel>;
}

export function OrganizationForm({ org, onSaved }: { org: Organization; onSaved: (org: Organization) => void }) {
  const [name, setName] = useState(org.name);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  useEffect(() => { setName(org.name); }, [org.name]);
  async function save(event: FormEvent) {
    event.preventDefault(); setSaving(true); setError(""); setSuccess("");
    try { const updated = await api<Organization>("/org", { method: "PATCH", body: { name: name.trim() } }); onSaved(updated); setSuccess("Workspace name updated."); }
    catch (reason) { setError(message(reason)); } finally { setSaving(false); }
  }
  return <Panel title="Workspace identity" description="Give your current workspace a name your team recognises."><form className="ui-form accounts-form" onSubmit={save}>
    <Field label="Workspace name" hint={`Current identifier: ${org.slug}`}><input className="ui-input" value={name} onChange={(event) => setName(event.target.value)} required minLength={2} maxLength={120} /></Field>
    <Feedback error={error} success={success} /><div><Button variant="primary" type="submit" loading={saving} disabled={name.trim().length < 2 || name.trim() === org.name}>Rename workspace</Button></div>
  </form></Panel>;
}

export function SecurityForm({ policy, onSaved }: { policy: Policy; onSaved: (policy: Policy) => void }) {
  const [webhook, setWebhook] = useState("");
  const [ips, setIps] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  useEffect(() => {
    const rules = policy.compliance_rules || {};
    setWebhook(typeof rules.webhook_url === "string" ? rules.webhook_url : "");
    setIps(Array.isArray(rules.blocked_ips) ? rules.blocked_ips.filter((ip): ip is string => typeof ip === "string").join("\n") : "");
  }, [policy]);
  async function save(event: FormEvent) {
    event.preventDefault(); setSaving(true); setError(""); setSuccess("");
    try {
      const latest = await api<Policy>("/policy");
      const updated = await api<Policy>("/policy", { method: "PATCH", body: { compliance_rules: { ...latest.compliance_rules, webhook_url: webhook.trim(), blocked_ips: ips.split("\n").map((ip) => ip.trim()).filter(Boolean) } } });
      onSaved(updated); setSuccess("Webhook and access settings saved.");
    } catch (reason) { setError(message(reason)); } finally { setSaving(false); }
  }
  return <Panel title="Notifications & access" description="Route blocked-request notifications and manage IP access."><form className="ui-form accounts-form" onSubmit={save}>
    <Field label="Webhook URL" hint="Receives guardrail block notifications. Leave empty to turn notifications off."><input className="ui-input" type="url" value={webhook} onChange={(event) => setWebhook(event.target.value)} placeholder="https://your-server.com/webhook" /></Field>
    <Field label="IP blocklist" hint="Enter one IP address per line. Matching requests are rejected with HTTP 403."><textarea className="ui-input accounts-code-input" rows={5} value={ips} onChange={(event) => setIps(event.target.value)} placeholder={"192.168.1.100\n10.0.0.50"} /></Field>
    <Feedback error={error} success={success} /><div><Button variant="primary" type="submit" loading={saving}>Save security settings</Button></div>
  </form></Panel>;
}

function PasswordForm() {
  const [current, setCurrent] = useState("");
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [mismatch, setMismatch] = useState(false);
  async function save(event: FormEvent) {
    event.preventDefault(); setError(""); setSuccess("");
    if (password !== repeat) { setMismatch(true); return; }
    setSaving(true); setMismatch(false);
    try { const response = await api<{ message: string }>("/auth/change-password", { method: "POST", body: { current_password: current, new_password: password } }); setSuccess(response.message || "Password updated."); setCurrent(""); setPassword(""); setRepeat(""); }
    catch (reason) { setError(message(reason)); } finally { setSaving(false); }
  }
  return <Panel title="Password" description="Use at least eight characters and a password unique to this account."><form className="ui-form accounts-form" onSubmit={save}>
    <Field label="Current password"><input className="ui-input" type="password" value={current} onChange={(event) => setCurrent(event.target.value)} autoComplete="current-password" required maxLength={256} /></Field>
    <div className="accounts-form-grid"><Field label="New password"><input className="ui-input" type="password" value={password} onChange={(event) => { setPassword(event.target.value); setMismatch(false); }} autoComplete="new-password" required minLength={8} maxLength={256} /></Field><Field label="Confirm new password" error={mismatch ? "The new passwords do not match." : undefined}><input className="ui-input" type="password" value={repeat} onChange={(event) => { setRepeat(event.target.value); setMismatch(false); }} autoComplete="new-password" required minLength={8} maxLength={256} /></Field></div>
    <Feedback error={error} success={success} /><div><Button variant="primary" type="submit" loading={saving}>Update password</Button></div>
  </form></Panel>;
}

function LimitsForm({ policy, onSaved }: { policy: Policy; onSaved: (policy: Policy) => void }) {
  const [rpm, setRpm] = useState(String(policy.rate_limit_rpm || ""));
  const [rpd, setRpd] = useState(String(policy.rate_limit_rpd || ""));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  useEffect(() => { setRpm(String(policy.rate_limit_rpm || "")); setRpd(String(policy.rate_limit_rpd || "")); }, [policy.rate_limit_rpm, policy.rate_limit_rpd]);
  async function save(event: FormEvent) {
    event.preventDefault(); setSaving(true); setError(""); setSuccess("");
    try { const updated = await api<Policy>("/policy", { method: "PATCH", body: { rate_limit_rpm: Number(rpm) || 0, rate_limit_rpd: Number(rpd) || 0 } }); onSaved(updated); setSuccess("Workspace request limits saved."); }
    catch (reason) { setError(message(reason)); } finally { setSaving(false); }
  }
  return <Panel title="Request limits" description="Set workspace quotas. Empty values use the gateway defaults."><form className="ui-form accounts-form" onSubmit={save}><div className="accounts-form-grid">
    <Field label="Requests per minute"><input className="ui-input" type="number" min={1} step={1} value={rpm} onChange={(event) => setRpm(event.target.value)} placeholder="Gateway default" /></Field><Field label="Requests per day"><input className="ui-input" type="number" min={1} step={1} value={rpd} onChange={(event) => setRpd(event.target.value)} placeholder="Gateway default" /></Field>
  </div><Feedback error={error} success={success} /><div><Button variant="primary" type="submit" loading={saving}>Save request limits</Button></div></form></Panel>;
}

function AuditExport() {
  const [days, setDays] = useState(30);
  const [exporting, setExporting] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  async function download() {
    setExporting(true); setProgress(0); setError(""); setSuccess("");
    try {
      const records: Record<string, unknown>[] = [];
      let page = 1;
      while (true) {
        const data = await api<{ total: number; items: Record<string, unknown>[] }>(`/org/export?days=${days}&page=${page}&page_size=500`);
        records.push(...data.items); setProgress(records.length);
        if (!data.items.length || records.length >= data.total) break;
        page += 1;
      }
      const url = URL.createObjectURL(new Blob([JSON.stringify({ exported_at: new Date().toISOString(), days, total: records.length, items: records }, null, 2)], { type: "application/json" }));
      const anchor = document.createElement("a"); anchor.href = url; anchor.download = `guardrails-audit-${days}days-${new Date().toISOString().slice(0, 10)}.json`; anchor.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setSuccess(`Exported ${records.length.toLocaleString()} audit records.`);
    } catch (reason) { setError(message(reason)); } finally { setExporting(false); }
  }
  return <Panel title="Audit export" description="Download workspace request decisions as JSON. Raw prompts and credentials are excluded."><div className="ui-form accounts-form"><Field label="Export period"><select className="ui-input" value={days} onChange={(event) => setDays(Number(event.target.value))} disabled={exporting}><option value={7}>Last 7 days</option><option value={30}>Last 30 days</option><option value={90}>Last 90 days</option></select></Field><Feedback error={error} success={success} />{exporting && <p role="status" className="accounts-copy">Preparing {progress.toLocaleString()} records…</p>}<div><Button variant="secondary" icon="logs" loading={exporting} onClick={() => void download()}>Download audit export</Button></div></div></Panel>;
}

export default function SettingsView({ user, onUserUpdate, darkMode, setDarkMode, onLogout }: { user: User | null; onUserUpdate?: (user: User) => void; darkMode: boolean; setDarkMode: Dispatch<SetStateAction<boolean>>; onLogout: () => void }) {
  const workspace = useWorkspaceSettings(user);
  const { confirm, dialog } = useConfirmation();
  return <div className="accounts-page accounts-settings">
    <PageHeader eyebrow="Preferences & access" title="Make this workspace yours." description="Manage your profile, security, and the settings your team shares." actions={<Badge tone={user?.is_admin ? "info" : "neutral"}>{user?.is_admin ? "Administrator" : "Member"}</Badge>} />
    <div className="accounts-settings-layout"><nav className="accounts-section-nav" aria-label="Settings sections"><a href="#settings-profile">Profile</a><a href="#settings-password">Password</a><a href="#settings-appearance">Appearance</a>{user?.is_admin && user.org_id && <><a href="#settings-workspace">Workspace</a><a href="#settings-security">Security</a><a href="#settings-limits">Request limits</a><a href="#settings-export">Audit export</a></>}<a href="#settings-session">Session</a></nav>
      <div className="accounts-settings-content"><div id="settings-profile"><ProfileForm user={user} onUserUpdate={onUserUpdate} /></div><div id="settings-password"><PasswordForm /></div>
        <div id="settings-appearance"><Panel title="Appearance" description="Choose the theme that feels comfortable for your work."><div className="accounts-theme-options" role="group" aria-label="Workspace theme"><Button variant={darkMode ? "secondary" : "primary"} icon="sun" aria-pressed={!darkMode} onClick={() => setDarkMode(false)}>Light</Button><Button variant={darkMode ? "primary" : "secondary"} icon="moon" aria-pressed={darkMode} onClick={() => setDarkMode(true)}>Dark</Button></div></Panel></div>
        {user?.is_admin && user.org_id && <>{workspace.loading && !workspace.policy && <LoadingState label="Loading workspace settings" />}{workspace.error && <Notice tone="danger">{workspace.error}<Button variant="ghost" onClick={() => void workspace.reload()}>Retry workspace settings</Button></Notice>}{workspace.org && <div id="settings-workspace"><OrganizationForm org={workspace.org} onSaved={workspace.setOrg} /></div>}{workspace.policy && <><div id="settings-security"><SecurityForm policy={workspace.policy} onSaved={workspace.setPolicy} /></div><div id="settings-limits"><LimitsForm policy={workspace.policy} onSaved={workspace.setPolicy} /></div></>}<div id="settings-export"><AuditExport /></div></>}
        <div id="settings-session"><Panel title="Your session" description={`Signed in as ${user?.email || "your account"}.`}><div className="accounts-session-row"><p className="accounts-copy">Sign out when you finish working on a shared device.</p><Button variant="danger" icon="logout" onClick={async () => { if (await confirm({ title: "Sign out of your account?", description: "You can sign back in to continue working with your workspace.", confirmLabel: "Sign out" })) onLogout(); }}>Sign out</Button></div></Panel></div>
      </div>
    </div>{dialog}
  </div>;
}
