import React, { useState, useEffect, useCallback } from "react";
import { api, maskGatewayKey } from "../utils/api";
import { trackEvent } from "../utils/analytics";
import { s } from "../styles/theme";
import type { components } from "../api-types";

type APIKeyOut = components["schemas"]["APIKeyOut"];

const SCOPE_CATALOG: { scope: string; desc: string; group: string }[] = [
  { scope: "chat", desc: "Send prompts via /chat", group: "Gateway" },
  { scope: "chat:stream", desc: "Stream via /chat/stream", group: "Gateway" },
  { scope: "logs:read", desc: "Read request logs", group: "Observability" },
  { scope: "analytics", desc: "Read analytics", group: "Observability" },
  { scope: "policy:read", desc: "Read policy", group: "Policy" },
  { scope: "policy:write", desc: "Edit policy", group: "Policy" },
  { scope: "skills:read", desc: "Scan skills", group: "Skills" },
  { scope: "skills:write", desc: "Manage rejections", group: "Skills" },
  { scope: "admin", desc: "Org admin", group: "Admin" },
];

function timeAgo(iso: string | null | undefined) {
  if (!iso) return "Never";
  const d = new Date(iso);
  const diff = (Date.now() - d.getTime())/1000;
  if (diff < 60) return "now";
  if (diff < 3600) return `${Math.floor(diff/60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff/3600)}h ago`;
  if (diff < 604800) return `${Math.floor(diff/86400)}d ago`;
  return d.toLocaleDateString();
}
function expiresIn(iso: string | null | undefined) {
  if (!iso) return { label: "Never", color: "#7b8a9d" };
  const diff = (new Date(iso).getTime() - Date.now())/1000;
  if (diff < 0) return { label: "Expired", color: "#be123c" };
  if (diff < 86400) return { label: `${Math.floor(diff/3600)}h left`, color: "#d97706" };
  if (diff < 604800) return { label: `${Math.floor(diff/86400)}d left`, color: "#0f766e" };
  return { label: new Date(iso!).toLocaleDateString(), color: "#7b8a9d" };
}

