import React, { useState, useEffect, useCallback, useMemo } from "react";
import { api } from "../utils/api";
import { s } from "../styles/theme";

// -- Types ------------------------------------------------------------------
type Memory = {
  id: string; title: string; content: string; category: string; kind: string;
  confidence: number; importance: number; pinned: boolean; archived: boolean;
  source_type: string | null; source_id: string | null;
  created_at: string; updated_at: string; last_accessed: string | null;
};

// -- Category meta — Linear label style ------------------------------------
const CAT_META: Record<string, { icon: string; color: string; bg: string; border: string; label: string }> = {
  fact:       { icon: "", color: "#0f766e", bg: "#ecfdf5", border: "#a7f3d0", label: "Fact" },
  preference: { icon: "", color: "#db2777", bg: "#fdf2f8", border: "#f9a8d4", label: "Preference" },
  procedure:  { icon: "", color: "#2563eb", bg: "#eff6ff", border: "#bfdbfe", label: "Procedure" },
  persona:    { icon: "", color: "#7c3aed", bg: "#f5f3ff", border: "#ddd6fe", label: "Persona" },
  goal:       { icon: "", color: "#d97706", bg: "#fffbeb", border: "#fde68a", label: "Goal" },
  skill:      { icon: "", color: "#0e7490", bg: "#ecfeff", border: "#a5f3fc", label: "Skill" },
};
const CATS = Object.keys(CAT_META) as (keyof typeof CAT_META)[];

