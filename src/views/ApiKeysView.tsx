import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { api } from "../utils/api";
import { trackEvent } from "../utils/analytics";
import type { components } from "../api-types";
import { Badge, Button, Dialog, EmptyState, Field, LoadingState, Notice, PageHeader, Panel, TableWrap, useConfirmation } from "../components/ui";
import "../styles/security.css";

type APIKeyOut = components["schemas"]["APIKeyOut"];
const SCOPE_CATALOG = [
  { scope: "chat", desc: "Send prompts via /chat", group: "Gateway" },
  { scope: "chat:stream", desc: "Stream via /chat/stream", group: "Gateway" },
  { scope: "logs:read", desc: "Read request logs", group: "Observability" },
  { scope: "analytics", desc: "Read analytics", group: "Observability" },
  { scope: "policy:read", desc: "Read policy", group: "Policy" },
  { scope: "policy:write", desc: "Edit policy", group: "Policy" },
  { scope: "skills:read", desc: "Scan skills", group: "Skills" },
  { scope: "skills:write", desc: "Manage rejections", group: "Skills" },
  { scope: "admin", desc: "Organization administration", group: "Admin" },
];
function expiryLabel(value?: string | null) {
  if (!value) return "No expiration";
  const remaining = new Date(value).getTime() - Date.now();
  if (remaining <= 0) return "Expired";
  if (remaining < 86400000) return `${Math.max(1, Math.ceil(remaining / 3600000))} hours left`;
  return new Date(value).toLocaleDateString();
}

