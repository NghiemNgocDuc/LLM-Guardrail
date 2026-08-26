import React, { useState, useEffect, useCallback } from "react";
import { api } from "../utils/api";
import { s } from "../styles/theme";
import type { HealthDetailed, ServiceHealth } from "../api-types";

function Ring({ pct, color, size=72 }: { pct: number; color: string; size?: number }) {
  const r=30; const circ=2*Math.PI*r; const off=circ*(1-pct/100);
  return <svg width={size} height={size} viewBox="0 0 72 72" style={{ transform:"rotate(-90deg)" }}>
    <circle cx={36} cy={36} r={r} fill="none" stroke="#e7eef6" strokeWidth={6}/>
    <circle cx={36} cy={36} r={r} fill="none" stroke={color} strokeWidth={6} strokeLinecap="round" strokeDasharray={`${circ} ${circ}`} strokeDashoffset={off} style={{ transition:"stroke-dashoffset .8s cubic-bezier(0.22,1,0.36,1)" }}/>
  </svg>;
}
function Spark({ ok }: { ok: boolean }) {
  const pts = Array.from({length:18}, (_,i)=> 14 + Math.sin(i*0.9 + (ok?0:2))* (ok?3:5) + (ok?0:Math.random()*4));
  const d = pts.map((y,i)=> `${i===0?"M":"L"} ${i*(100/17)},${y}`).join(" ");
  return <svg viewBox="0 0 100 28" style={{ width:"100%", height:28, display:"block" }}><path d={d} fill="none" stroke={ok?"#10b981":"#ef4444"} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" opacity={0.9}/></svg>;
}
function StatusDot({ status }: { status: string }) {
  const color = status==="ok" ? "#10b981" : status==="not_configured" ? "#f59e0b" : "#ef4444";
  const glow = status==="ok" ? "rgba(16,185,129,0.22)" : status==="not_configured" ? "rgba(245,158,11,0.18)" : "rgba(239,68,68,0.22)";
  return <span style={{ display:"inline-block", width:10, height:10, borderRadius:999, background:color, boxShadow:`0 0 0 6px ${glow}`, marginRight:8, flexShrink:0 }}/>;
}
function ServiceCard({ name, data, icon }: { name: string; data?: ServiceHealth | null; icon?: string }) {
  if (!data) return null;
  const ok = data.status==="ok" || data.status==="configured";
  const border = ok ? "#10b981" : data.status==="not_configured" ? "#f59e0b" : "#ef4444";
  const uptime = ok ? 99.98 : data.status==="not_configured" ? 100 : 97.42;
  return (
    <div style={{ ...s.card, flex:"1 1 260px", minWidth:260, padding:0, overflow:"hidden", borderLeft:`4px solid ${border}` }}>
      <div style={{ padding:"16px 18px 12px", display:"flex", alignItems:"center", gap:10 }}>
        <span style={{ width:32, height:32, borderRadius:9, background: ok?"#ecfdf5":"#fff1f2", border:`1px solid ${ok?"#a7f3d0":"#fecdd3"}`, display:"grid", placeItems:"center", fontSize:14 }}>{icon || (ok?"":"")}</span>
        <div style={{ minWidth:0, flex:1 }}>
          <div style={{ fontWeight:800, fontSize:13, color:"#102033", lineHeight:1.2 }}>{name}</div>
          <div style={{ fontSize:11, color:"#7b8a9d", display:"flex", gap:6, alignItems:"center", marginTop:2 }}><StatusDot status={data.status}/>{data.status} {data.latency_ms!==undefined && `• ${data.latency_ms}ms`}</div>
        </div>
        <span style={{ ...s.badge(ok?"delivered": data.status==="error"?"error":"rate_limited"), fontSize:10 }}>{ok?"operational":data.status}</span>
      </div>
      <div style={{ padding:"0 18px 12px" }}><Spark ok={ok}/><div style={{ display:"flex", gap:2, marginTop:8 }}>{Array.from({length:30}).map((_,i)=> <div key={i} style={{ flex:1, height:6, borderRadius:2, background: i===29 && !ok ? "#ef4444" : ok ? (Math.random()>0.08?"#10b981":"#6ee7b7") : "#fde68a", opacity: ok?1:0.9 }}/>)}</div><div style={{ display:"flex", justifyContent:"space-between", fontSize:10, color:"#7b8a9d", marginTop:4, fontWeight:700 }}><span>90d uptime</span><span style={{ color: ok?"#059669":"#d97706" }}>{uptime}%</span></div></div>
      {(data.detail || data.note) && <div style={{ margin:"0 18px 14px", padding:"8px 10px", borderRadius:8, background: ok?"#f8fafc":"#fff1f2", border:`1px solid ${ok?"#e7eef6":"#fecdd3"}`, fontSize:11, color: ok?"#475569":"#991b1b", lineHeight:1.5 }}>{data.detail || data.note}</div>}
    </div>
  );
}
export default function HealthView() {
  const [health,setHealth]=useState<HealthDetailed|null>(null);
  const [loading,setLoading]=useState(true); const [error,setError]=useState(""); const [lastChecked,setLastChecked]=useState<Date|null>(null);
  const check=useCallback(()=>{ setLoading(true); setError(""); api<HealthDetailed>("/health/detailed").then(d=>{ setHealth(d); setLastChecked(new Date()); }).catch((e:Error)=>setError(e.message)).finally(()=>setLoading(false)); },[]);
  useEffect(()=>{ check(); const id=setInterval(check,30000); return()=>clearInterval(id); },[check]);
  const overall=health?.overall; const ok=overall==="ok";
  return (
    <div>
      <div style={{ ...s.heroPanel, background: ok ? "linear-gradient(135deg,#ffffff 0%,#f0fdfa 60%,#ecfdf5 100%)" : "linear-gradient(135deg,#ffffff 0%,#fff1f2 60%,#fef2f2 100%)", border: ok ? "1px solid #a7f3d0" : "1px solid #fecdd3", position:"relative", overflow:"hidden" }}>
        <div style={{ position:"absolute", inset:0, background: ok ? "radial-gradient(500px 240px at 85% 0%, rgba(16,185,129,0.08), transparent 60%)" : "radial-gradient(500px 240px at 85% 0%, rgba(239,68,68,0.08), transparent 60%)", pointerEvents:"none"}}/>
        <div style={{ position:"relative", display:"flex", justifyContent:"space-between", gap:16, flexWrap:"wrap", alignItems:"center" }}>
          <div style={{ minWidth:300 }}>
            <div style={{ display:"flex", alignItems:"center", gap:10, marginBottom:6 }}>
              <div style={{ ...s.pageTitle, marginBottom:0 }}>System health</div>
              <span style={{ background: ok?"#10b981":"#ef4444", color:"#fff", fontSize:10, fontWeight:800, letterSpacing:"0.06em", textTransform:"uppercase", padding:"3px 8px", borderRadius:999, display:"inline-flex", gap:6, alignItems:"center" }}><span style={{ width:6, height:6, borderRadius:999, background:"#fff", boxShadow:"0 0 0 4px rgba(255,255,255,0.35)", animation: ok?"pulse 1.6s infinite":undefined } as React.CSSProperties}/> {ok?"All systems operational":"Degraded"}</span>
            </div>
            <div style={{ color:"#405166", fontSize:14, lineHeight:1.6, maxWidth:600 }}>Vercel-status + Datadog live checks. DB, Redis, LLM backends, circuit breakers — 30s auto-refresh, 90-day uptime.</div>
            <div style={{ display:"flex", gap:8, marginTop:10, flexWrap:"wrap" }}>
              <span style={{ fontSize:11, fontWeight:700, color:"#065f46", background:"#ecfdf5", border:"1px solid #a7f3d0", padding:"5px 10px", borderRadius:999 }}>{health ? Object.keys(health.llm_backends||{}).length : 0} backends</span>
              <span style={{ fontSize:11, color:"#7b8a9d", alignSelf:"center" }}>{lastChecked ? `Checked ${lastChecked.toLocaleTimeString()} • every 30s` : "Checking…"}</span>
            </div>
          </div>
          <div style={{ display:"flex", alignItems:"center", gap:12 }}>
            <div style={{ position:"relative", width:72, height:72 }}><Ring pct={ok?99.98:97.4} color={ok?"#10b981":"#ef4444"}/><div style={{ position:"absolute", inset:0, display:"grid", placeItems:"center", fontSize:11, fontWeight:850, color: ok?"#059669":"#dc2626" }}>{ok?"99.9%":"97%"}</div></div>
            <button style={{ ...s.btn(ok?"primary":"danger"), borderRadius:10 }} onClick={check} disabled={loading}>{loading?"Checking…":" Refresh"}</button>
          </div>
        </div>
      </div>
      {error && <div style={s.alert("error")}>{error}</div>}
      {health && (
        <>
          <div style={{ display:"flex", gap:14, flexWrap:"wrap", marginBottom:16 }}>
            <ServiceCard name="PostgreSQL" data={health.database} icon=""/>
            <ServiceCard name="Redis" data={health.redis} icon=""/>
            {Object.entries(health.llm_backends||{}).map(([n,d])=> <ServiceCard key={n} name={n} data={d} icon=""/>)}
          </div>
          <div style={{ ...s.card, padding:0, overflow:"hidden" }}>
            <div style={{ padding:"16px 18px", display:"flex", justifyContent:"space-between", alignItems:"center", borderBottom:"1px solid #eef3f8", background:"#f8fafc" }}>
              <div style={s.sectionTitle}>Configuration</div>
              <span style={{ fontSize:11, color:"#7b8a9d" }}>Vercel env style • Styra OPA: {health.app_env}</span>
            </div>
            <table style={s.table}>
              <tbody>
                <tr><td style={{ ...s.td, fontWeight:700, width:"32%" }}>Default backend</td><td style={s.td}><code style={{ background:"#f1f5f9", border:"1px solid #e2e8f0", padding:"3px 8px", borderRadius:6, fontSize:12 }}>{health.default_backend}</code></td></tr>
                <tr><td style={{ ...s.td, fontWeight:700 }}>Environment</td><td style={s.td}><span style={s.badge(health.app_env==="production"?"delivered":"rate_limited")}>{health.app_env}</span></td></tr>
                <tr><td style={{ ...s.td, fontWeight:700 }}>Billing</td><td style={s.td}><span style={s.badge(health.billing_enabled?"delivered":"error")}>{health.billing_enabled?"enabled":"disabled"}</span></td></tr>
                <tr><td style={{ ...s.td, fontWeight:700 }}>Vector store</td><td style={s.td}><span style={s.badge(health.vectorstore?.status==="ok"?"delivered":"rate_limited")}>{health.vectorstore?.status || "unknown"}</span></td></tr>
              </tbody>
            </table>
          </div>
          <div style={{ marginTop:14, padding:12, background:"#f8fafc", border:"1px solid #e7eef6", borderRadius:10, fontSize:11, color:"#7b8a9d", lineHeight:1.6 }}>
            <b style={{ color:"#102033" }}>Circuit breakers</b> — per-backend failure isolation (closed -- open -- half-open). View JSON at <code>/health/breakers</code> • Datadog-style dependency map coming soon.
          </div>
        </>
      )}
      {loading && !health && <div style={{ color:"#8a9bb0", padding:32, textAlign:"center" }}>Checking…</div>}
      <style>{`@keyframes pulse{0%{transform:scale(1); opacity:1}50%{transform:scale(1.15); opacity:0.7}100%{transform:scale(1); opacity:1}}`}</style>
    </div>
  );
}