function timeAgo(iso: string) {
  const d = new Date(iso);
  const s = (Date.now() - d.getTime()) / 1000;
  if (s < 60) return "now";
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  if (s < 604800) return `${Math.floor(s / 86400)}d`;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
function groupLabel(iso: string) {
  const d = new Date(iso);
  const today = new Date(); today.setHours(0,0,0,0);
  const yest = new Date(today); yest.setDate(yest.getDate()-1);
  const ts = d.getTime();
  if (ts >= today.getTime()) return "Today";
  if (ts >= yest.getTime()) return "Yesterday";
  if (ts >= today.getTime() - 6*86400000) return "This week";
  return "Earlier";
}

export default function MemoryView() {
  const [items, setItems] = useState<Memory[]>([]);
  const [q, setQ] = useState("");
  const [cat, setCat] = useState<string>("");
  const [pinnedOnly, setPinnedOnly] = useState(false);
  const [selected, setSelected] = useState<Memory | null>(null);
  const [editing, setEditing] = useState<Partial<Memory> & { id?: string } | null>(null);
  const [showNew, setShowNew] = useState(false);
  const [recallQ, setRecallQ] = useState("");
  const [recallRes, setRecallRes] = useState<Memory[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [stats, setStats] = useState<{total:number; pinned:number; by_category:Record<string,number>}|null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [mems, st] = await Promise.all([
        api<Memory[]>(`/memories?` + new URLSearchParams({ ...(q?{q}:{}), ...(cat?{category:cat}:{}), ...(pinnedOnly?{pinned_only:"true"}:{}), archived:"false", limit:"100" })),
        api<{total:number; pinned:number; by_category:Record<string,number>}>("/memories/stats").catch(()=>null),
      ]);
      setItems(mems);
      if (st) setStats(st);
      if (mems.length && !selected) setSelected(mems[0]);
    } finally { setLoading(false); }
  }, [q, cat, pinnedOnly]);

  useEffect(()=>{ load(); }, [load]);
  useEffect(()=>{ if(toast){ const t=setTimeout(()=>setToast(null),2800); return ()=>clearTimeout(t); } }, [toast]);

  const groups = useMemo(()=>{
    const g: Record<string, Memory[]> = {};
    for (const m of items) {
      const label = groupLabel(m.updated_at);
      (g[label] ||= []).push(m);
    }
    const order = ["Today","Yesterday","This week","Earlier"];
    return order.filter(k=>g[k]).map(k=>({ label:k, items:g[k]}));
  }, [items]);

  async function createManual(content: string, category: string) {
    if (!content.trim()) return;
    setSaving(true);
    try {
      const mem = await api<Memory>("/memories", { method:"POST", body:{ content: content.trim(), category, kind:"user" }});
      setToast("Memory saved • pinned to top");
      setShowNew(false);
      setItems(v=>[mem, ...v]);
      setSelected(mem);
    } finally { setSaving(false); }
  }
  async function togglePin(m: Memory) {
    const upd = await api<Memory>(`/memories/${m.id}`, { method:"PATCH", body:{ pinned: !m.pinned }});
    setItems(v=>v.map(x=>x.id===m.id? upd : x));
    if (selected?.id===m.id) setSelected(upd);
  }
  async function saveEdit() {
    if (!editing?.id) return;
    setSaving(true);
    try {
      const upd = await api<Memory>(`/memories/${editing.id}`, { method:"PATCH", body:{ title: editing.title, content: editing.content, category: editing.category, importance: editing.importance, pinned: editing.pinned }});
      setItems(v=>v.map(x=>x.id===upd.id? upd : x));
      setSelected(upd);
      setEditing(null);
      setToast("Memory updated");
    } finally { setSaving(false); }
  }
  async function archive(m: Memory) {
    if (!confirm(`Archive "${m.title}"?`)) return;
    await api(`/memories/${m.id}`, { method:"DELETE" });
    setItems(v=>v.filter(x=>x.id!==m.id));
    if (selected?.id===m.id) setSelected(items.find(x=>x.id!==m.id) || null);
    setToast("Archived");
  }
  async function doRecall() {
    if (!recallQ.trim()) { setRecallRes(null); return; }
    const res = await api<{memories:Memory[]; query:string}>("/memories/recall", { method:"POST", body:{ query: recallQ, top_k:6 }});
    setRecallRes(res.memories);
  }
  async function extractFromChat() {
    // preview extraction from last prompt stored in localStorage (ChatView)
    const hist = JSON.parse(localStorage.getItem("guardrails_chat_history") || "[]") as {prompt:string; result:{response?:string}}[];
    const last = hist[hist.length-1];
    if (!last) { setToast("No recent chat to extract from — chat first"); return; }
    const preview = await api<{candidates:{title:string; content:string; category:string; confidence:number}[]}>("/memories/extract/preview", { method:"POST", body:{ prompt:last.prompt, response: last.result?.response }});
    if (!preview.candidates.length) { setToast("Nothing memorable in last chat"); return; }
    if (!confirm(`Extract ${preview.candidates.length} memories?\n\n` + preview.candidates.map(c=>`• ${c.content}`).join("\n"))) return;
    const created = await api<Memory[]>("/memories/extract/confirm", { method:"POST", body:{ items: preview.candidates }});
    setToast(`Extracted ${created.length} memories`);
    load();
  }

  return (
    <div style={{ minWidth: 0 }}>
      {/* Hero — Linear inbox style */}
      <div style={{ ...s.heroPanel, background: "linear-gradient(135deg,#ffffff 0%,#f0fdfa 55%,#eff6ff 100%)", border:"1px solid #ccfbf1", position:"relative", overflow:"hidden" }}>
        <div style={{ position:"absolute", inset:0, background:"radial-gradient(600px 300px at 85% -10%, rgba(20,184,166,0.10), transparent 60%), radial-gradient(500px 400px at -5% 110%, rgba(59,130,246,0.07), transparent 60%)", pointerEvents:"none"}}/>
        <div style={{ position:"relative", display:"flex", justifyContent:"space-between", gap:16, flexWrap:"wrap", alignItems:"flex-start" }}>
          <div style={{ minWidth:280 }}>
            <div style={{ display:"flex", alignItems:"center", gap:10, marginBottom:6 }}>
              <div style={{ ...s.pageTitle, marginBottom:0 }}>Memory</div>
              <span style={{ background:"#0f766e", color:"#fff", fontSize:10, fontWeight:800, letterSpacing:"0.06em", textTransform:"uppercase", padding:"3px 8px", borderRadius:999 }}>Mem0 x Linear</span>
            </div>
            <div style={{ color:"#405166", fontSize:14, lineHeight:1.55, maxWidth:620 }}>
              Your long-term memory — <b>facts, preferences, procedures</b> auto-extracted from chats and skills. Pinned memories are injected into every prompt.
              <span style={{ color:"#0f766e", fontWeight:700 }}> • Superhuman-fast search</span> <span style={{color:"#a8a29e"}}>• Notion-grade blocks</span>
            </div>
            <div style={{ display:"flex", gap:8, marginTop:12, flexWrap:"wrap" }}>
              <span style={{ ...s.badge("delivered"), background:"#ecfdf5", borderColor:"#6ee7b7", color:"#065f46" }}>{stats?.total ?? items.length} remembered</span>
              <span style={{ ...s.badge("rate_limited") }}>{stats?.pinned ?? items.filter(x=>x.pinned).length} pinned</span>
              <span style={{ ...s.badge("input_blocked") }}>{Object.keys(stats?.by_category || {}).length || CATS.length} categories</span>
              <span style={{ fontSize:11, color:"#7b8a9d", alignSelf:"center" }}>K to search • C to create</span>
            </div>
          </div>
          <div style={{ display:"flex", gap:8, flexWrap:"wrap", alignSelf:"flex-start" }}>
            <button style={{ ...s.btn("secondary"), borderRadius:10 }} onClick={extractFromChat}> Extract from last chat</button>
            <button style={{ ...s.btn("primary"), borderRadius:10, boxShadow:"0 10px 24px rgba(15,118,110,0.22)" }} onClick={()=>setShowNew(v=>!v)}>+ New memory</button>
          </div>
        </div>
      </div>

      {toast && <div style={{ position:"fixed", top:16, right:16, zIndex:50, background:"#0f766e", color:"#fff", padding:"10px 16px", borderRadius:10, fontSize:13, fontWeight:700, boxShadow:"0 12px 28px rgba(0,0,0,0.18)" }}>{toast}</div>}

      {/* Command / search bar — Superhuman + Linear */}
      <div style={{ display:"flex", gap:10, marginBottom:14, flexWrap:"wrap", alignItems:"center" }}>
        <div style={{ position:"relative", flex:"1 1 320px", minWidth:260 }}>
          <span style={{ position:"absolute", left:12, top:"50%", transform:"translateY(-50%)", color:"#8a9bb0", fontSize:13 }}>K</span>
          <input
            value={q}
            onChange={e=>setQ(e.target.value)}
            placeholder="Search memories — try 'my stack', 'prefers dark mode', 'deployment steps'…"
            style={{ ...s.input, paddingLeft:36, marginBottom:0, borderRadius:12, background:"#fff", border:"1px solid #cfe4de", boxShadow:"0 4px 14px rgba(15,118,110,0.06)" }}
            onKeyDown={e=>{ if(e.key==="Enter" && recallQ) doRecall(); }}
          />
        </div>
        <div style={{ display:"flex", background:"#eef3f8", borderRadius:999, padding:3, gap:2, flexWrap:"wrap" }}>
          {["","fact","preference","procedure","persona","goal","skill"].map(c=>(
            <button key={c||"all"} onClick={()=>setCat(c)} style={{ padding:"6px 12px", borderRadius:999, border:"none", cursor:"pointer", fontSize:12, fontWeight:800, background: cat===c ? "#0f766e" : "transparent", color: cat===c ? "#fff" : "#405166", transition:"all .15s" }}>
              {c ? CAT_META[c as string]?.label || c : "All"}
            </button>
          ))}
        </div>
        <label style={{ display:"inline-flex", alignItems:"center", gap:6, fontSize:12, fontWeight:700, color: pinnedOnly?"#0f766e":"#607086", cursor:"pointer", background: pinnedOnly?"#ecfdf5":"#fff", border:`1px solid ${pinnedOnly?"#6ee7b7":"#dce7f0"}`, padding:"7px 12px", borderRadius:999 }}>
          <input type="checkbox" checked={pinnedOnly} onChange={e=>setPinnedOnly(e.target.checked)} /> Pinned
        </label>
      </div>

      {/* Semantic recall bar — Mem0 style */}
      <div style={{ display:"flex", gap:8, marginBottom:16, alignItems:"center", flexWrap:"wrap" }}>
        <input value={recallQ} onChange={e=>setRecallQ(e.target.value)} placeholder="Semantic recall — ask your memory: 'what do you know about my project?'" style={{ ...s.input, flex:"1 1 300px", minWidth:240, marginBottom:0, borderRadius:10, background:"#f8fbff" }} />
        <button style={{ ...s.btn("secondary"), borderRadius:10 }} onClick={doRecall}>Recall</button>
        {recallRes && <button style={{ ...s.btn("secondary"), borderRadius:10 }} onClick={()=>setRecallRes(null)}>Clear</button>}
      </div>
      {recallRes && (
        <div style={{ ...s.card, marginBottom:16, background:"#f8fbff", borderColor:"#c7d2fe" }}>
          <div style={{ ...s.sectionTitle, marginBottom:8 }}>Recall: "{recallQ}" • {recallRes.length} hits</div>
          {recallRes.length===0 ? <div style={s.muted}>No matches — try a broader query.</div> : recallRes.map(m=>(
            <div key={m.id} onClick={()=>setSelected(m)} style={{ display:"flex", gap:10, padding:"8px 10px", borderRadius:8, cursor:"pointer", background: selected?.id===m.id?"#fff":"transparent", border: selected?.id===m.id?"1px solid #c7d2fe":"1px solid transparent" }}>
              <span style={{ ...s.badge("delivered"), background: CAT_META[m.category]?.bg, borderColor: CAT_META[m.category]?.border, color: CAT_META[m.category]?.color, height:22 }}>{CAT_META[m.category]?.icon} {m.category}</span>
              <span style={{ fontSize:13, color:"#102033", fontWeight:600 }}>{m.title}</span>
              <span style={{ fontSize:12, color:"#7b8a9d", marginLeft:"auto" }}>{(m.confidence*100).toFixed(0)}%</span>
            </div>
          ))}
        </div>
      )}

      {showNew && (
        <div style={{ ...s.card, marginBottom:16, borderColor:"#99f6e4", background:"linear-gradient(135deg,#fff 0%,#f0fdfa 100%)" }}>
          <div style={s.sectionTitle}>New memory — manual</div>
          <NewMemoryForm onCreate={createManual} saving={saving} onCancel={()=>setShowNew(false)} />
        </div>
      )}

      {/* Main — Linear master/detail */}
      <div style={{ display:"flex", gap:16, alignItems:"flex-start", flexWrap:"wrap" }}>
        {/* List */}
        <div style={{ flex:"1 1 420px", minWidth:320, display:"flex", flexDirection:"column", gap:14 }}>
          {loading ? (
            <div style={{ ...s.card, padding:40, textAlign:"center", color:"#8a9bb0" }}>Loading memories…</div>
          ) : items.length===0 ? (
            <div style={{ ...s.card, padding:28, textAlign:"center" }}>
              <div style={{ fontSize:22, marginBottom:8 }}></div>
              <div style={{ fontWeight:800, color:"#102033" }}>No memories yet</div>
              <div style={{ fontSize:13, color:"#7b8a9d", marginTop:6, lineHeight:1.5 }}>Chat with the playground — we'll auto-extract facts & preferences.<br/>Or create one manually.</div>
              <button style={{ ...s.btn("primary"), marginTop:14, borderRadius:10 }} onClick={()=>setShowNew(true)}>Create first memory</button>
            </div>
          ) : groups.map(g=>(
            <div key={g.label}>
              <div style={{ fontSize:11, fontWeight:800, color:"#7b8a9d", letterSpacing:"0.06em", textTransform:"uppercase", margin:"4px 0 8px 4px" }}>{g.label} <span style={{ fontWeight:600, color:"#a8a29e"}}>• {g.items.length}</span></div>
              <div style={{ display:"flex", flexDirection:"column", gap:8 }}>
                {g.items.map(m=>(
                  <div key={m.id} onClick={()=>setSelected(m)} style={{
                    ...s.card,
                    padding:"14px 16px",
                    cursor:"pointer",
                    borderColor: selected?.id===m.id ? "#0f766e" : m.pinned ? "#6ee7b7" : "rgba(15,118,110,0.12)",
                    background: selected?.id===m.id ? "#f0fdfa" : m.pinned ? "#f8fffe" : "rgba(255,255,255,0.92)",
                    borderLeftWidth: m.pinned ? 3 : 1,
                    borderLeftColor: m.pinned ? "#0f766e" : undefined,
                    boxShadow: selected?.id===m.id ? "0 8px 24px rgba(15,118,110,0.10)" : "0 4px 12px rgba(15,118,110,0.04)",
                    transform: selected?.id===m.id ? "translateY(-1px)" : undefined,
                    transition:"all .14s",
                  }}>
                    <div style={{ display:"flex", gap:10, alignItems:"flex-start" }}>
                      <span style={{ width:28, height:28, borderRadius:8, display:"grid", placeItems:"center", background: CAT_META[m.category]?.bg, border:`1px solid ${CAT_META[m.category]?.border}`, color: CAT_META[m.category]?.color, fontSize:12, flexShrink:0 }}>{CAT_META[m.category]?.icon}</span>
                      <div style={{ minWidth:0, flex:1 }}>
                        <div style={{ display:"flex", gap:6, alignItems:"center", flexWrap:"wrap", marginBottom:4 }}>
                          <span style={{ fontSize:11, fontWeight:800, color: CAT_META[m.category]?.color, background: CAT_META[m.category]?.bg, border:`1px solid ${CAT_META[m.category]?.border}`, padding:"2px 7px", borderRadius:999 }}>{CAT_META[m.category]?.label}</span>
                          {m.pinned && <span style={{ fontSize:10, fontWeight:800, color:"#065f46", background:"#d1fae5", padding:"2px 6px", borderRadius:999 }}>PINNED</span>}
                          <span style={{ fontSize:10, color:"#8a9bb0" }}>{timeAgo(m.updated_at)} • {m.confidence.toFixed(2)}</span>
                        </div>
                        <div style={{ fontSize:13, fontWeight:800, color:"#102033", lineHeight:1.3, display:"-webkit-box", WebkitLineClamp:1, WebkitBoxOrient:"vertical", overflow:"hidden" }}>{m.title}</div>
                        <div style={{ fontSize:13, color:"#405166", lineHeight:1.5, display:"-webkit-box", WebkitLineClamp:2, WebkitBoxOrient:"vertical", overflow:"hidden", marginTop:3 }}>{m.content}</div>
                        <div style={{ display:"flex", gap:6, marginTop:8, flexWrap:"wrap", alignItems:"center" }}>
                          <span style={{ fontSize:10, color:"#7b8a9d", border:"1px solid #e7eef6", padding:"3px 7px", borderRadius:999, background:"#f8fbff" }}>{m.source_type || "manual"} {m.source_id ? "• " + m.source_id.slice(0,6) : ""}</span>
                          <span style={{ display:"inline-flex", gap:3 }}>{Array.from({length:5}).map((_,i)=>(
                            <span key={i} style={{ width:6, height:6, borderRadius:999, background: i < m.importance ? "#f59e0b" : "#e7eef6" }} />
                          ))}</span>
                          <span style={{ marginLeft:"auto", display:"inline-flex", gap:4 }}>
                            <button onClick={e=>{ e.stopPropagation(); togglePin(m); }} title={m.pinned?"Unpin":"Pin"} style={{ width:26, height:26, borderRadius:8, border:"1px solid #dce7f0", background: m.pinned?"#0f766e":"#fff", color: m.pinned?"#fff":"#607086", cursor:"pointer" }}>{m.pinned?"":""}</button>
                            <button onClick={e=>{ e.stopPropagation(); setEditing(m); }} style={{ width:26, height:26, borderRadius:8, border:"1px solid #dce7f0", background:"#fff", color:"#607086", cursor:"pointer" }}>Edit</button>
                            <button onClick={e=>{ e.stopPropagation(); archive(m); }} style={{ width:26, height:26, borderRadius:8, border:"1px solid #fecdd3", background:"#fff", color:"#be123c", cursor:"pointer" }}>x</button>
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* Detail — Notion block + Linear properties */}
        <div style={{ flex:"1.2 1 420px", minWidth:340, position:"sticky", top:16, alignSelf:"flex-start" }}>
          {!selected ? (
            <div style={{ ...s.card, padding:32, textAlign:"center", color:"#8a9bb0" }}>Select a memory</div>
          ) : editing && editing.id===selected.id ? (
            <div style={{ ...s.card }}>
              <div style={s.sectionTitle}>Edit memory</div>
              <input value={editing.title || ""} onChange={e=>setEditing(v=>({...v!, title:e.target.value}))} placeholder="Title" style={{ ...s.input, marginBottom:10 }} />
              <textarea value={editing.content || ""} onChange={e=>setEditing(v=>({...v!, content:e.target.value}))} style={{ ...s.input, minHeight:140, resize:"vertical" }} />
              <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:10, marginTop:10 }}>
                <div><label style={s.label}>Category</label><select value={editing.category} onChange={e=>setEditing(v=>({...v!, category:e.target.value}))} style={s.input}>{CATS.map(c=><option key={c} value={c}>{c}</option>)}</select></div>
                <div><label style={s.label}>Importance</label><select value={editing.importance} onChange={e=>setEditing(v=>({...v!, importance: Number(e.target.value)}))} style={s.input}>{[1,2,3,4,5].map(n=><option key={n} value={n}>{n}</option>)}</select></div>
              </div>
              <label style={{ display:"flex", gap:8, alignItems:"center", marginTop:10, fontSize:13, fontWeight:700 }}><input type="checkbox" checked={!!editing.pinned} onChange={e=>setEditing(v=>({...v!, pinned:e.target.checked}))} /> Pinned (injected into every prompt)</label>
              <div style={{ display:"flex", gap:8, marginTop:14 }}>
                <button style={s.btn("primary")} onClick={saveEdit} disabled={saving}>{saving?"Saving…":"Save"}</button>
                <button style={s.btn("secondary")} onClick={()=>setEditing(null)}>Cancel</button>
              </div>
            </div>
          ) : (
            <div style={{ ...s.card, padding:0, overflow:"hidden" }}>
              <div style={{ height:4, background:`linear-gradient(90deg, ${CAT_META[selected.category]?.color}, ${CAT_META[selected.category]?.color}66)`, opacity:0.95 }} />
              <div style={{ padding:20 }}>
                <div style={{ display:"flex", gap:8, alignItems:"center", marginBottom:10, flexWrap:"wrap" }}>
                  <span style={{ ...s.badge("delivered"), background: CAT_META[selected.category]?.bg, borderColor: CAT_META[selected.category]?.border, color: CAT_META[selected.category]?.color }}>{CAT_META[selected.category]?.icon} {selected.category}</span>
                  <span style={{ fontSize:11, color:"#7b8a9d", fontWeight:700 }}>{selected.kind} • {selected.confidence.toFixed(2)} • {new Date(selected.created_at).toLocaleString()}</span>
                  {selected.pinned && <span style={{ ...s.badge("rate_limited") }}>Pinned</span>}
                </div>
                <div style={{ fontSize:20, fontWeight:850, color:"#102033", lineHeight:1.25, letterSpacing:"-0.01em" }}>{selected.title}</div>
                <div style={{ marginTop:12, padding:16, background:"#f8fbff", border:"1px solid #e7eef6", borderRadius:12, fontSize:14, lineHeight:1.65, color:"#27394f", whiteSpace:"pre-wrap" }}>{selected.content}</div>

                <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:10, marginTop:16 }}>
                  <Info label="Importance" value={"".repeat(selected.importance) + "".repeat(5-selected.importance)} />
                  <Info label="Source" value={`${selected.source_type || "manual"} ${selected.source_id ? "• " + selected.source_id.slice(0,8) : ""}`} />
                  <Info label="Created" value={new Date(selected.created_at).toLocaleString()} />
                  <Info label="Updated" value={new Date(selected.updated_at).toLocaleString()} />
                </div>

                {/* Mem0-style recall provenance mini-graph */}
                <div style={{ marginTop:16, padding:12, background:"linear-gradient(135deg,#fff 0%,#f0fdfa 100%)", border:"1px solid #ccfbf1", borderRadius:10, display:"flex", gap:8, alignItems:"center", flexWrap:"wrap" }}>
                  <span style={{ width:28, height:28, borderRadius:8, background:"#0f766e", color:"#fff", display:"grid", placeItems:"center", fontSize:12 }}></span>
                  <div style={{ fontSize:12, color:"#405166" }}><b>Recall provenance</b> — vector + keyword fallback. Last accessed {selected.last_accessed ? timeAgo(selected.last_accessed) + " ago" : "never"}.</div>
                </div>

                <div style={{ display:"flex", gap:8, marginTop:16, flexWrap:"wrap" }}>
                  <button style={s.btn("primary")} onClick={()=>setEditing(selected)}>Edit</button>
                  <button style={{ ...s.btn("secondary"), color: selected.pinned?"#065f46":undefined, borderColor: selected.pinned?"#6ee7b7":undefined }} onClick={()=>togglePin(selected)}>{selected.pinned?"Unpin":"Pin to context"}</button>
                  <button style={{ ...s.btn("danger"), marginLeft:"auto" }} onClick={()=>archive(selected)}>Archive</button>
                </div>
              </div>
            </div>
          )}
          {/* Tips */}
          <div style={{ marginTop:12, padding:12, background:"#fffbeb", border:"1px solid #fde68a", borderRadius:10, fontSize:12, color:"#92400e", lineHeight:1.6 }}>
            <b>Pro tips</b> — Mem0/Notion style: Type <code style={{ background:"#fff", border:"1px solid #fde68a", padding:"1px 6px", borderRadius:6 }}>remember that…</code> in chat to auto-create a memory. Pinned memories are prepended to every LLM call.
          </div>
        </div>
      </div>
    </div>
  );
}