export default function ApiKeysView() {
  const [keys, setKeys] = useState<APIKeyOut[]>([]);
  const [newName, setNewName] = useState("");
  const [newExpiry, setNewExpiry] = useState("");
  const [newScopes, setNewScopes] = useState<string[]>(["chat"]);
  const [showCreate, setShowCreate] = useState(false);
  const [rawKey, setRawKey] = useState("");
  const [copied, setCopied] = useState("");
  const [error, setError] = useState("");
  const [createError, setCreateError] = useState("");
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [revoking, setRevoking] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const copyTimer = useRef<number | undefined>(undefined);
  const { confirm, dialog } = useConfirmation();
  const load = useCallback(async () => {
    setLoading(true);
    try { setKeys(await api<APIKeyOut[]>("/api-keys")); setError(""); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => () => window.clearTimeout(copyTimer.current), []);
  async function copy(value: string, message: string) {
    try { await navigator.clipboard.writeText(value); setCopied(message); window.clearTimeout(copyTimer.current); copyTimer.current = window.setTimeout(() => setCopied(""), 2500); }
    catch { setError("Copy is unavailable. Select the value and copy it manually."); }
  }
  async function create(event: FormEvent) {
    event.preventDefault();
    if (creating || !newName.trim()) return;
    setCreateError(""); setCreating(true);
    try {
      const data = await api<components["schemas"]["APIKeyCreated"]>("/api-keys", { method: "POST", body: { name: newName.trim(), scopes: newScopes, expires_at: newExpiry || null } });
      trackEvent("api_key_created", { name: newName.trim() });
      setRawKey(data.raw_key); setCopied(""); setNewName(""); setNewExpiry(""); setNewScopes(["chat"]); setShowCreate(false); await load();
    } catch (reason) { setCreateError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setCreating(false); }
  }
  async function revoke(key: APIKeyOut) {
    if (!await confirm({ title: `Revoke ${key.name}?`, description: "Apps using this key will immediately lose access. Create and deploy a replacement before revoking a key in use.", confirmLabel: "Revoke key", danger: true })) return;
    setRevoking(key.id); setError("");
    try { await api(`/api-keys/${key.id}`, { method: "DELETE" }); trackEvent("api_key_revoked"); setCopied(`${key.name} revoked.`); await load(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setRevoking(null); }
  }
  const active = keys.filter(key => key.is_active && (!key.expires_at || new Date(key.expires_at).getTime() > Date.now()));
  const visible = keys.filter(key => `${key.name} ${key.key_prefix} ${(key.scopes || []).join(" ")}`.toLowerCase().includes(query.toLowerCase()));
  return <div className="security-page">
    <PageHeader eyebrow="ACCESS MANAGEMENT" title="API keys" description="Connect your apps to the gateway with scoped, revocable credentials." actions={<Button variant="primary" icon="plus" onClick={() => { setCreateError(""); setShowCreate(true); }}>Create key</Button>} />
    {error && <Notice tone="danger">{error}</Notice>}
    {copied && <Notice tone="success">{copied}</Notice>}
    {rawKey && <Panel title="Your new key is ready" description="Copy it now. The complete key is shown only once." actions={<Button variant="ghost" onClick={() => setRawKey("")}>Dismiss</Button>} className="security-new-key">
      <div className="security-secret-row"><code className="security-code-value">{rawKey}</code><Button icon="copy" onClick={() => copy(rawKey, "API key copied.")}>Copy key</Button></div>
      <p className="security-hint">Store this key securely. Use gateway keys starting with <code>grg_</code> for your app; keep provider credentials in server configuration.</p>
    </Panel>}
    <div className="security-summary-grid">
      <div><span>Active keys</span><strong>{loading ? "—" : active.length}</strong><small>Ready to authenticate requests</small></div>
      <div><span>Total keys</span><strong>{loading ? "—" : keys.length}</strong><small>Including revoked and expired keys</small></div>
      <div><span>Requests served</span><strong>{loading ? "—" : keys.reduce((sum, key) => sum + key.total_requests, 0).toLocaleString()}</strong><small>Across your listed keys</small></div>
    </div>
    <Panel title="Gateway credentials" description="Only key prefixes are stored in this list. Full keys cannot be retrieved." actions={<Button variant="ghost" icon="refresh" loading={loading} onClick={load}>Refresh</Button>}>
      <Field label="Find a key" htmlFor="key-search"><input id="key-search" className="ui-input" value={query} onChange={event => setQuery(event.target.value)} placeholder="Search by name, prefix, or scope" type="search" /></Field>
      {loading ? <LoadingState label="Loading API keys…" /> : !visible.length ? <EmptyState icon="key" title={keys.length ? "No matching keys" : "Your first connection starts here"} description={keys.length ? "Try another name or scope." : "Create a key with only the permissions your app needs."} action={!keys.length ? <Button icon="plus" onClick={() => setShowCreate(true)}>Create key</Button> : undefined} /> : <TableWrap label="API keys"><table className="ui-table security-keys-table"><thead><tr><th scope="col">Key</th><th scope="col">Permissions</th><th scope="col">Activity</th><th scope="col">Expiration</th><th scope="col">Status</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead><tbody>{visible.map(key => {
        const expired = Boolean(key.expires_at && new Date(key.expires_at).getTime() <= Date.now());
        return <tr key={key.id}><td><strong>{key.name}</strong><div className="security-key-prefix"><code>{key.key_prefix}••••</code><Button variant="ghost" icon="copy" aria-label={`Copy ${key.name} prefix`} onClick={() => copy(key.key_prefix, "Key prefix copied.")} /></div></td><td><div className="security-badges">{(key.scopes || ["chat"]).map(scope => <Badge key={scope}>{scope}</Badge>)}</div></td><td><strong>{key.total_requests.toLocaleString()} requests</strong><small>{key.total_blocked.toLocaleString()} blocked</small><small>{key.last_used_at ? `Last used ${new Date(key.last_used_at).toLocaleString()}` : "Not used yet"}</small></td><td>{expiryLabel(key.expires_at)}</td><td><Badge tone={!key.is_active || expired ? "neutral" : "success"}>{!key.is_active ? "Revoked" : expired ? "Expired" : "Active"}</Badge></td><td>{key.is_active && !expired && <Button variant="danger" loading={revoking === key.id} disabled={Boolean(revoking)} onClick={() => revoke(key)}>Revoke</Button>}</td></tr>;
      })}</tbody></table></TableWrap>}
    </Panel>
    <Dialog open={showCreate} onClose={() => { if (!creating) setShowCreate(false); }} dismissible={!creating} title="Create an API key" description="Give this connection a name and choose its permissions." size="lg">
      <form onSubmit={create} className="security-form">
        {createError && <Notice tone="danger">{createError}</Notice>}
        <div className="security-two-columns"><Field label="Key name" htmlFor="key-name" hint="A recognizable label, such as production or CI."><input id="key-name" className="ui-input" value={newName} onChange={event => setNewName(event.target.value)} placeholder="Production gateway" autoFocus required disabled={creating} /></Field><Field label="Expiration date (optional)" htmlFor="key-expiry" hint="Leave blank for a key without an expiration date."><input id="key-expiry" className="ui-input" type="date" value={newExpiry} onChange={event => setNewExpiry(event.target.value)} disabled={creating} /></Field></div>
        <fieldset className="security-fieldset" disabled={creating}><legend>Permissions</legend><p className="security-hint">Select the minimum access this app requires.</p><div className="security-scope-grid">{SCOPE_CATALOG.map(option => <label key={option.scope} className="security-scope-option"><input type="checkbox" checked={newScopes.includes(option.scope)} onChange={event => setNewScopes(current => event.target.checked ? [...current, option.scope] : current.filter(scope => scope !== option.scope))} /><span><strong>{option.scope}</strong><small>{option.desc}</small><small>{option.group}</small></span></label>)}</div></fieldset>
        <div className="security-actions"><Button variant="secondary" type="button" onClick={() => setShowCreate(false)} disabled={creating}>Cancel</Button><Button variant="primary" type="submit" icon="plus" loading={creating} disabled={!newName.trim()}>Create key</Button></div>
      </form>
    </Dialog>
    {dialog}
  </div>;
}