export default function ApiKeysView() {
  const [keys, setKeys] = useState<APIKeyOut[]>([]);
  const [newName, setNewName] = useState("");
  const [newExpiry, setNewExpiry] = useState("");
  const [newScopes, setNewScopes] = useState<string[]>(["chat"]);
  const [showCreate, setShowCreate] = useState(false);
  const [rawKey, setRawKey] = useState("");
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [revoking, setRevoking] = useState<string | null>(null);

  const load = useCallback(() => {
    api<APIKeyOut[]>("/api-keys").then(setKeys).catch((e: Error)=>setError(e.message));
  }, []);
  useEffect(()=>{ load(); }, [load]);

  async function create() {
    if (!newName.trim()) return;
    setError(""); setLoading(true);
    try {
      const data = await api<components["schemas"]["APIKeyCreated"]>("/api-keys", { method:"POST", body:{ name: newName.trim(), scopes: newScopes, expires_at: newExpiry || null }});
      trackEvent("api_key_created", { name: newName.trim() });
      setRawKey(data.raw_key);
      setNewName(""); setNewExpiry(""); setNewScopes(["chat"]); setShowCreate(false);
      load();
    } catch(e){ setError(e instanceof Error ? e.message : String(e)); }
    finally{ setLoading(false); }
  }
  async function revoke(id: string) {
    if (!confirm("Revoke this key? Apps using it will get 401 immediately.")) return;
    setRevoking(id);
    try { await api("/api-keys/" + id, { method:"DELETE" }); trackEvent("api_key_revoked"); load(); }
    catch(e){ setError(e instanceof Error ? e.message : String(e)); }
    finally{ setRevoking(null); }
  }

  return (
    <div>
      {/* Hero — GitHub + Stripe */}
      <div style={{ ...s.heroPanel, background:"linear-gradient(135deg,#ffffff 0%,#f8fafc 60%,#f0fdfa 100%)", border:"1px solid #e2e8f0", position:"relative", overflow:"hidden" }}>
        <div style={{ position:"absolute", inset:0, background:"radial-gradient(500px 220px at 92% 0%, rgba(99,102,241,0.08), transparent 60%)", pointerEvents:"none"}}/>
        <div style={{ position:"relative", display:"flex", justifyContent:"space-between", gap:16, flexWrap:"wrap", alignItems:"flex-start" }}>
          <div style={{ minWidth:300 }}>
            <div style={{ display:"flex", alignItems:"center", gap:10, marginBottom:6 }}>
              <div style={{ ...s.pageTitle, marginBottom:0 }}>API keys</div>
              <span style={{ background:"#111827", color:"#fff", fontSize:10, fontWeight:800, letterSpacing:"0.06em", textTransform:"uppercase", padding:"3px 8px", borderRadius:999 }}>GitHub • Stripe</span>
            </div>
            <div style={{ color:"#405166", fontSize:14, lineHeight:1.6, maxWidth:620 }}>
              Scoped <code style={{ background:"#f1f5f9", border:"1px solid #e2e8f0", padding:"1px 6px", borderRadius:6, fontSize:12 }}>grg_…</code> keys for apps. Keep them secret — like GitHub PATs.
              <span style={{ color:"#dc2626", fontWeight:700 }}> Never commit to git.</span>
            </div>
            <div style={{ display:"flex", gap:8, marginTop:10, flexWrap:"wrap" }}>
              <span style={{ fontSize:11, fontWeight:700, color:"#6366f1", background:"#eef2ff", border:"1px solid #c7d2fe", padding:"5px 9px", borderRadius:999 }}> Hashed with bcrypt</span>
              <span style={{ fontSize:11, fontWeight:700, color:"#0f766e", background:"#ecfdf5", border:"1px solid #a7f3d0", padding:"5px 9px", borderRadius:999 }}>{keys.filter(k=>k.is_active).length} active • {keys.length} total</span>
            </div>
          </div>
          <button style={{ ...s.btn("primary"), borderRadius:10, padding:"10px 18px", boxShadow:"0 8px 20px rgba(17,24,39,0.14)" }} onClick={()=>setShowCreate(true)}>+ New key</button>
        </div>
      </div>

      {error && <div style={{ ...s.alert("error"), marginBottom:14 }}>{error}</div>}
      {rawKey && (
        <div style={{ background:"#f0fdf4", border:"1px solid #86efac", borderRadius:12, padding:16, marginBottom:16, display:"flex", gap:12, alignItems:"flex-start", flexWrap:"wrap" }}>
          <div style={{ width:36, height:36, borderRadius:10, background:"#0f766e", color:"#fff", display:"grid", placeItems:"center", fontSize:16, flexShrink:0 }}></div>
          <div style={{ minWidth:260, flex:1 }}>
            <div style={{ fontSize:13, fontWeight:850, color:"#065f46" }}>Key created — copy now, it won't be shown again.</div>
            <code style={{ display:"block", marginTop:8, padding:"10px 12px", background:"#fff", border:"1px solid #a7f3d0", borderRadius:8, fontSize:12, wordBreak:"break-all", color:"#0f766e", fontWeight:700 }}>{rawKey}</code>
            <div style={{ fontSize:11, color:"#065f46", marginTop:6 }}>Stored as bcrypt hash • prefix <code>{rawKey.slice(0,12)}</code> is what you'll see below.</div>
          </div>
          <div style={{ display:"flex", gap:8, flexShrink:0 }}>
            <button style={{ ...s.btn("primary"), borderRadius:8, background: copied ? "#065f46" : undefined }} onClick={()=>{ navigator.clipboard.writeText(rawKey); setCopied(true); setTimeout(()=>setCopied(false),2000); }}>{copied ? "Copied" : "Copy"}</button>
            <button style={s.btn("secondary")} onClick={()=>setRawKey("")}>Dismiss</button>
          </div>
        </div>
      )}

      {/* Create drawer — Stripe style */}
      {showCreate && (
        <div style={{ ...s.card, marginBottom:16, borderColor:"#6366f1", background:"linear-gradient(135deg,#fff 0%,#f5f3ff 100%)", position:"relative" }}>
          <button onClick={()=>setShowCreate(false)} style={{ position:"absolute", top:12, right:12, width:28, height:28, borderRadius:8, border:"1px solid #e2e8f0", background:"#fff", cursor:"pointer" }}>x</button>
          <div style={s.sectionTitle}>Create new key</div>
          <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(240px,1fr))", gap:12, marginTop:12 }}>
            <div>
              <label style={s.label}>Name <span style={{ color:"#dc2626" }}>*</span></label>
              <input style={s.input} placeholder="production • ci • playground" value={newName} onChange={e=>setNewName(e.target.value)} onKeyDown={e=>e.key==="Enter"&&create()} autoFocus />
              <div style={{ fontSize:11, color:"#7b8a9d", marginTop:6 }}>Human label — not secret.</div>
            </div>
            <div>
              <label style={s.label}>Expires (optional)</label>
              <input type="date" style={s.input} value={newExpiry} onChange={e=>setNewExpiry(e.target.value)} />
              <div style={{ fontSize:11, color:"#7b8a9d", marginTop:6 }}>Leave empty for no expiry.</div>
            </div>
          </div>
          <div style={{ marginTop:14 }}>
            <label style={s.label}>Scopes</label>
            <div style={{ display:"flex", flexWrap:"wrap", gap:8 }}>
              {SCOPE_CATALOG.map(o=>(
                <label key={o.scope} style={{ display:"inline-flex", alignItems:"center", gap:6, padding:"7px 12px", borderRadius:999, border: newScopes.includes(o.scope) ? "1px solid #6366f1" : "1px solid #e2e8f0", background: newScopes.includes(o.scope) ? "#eef2ff" : "#fff", color: newScopes.includes(o.scope) ? "#4338ca" : "#475569", fontSize:12, fontWeight:700, cursor:"pointer" }}>
                  <input type="checkbox" checked={newScopes.includes(o.scope)} onChange={e=>setNewScopes(v=> e.target.checked ? [...v, o.scope] : v.filter(x=>x!==o.scope))} style={{ accentColor:"#6366f1" }}/>
                  {o.scope}
                  <span style={{ fontSize:10, color:"#7b8a9d", fontWeight:600 }}>· {o.group}</span>
                </label>
              ))}
            </div>
            <div style={{ fontSize:11, color:"#7b8a9d", marginTop:8 }}>Least privilege — e.g. read-only CI gets <code>logs:read</code> only.</div>
          </div>
          <div style={{ display:"flex", gap:8, marginTop:14 }}>
            <button style={{ ...s.btn("primary"), borderRadius:10, opacity: loading?0.6:1 }} onClick={create} disabled={loading || !newName.trim()}>{loading ? "Creating…" : "Create key"}</button>
            <button style={s.btn("secondary")} onClick={()=>setShowCreate(false)}>Cancel</button>
          </div>
        </div>
      )}

      {/* Keys table — GitHub style */}
      <div style={{ ...s.card, padding:0, overflow:"hidden" }}>
        <div style={{ padding:"14px 18px", display:"flex", justifyContent:"space-between", alignItems:"center", borderBottom:"1px solid #eef3f8", background:"#f8fafc" }}>
          <div style={{ fontSize:13, fontWeight:800, color:"#102033" }}>{keys.length} keys</div>
          <div style={{ display:"flex", gap:6, alignItems:"center", fontSize:11, color:"#7b8a9d" }}>
            <span style={{ width:8, height:8, borderRadius:999, background:"#22c55e", display:"inline-block" }}/> bcrypt • prefix shown
          </div>
        </div>
        <div style={{ overflowX:"auto" }}>
          <table style={{ ...s.table, minWidth:900 }}>
            <thead style={{ background:"#f8fafc" }}>
              <tr>{["Key","Last used","Expires","Scopes","Usage","Status",""].map(h=> <th key={h} style={{ ...s.th, background:"transparent", fontSize:11 }}>{h}</th>)}</tr>
            </thead>
            <tbody>
              {keys.map(k=>{
                const exp = expiresIn(k.expires_at);
                const isExpired = k.expires_at && new Date(k.expires_at).getTime() < Date.now();
                return (
                  <tr key={k.id} style={{ opacity: !k.is_active || isExpired ? 0.6 : 1, background: isExpired ? "#fff1f2" : undefined, transition:"background .12s" }} onMouseEnter={e=>e.currentTarget.style.background="#f8fafc"} onMouseLeave={e=>e.currentTarget.style.background=isExpired ? "#fff1f2" : "transparent"}>
                    <td style={s.td}>
                      <div style={{ fontWeight:800, color:"#102033", fontSize:13 }}>{k.name}</div>
                      <div style={{ display:"flex", gap:6, alignItems:"center", marginTop:4 }}>
                        <code style={{ fontSize:11, background:"#0f172a", color:"#e2e8f0", padding:"3px 7px", borderRadius:6, fontWeight:700, letterSpacing:"0.04em" }}>{maskGatewayKey(k.key_prefix + "0".repeat(24))}</code>
                        <button onClick={()=>navigator.clipboard.writeText(k.key_prefix)} title="Copy prefix" style={{ border:"1px solid #e2e8f0", background:"#fff", borderRadius:6, padding:"2px 6px", cursor:"pointer", fontSize:11 }}>Copy</button>
                        <span style={{ fontSize:10, color:"#7b8a9d" }}>• {k.key_prefix}</span>
                      </div>
                    </td>
                    <td style={s.td}>
                      <div style={{ fontSize:13, fontWeight:700, color:"#102033" }}>{timeAgo(k.last_used_at)}</div>
                      <div style={{ fontSize:11, color:"#7b8a9d" }}>{k.last_used_at ? new Date(k.last_used_at).toLocaleString() : "—"}</div>
                    </td>
                    <td style={s.td}><span style={{ fontSize:12, fontWeight:700, color: exp.color }}>{exp.label}</span></td>
                    <td style={{ ...s.td, maxWidth:240 }}>
                      <div style={{ display:"flex", flexWrap:"wrap", gap:4 }}>
                        {(k.scopes || ["chat"]).slice(0,4).map(sc=>(
                          <span key={sc} style={{ fontSize:10, fontWeight:700, padding:"3px 7px", borderRadius:999, border:"1px solid #e2e8f0", background:"#f8fafc", color:"#334155" }}>{sc}</span>
                        ))}
                        {(k.scopes?.length || 0) > 4 && <span style={{ fontSize:10, color:"#7b8a9d" }}>+{k.scopes.length-4}</span>}
                      </div>
                    </td>
                    <td style={s.td}>
                      <div style={{ fontSize:12, fontWeight:700, color:"#0f766e" }}>{k.total_requests.toLocaleString()} req</div>
                      <div style={{ fontSize:11, color: k.total_blocked ? "#dc2626" : "#7b8a9d" }}>{k.total_blocked.toLocaleString()} blocked</div>
                      <div style={{ marginTop:4, height:4, background:"#e7eef6", borderRadius:999, overflow:"hidden", width:80 }}><div style={{ width: `${Math.min(100, k.total_requests ? (k.total_requests/(k.total_requests+1))*100 : 0)}%`, height:"100%", background:"#6366f1" }}/></div>
                    </td>
                    <td style={s.td}>
                      {isExpired ? <span style={{ ...s.badge("error") }}>expired</span> :
                       k.is_active ? <span style={{ display:"inline-flex", alignItems:"center", gap:6, background:"#ecfdf5", border:"1px solid #a7f3d0", color:"#065f46", padding:"4px 10px", borderRadius:999, fontSize:11, fontWeight:800 }}><span style={{ width:6, height:6, borderRadius:999, background:"#10b981", boxShadow:"0 0 0 4px rgba(16,185,129,0.18)" }}/> active</span> :
                       <span style={s.badge("error")}>revoked</span>}
                    </td>
                    <td style={{ ...s.td, textAlign:"right" }}>
                      {k.is_active && !isExpired ? <button style={{ ...s.btn("danger"), padding:"6px 12px", fontSize:11, borderRadius:8 }} onClick={()=>revoke(k.id)} disabled={revoking===k.id}>{revoking===k.id ? "…" : "Revoke"}</button> : <span style={{ fontSize:11, color:"#7b8a9d" }}>—</span>}
                    </td>
                  </tr>
                );
              })}
              {keys.length===0 && <tr><td colSpan={7} style={{ ...s.td, textAlign:"center", padding:28 }}><div style={{ fontSize:32, marginBottom:8 }}></div><div style={{ fontWeight:800, color:"#102033" }}>No keys yet</div><div style={{ fontSize:13, color:"#7b8a9d", marginTop:4 }}>Create your first <code>grg_…</code> key to call <code>/chat</code>.</div><button style={{ ...s.btn("primary"), marginTop:12, borderRadius:8 }} onClick={()=>setShowCreate(true)}>Create key</button></td></tr>}
            </tbody>
          </table>
        </div>
        <div style={{ padding:"12px 18px", background:"#f8fafc", borderTop:"1px solid #eef3f8", display:"flex", gap:8, flexWrap:"wrap", alignItems:"center" }}>
          <span style={{ fontSize:11, color:"#7b8a9d", lineHeight:1.5 }}> Keys are bcrypt-hashed. <b>Copy once.</b> Rotate every 90 days. Use <code style={{ background:"#fff", border:"1px solid #e2e8f0", padding:"1px 5px", borderRadius:4 }}>grg_</code> not <code style={{ background:"#fff1f2", border:"1px solid #fecdd3", padding:"1px 5px", borderRadius:4 }}>gsk_/sk-</code>.</span>
          <a href="https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens" target="_blank" rel="noreferrer" style={{ marginLeft:"auto", fontSize:11, fontWeight:700, color:"#6366f1" }}>GitHub PAT docs --</a>
        </div>
      </div>
    </div>
  );
}
