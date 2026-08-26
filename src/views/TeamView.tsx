import React, { useState, useEffect, useCallback } from "react";
import { api } from "../utils/api";
import { s } from "../styles/theme";
import type { components } from "../api-types";
type UserOut = components["schemas"]["UserOut"];
type AdminUserStats = components["schemas"]["AdminUserStats"];
export default function TeamView({ user }: { user: UserOut | null }) {
  const [members,setMembers]=useState<AdminUserStats[]>([]);
  const [q,setQ]=useState(""); const [roleFilter,setRoleFilter]=useState<string>("");
  const [error,setError]=useState(""); const [success,setSuccess]=useState("");
  const [inviteEmail,setInviteEmail]=useState(""); const [inviteName,setInviteName]=useState(""); const [inviteAdmin,setInviteAdmin]=useState(false); const [inviting,setInviting]=useState(false); const [showInvite,setShowInvite]=useState(false);
  const fetchMembers=useCallback(async()=>{ try{ const d=await api<AdminUserStats[]>("/admin/users/stats"); setMembers(d);}catch(e){ setError(e instanceof Error?e.message:String(e));} },[]);
  useEffect(()=>{ if(user?.is_admin) fetchMembers(); },[user,fetchMembers]);
  async function handleInvite(e:React.FormEvent){ e.preventDefault(); if(!inviteEmail.trim()||!inviteName.trim())return; setInviting(true); setError(""); setSuccess(""); try{ await api("/admin/users/invite",{method:"POST", body:{email:inviteEmail.trim(), full_name:inviteName.trim(), is_admin:inviteAdmin}}); setSuccess(`Invitation sent to ${inviteEmail}.`); setInviteEmail(""); setInviteName(""); setInviteAdmin(false); setShowInvite(false); fetchMembers();}catch(e){ setError(e instanceof Error?e.message:String(e));} finally{setInviting(false);} }
  async function updateMember(id:string, upd:Record<string,unknown>){ try{ await api(`/admin/users/${id}`,{method:"PATCH", body:upd}); setSuccess("Updated."); setTimeout(()=>setSuccess(""),2500); fetchMembers(); }catch(e){ setError(e instanceof Error?e.message:String(e)); } }
  async function removeMember(m:AdminUserStats){ if(!confirm(`Remove ${m.email}?`))return; try{ await api(`/admin/users/${m.id}`,{method:"DELETE"}); setSuccess(`${m.email} removed.`); fetchMembers(); }catch(e){ setError(e instanceof Error?e.message:String(e)); } }
  const fmt=(n:number)=>Number(n).toLocaleString();
  const filtered=members.filter(m=>{
    if(roleFilter==="admin" && !m.is_admin) return false;
    if(roleFilter==="member" && m.is_admin) return false;
    if(roleFilter==="active" && !m.is_active) return false;
    if(q && !(`${m.full_name} ${m.email}`.toLowerCase().includes(q.toLowerCase()))) return false;
    return true;
  });
  if(!user?.is_admin) return <div><div style={s.heroPanel}><div style={s.pageTitle}>Team & Access</div></div><div style={s.alert("error")}>Organisation Administrator required.</div></div>;
  return (
    <div>
      <div style={{ ...s.heroPanel, background:"linear-gradient(135deg,#ffffff 0%,#f8fafc 60%,#f0fdfa 100%)", border:"1px solid #e2e8f0", position:"relative", overflow:"hidden" }}>
        <div style={{ position:"absolute", inset:0, background:"radial-gradient(600px 280px at 85% 0%, rgba(15,118,110,0.07), transparent 60%)", pointerEvents:"none"}}/>
        <div style={{ position:"relative", display:"flex", justifyContent:"space-between", gap:16, flexWrap:"wrap", alignItems:"flex-start" }}>
          <div style={{ minWidth:300 }}>
            <div style={{ display:"flex", alignItems:"center", gap:10, marginBottom:6 }}>
              <div style={{ ...s.pageTitle, marginBottom:0 }}>Team</div>
              <span style={{ background:"#0f766e", color:"#fff", fontSize:10, fontWeight:800, letterSpacing:"0.06em", textTransform:"uppercase", padding:"3px 8px", borderRadius:999 }}>Linear • Slack</span>
              <span style={{ background:"#fff", border:"1px solid #e2e8f0", color:"#475569", fontSize:11, fontWeight:700, padding:"4px 10px", borderRadius:999 }}>{members.length} members</span>
            </div>
            <div style={{ color:"#405166", fontSize:14, lineHeight:1.6 }}>Invite, approve, and track usage. Presence • roles • token balance — Linear-grade density.</div>
          </div>
          <button style={{ ...s.btn("primary"), borderRadius:10, padding:"10px 18px", boxShadow:"0 8px 20px rgba(15,118,110,0.18)" }} onClick={()=>setShowInvite(v=>!v)}>+ Invite member</button>
        </div>
      </div>
      {error && <div style={{ ...s.alert("error"), marginBottom:12 }}>{error}</div>}
      {success && <div style={{ ...s.alert("success"), marginBottom:12 }}>{success}</div>}

      {/* Controls — Linear command bar */}
      <div style={{ display:"flex", gap:10, marginBottom:14, flexWrap:"wrap", alignItems:"center" }}>
        <div style={{ position:"relative", flex:"1 1 260px", minWidth:240 }}>
          <span style={{ position:"absolute", left:12, top:"50%", transform:"translateY(-50%)", color:"#8a9bb0", fontSize:12 }}></span>
          <input value={q} onChange={e=>setQ(e.target.value)} placeholder="Filter by name or email… (F)" style={{ ...s.input, paddingLeft:34, marginBottom:0, borderRadius:10, background:"#fff" }}/>
        </div>
        <div style={{ display:"flex", background:"#eef3f8", borderRadius:999, padding:3, gap:2 }}>
          {[
            {k:"", l:"All"},
            {k:"admin", l:"Admins"},
            {k:"member", l:"Members"},
            {k:"active", l:"Active"},
          ].map(o=>(
            <button key={o.k} onClick={()=>setRoleFilter(o.k)} style={{ padding:"6px 12px", borderRadius:999, border:"none", cursor:"pointer", fontSize:12, fontWeight:800, background: roleFilter===o.k?"#0f766e":"transparent", color: roleFilter===o.k?"#fff":"#405166" }}>{o.l}</button>
          ))}
        </div>
        <span style={{ fontSize:11, color:"#7b8a9d", marginLeft:"auto" }}>{filtered.length} shown</span>
      </div>

      {/* Invite inline — Slack style */}
      {showInvite && (
        <div style={{ ...s.card, marginBottom:14, borderColor:"#99f6e4", background:"linear-gradient(135deg,#fff 0%,#f0fdfa 100%)" }}>
          <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:12 }}>
            <div style={s.sectionTitle}>Invite to workspace</div>
            <button onClick={()=>setShowInvite(false)} style={{ width:28, height:28, borderRadius:8, border:"1px solid #e2e8f0", background:"#fff", cursor:"pointer" }}>x</button>
          </div>
          <form onSubmit={handleInvite} style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(200px,1fr))", gap:12, alignItems:"end" }}>
            <div><label style={s.label}>Full name</label><input style={s.input} placeholder="Jane Doe" value={inviteName} onChange={e=>setInviteName(e.target.value)} required/></div>
            <div><label style={s.label}>Work email</label><input type="email" style={s.input} placeholder="jane@company.com" value={inviteEmail} onChange={e=>setInviteEmail(e.target.value)} required/></div>
            <div><label style={s.label}>Role</label><div style={{ display:"flex", background:"#eef3f8", borderRadius:10, padding:3, gap:2 }}>
              <button type="button" onClick={()=>setInviteAdmin(false)} style={{ flex:1, padding:"8px 10px", borderRadius:8, border:"none", cursor:"pointer", fontSize:12, fontWeight:800, background: !inviteAdmin?"#0f766e":"transparent", color: !inviteAdmin?"#fff":"#405166" }}>Member</button>
              <button type="button" onClick={()=>setInviteAdmin(true)} style={{ flex:1, padding:"8px 10px", borderRadius:8, border:"none", cursor:"pointer", fontSize:12, fontWeight:800, background: inviteAdmin?"#0f766e":"transparent", color: inviteAdmin?"#fff":"#405166" }}>Admin</button>
            </div><div style={{ fontSize:10, color:"#7b8a9d", marginTop:4 }}>{inviteAdmin?"Transfers your admin — Linear handover":"Can chat & view logs"}</div></div>
            <button style={{ ...s.btn("primary"), borderRadius:10, height:42 }} type="submit" disabled={inviting}>{inviting?"Sending…":"Send invite --"}</button>
          </form>
          <div style={{ fontSize:11, color:"#64748b", marginTop:10 }}>Secure link to set password • Expires in 24h • SCIM-ready</div>
        </div>
      )}

      {/* Members — Linear table */}
      <div style={{ ...s.card, padding:0, overflow:"hidden" }}>
        <div style={{ overflowX:"auto" }}>
          <table style={{ ...s.table, minWidth:900 }}>
            <thead style={{ background:"#f8fafc" }}>
              <tr>{["Member","Role","Activity","Tokens","Requests","Status",""].map(h=> <th key={h} style={{ ...s.th, background:"transparent", fontSize:11 }}>{h}</th>)}</tr>
            </thead>
            <tbody>
              {filtered.map(m=>{
                const isYou=m.id===user.id;
                const online=m.last_login && (Date.now()-new Date(m.last_login).getTime()) < 300000;
                const usagePct = m.tokens_balance + m.tokens_used ? Math.min(100, Math.round((m.tokens_used/(m.tokens_balance+m.tokens_used))*100)) : 0;
                return (
                  <tr key={m.id} style={{ transition:"background .12s" }} onMouseEnter={e=>e.currentTarget.style.background="#f8fafc"} onMouseLeave={e=>e.currentTarget.style.background="transparent"}>
                    <td style={s.td}>
                      <div style={{ display:"flex", gap:10, alignItems:"center" }}>
                        <div style={{ position:"relative", width:36, height:36, borderRadius:10, background: isYou?"#0f766e":"#e2e8f0", color: isYou?"#fff":"#475569", display:"grid", placeItems:"center", fontWeight:800, fontSize:13, flexShrink:0 }}>{m.full_name.split(" ").map(w=>w[0]).join("").slice(0,2).toUpperCase()}<span style={{ position:"absolute", bottom:-2, right:-2, width:10, height:10, borderRadius:999, background: online?"#22c55e": m.is_active?"#94a3b8":"#ef4444", border:"2px solid #fff", boxShadow:"0 1px 4px rgba(0,0,0,0.12)" }} /></div>
                        <div style={{ minWidth:0 }}>
                          <div style={{ fontWeight:800, color:"#102033", fontSize:13, display:"flex", gap:6, alignItems:"center" }}>{m.full_name} {isYou && <span style={{ fontSize:10, fontWeight:800, color:"#0f766e", background:"#ecfdf5", border:"1px solid #a7f3d0", padding:"2px 6px", borderRadius:999 }}>You</span>}</div>
                          <div style={{ fontSize:12, color:"#7b8a9d", whiteSpace:"nowrap", overflow:"hidden", textOverflow:"ellipsis", maxWidth:180 }}>{m.email}</div>
                        </div>
                      </div>
                    </td>
                    <td style={s.td}>
                      {isYou ? <span style={{ fontSize:12, fontWeight:700, color:"#0f766e" }}>Admin • You</span> :
                        <select value={m.is_admin ? "admin" : "member"} onChange={e=>updateMember(m.id,{is_admin:e.target.value==="admin"})} style={{ ...s.input, padding:"6px 10px", width:"auto", fontSize:12, fontWeight:700, borderRadius:8 }}>
                          <option value="member">Member</option>
                          <option value="admin">Admin</option>
                        </select>
                      }
                    </td>
                    <td style={{ ...s.td, fontSize:12 }}>
                      <div style={{ fontWeight:600, color:"#102033" }}>{m.last_login ? new Date(m.last_login).toLocaleDateString() : "Never"}</div>
                      <div style={{ fontSize:11, color: online?"#16a34a":"#7b8a9d", fontWeight:700 }}>{online?" Online": m.last_login ? new Date(m.last_login).toLocaleTimeString() : "—"}</div>
                    </td>
                    <td style={s.td}>
                      <div style={{ fontSize:12, fontWeight:800, color:"#102033" }}>{fmt(m.tokens_used)} used</div>
                      <div style={{ fontSize:11, color:"#7b8a9d" }}>{fmt(m.tokens_balance)} left</div>
                      <div style={{ marginTop:4, height:4, background:"#e7eef6", borderRadius:999, overflow:"hidden", width:80 }}><div style={{ width:`${usagePct}%`, height:"100%", background: usagePct>80?"#f43f5e": usagePct>60?"#f59e0b":"#0f766e", borderRadius:999 }}/></div>
                    </td>
                    <td style={s.td}>
                      <div style={{ fontSize:12, fontWeight:700 }}>{fmt(m.total_requests)} <span style={{ fontWeight:400, color:"#7b8a9d" }}>req</span></div>
                      <div style={{ fontSize:11, color: m.total_blocked ? "#dc2626" : "#7b8a9d" }}>{fmt(m.total_blocked)} blocked</div>
                    </td>
                    <td style={s.td}>
                      {isYou ? <span style={s.badge("delivered")}>Active</span> :
                        <button style={{ ...s.btn(m.is_active?"secondary":"primary"), padding:"6px 12px", fontSize:11, borderRadius:8 }} onClick={()=>updateMember(m.id,{is_active:!m.is_active})}>{m.is_active?"Revoke":"Restore"}</button>
                      }
                    </td>
                    <td style={{ ...s.td, textAlign:"right" }}>
                      {m.id!==user.id && <button style={{ ...s.btn("danger"), padding:"6px 12px", fontSize:11, borderRadius:8 }} onClick={()=>removeMember(m)}>Remove</button>}
                    </td>
                  </tr>
                );
              })}
              {filtered.length===0 && <tr><td colSpan={7} style={{ ...s.td, textAlign:"center", padding:28, color:"#7b8a9d" }}>No members match • try "All"</td></tr>}
            </tbody>
          </table>
        </div>
        <div style={{ padding:"12px 18px", background:"#f8fafc", borderTop:"1px solid #eef3f8", display:"flex", gap:8, flexWrap:"wrap", alignItems:"center" }}>
          <span style={{ fontSize:11, color:"#7b8a9d" }}>{members.length} members • {members.filter(m=>m.is_admin).length} admins • Presence = last login &lt;5m</span>
          <a href="#" style={{ marginLeft:"auto", fontSize:11, fontWeight:700, color:"#6366f1", textDecoration:"none" }}>Invite via SCIM --</a>
        </div>
      </div>
    </div>
  );
}