function Info({ label, value }: { label:string; value:string }) {
  return <div style={{ background:"#f8fbff", border:"1px solid #e7eef6", borderRadius:8, padding:"10px 12px" }}><div style={{ fontSize:10, fontWeight:800, color:"#7b8a9d", letterSpacing:"0.05em", textTransform:"uppercase"}}>{label}</div><div style={{ fontSize:13, fontWeight:700, color:"#102033", marginTop:4}}>{value}</div></div>;
}

function NewMemoryForm({ onCreate, saving, onCancel }: { onCreate:(content:string, category:string)=>void; saving:boolean; onCancel:()=>void }) {
  const [content, setContent] = useState("");
  const [cat, setCat] = useState("fact");
  return (
    <div>
      <textarea value={content} onChange={e=>setContent(e.target.value)} placeholder="e.g. User prefers dark mode and concise answers. Always use pnpm, never npm." style={{ ...{width:"100%", background:"#fff", border:"1px solid #99f6e4", borderRadius:10, padding:"12px 14px", fontSize:14, lineHeight:1.5, outline:"none"}, minHeight:90, resize:"vertical" } as React.CSSProperties} />
      <div style={{ display:"flex", gap:8, marginTop:10, alignItems:"center", flexWrap:"wrap" }}>
        <select value={cat} onChange={e=>setCat(e.target.value)} style={{ ...{ background:"#fff", border:"1px solid #99f6e4", borderRadius:8, padding:"8px 12px", fontSize:13, fontWeight:700 } as React.CSSProperties, minWidth:140 }}>
          {CATS.map(c=><option key={c} value={c}>{CAT_META[c].label}</option>)}
        </select>
        <button style={{ ...{ padding:"10px 16px", borderRadius:10, border:"1px solid transparent", cursor:"pointer", fontSize:13, fontWeight:800, background:"linear-gradient(135deg,#0f766e,#047857)", color:"#fff", opacity: saving?0.6:1 } as React.CSSProperties }} onClick={()=>onCreate(content, cat)} disabled={saving || !content.trim()}>{saving?"Saving…":"Save memory"}</button>
        <button style={{ background:"#fff", border:"1px solid #dce7f0", borderRadius:10, padding:"8px 12px", fontSize:12, fontWeight:700, color:"#405166", cursor:"pointer" }} onClick={onCancel}>Cancel</button>
        <span style={{ fontSize:11, color:"#7b8a9d" }}>Stored per-user, vectored for recall</span>
      </div>
    </div>
  );
}
