import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../utils/api";
import AppIcon from "../components/AppIcon";
import { Badge, Button, Dialog, EmptyState, Field, LoadingState, Notice, PageHeader, Panel, useConfirmation } from "../components/ui";
import "../styles/memory.css";

type Memory = { id: string; title: string; content: string; category: string; kind: string; confidence: number; importance: number; pinned: boolean; archived: boolean; source_type: string | null; source_id: string | null; created_at: string; updated_at: string; last_accessed: string | null };
type MemoryStats = { total: number; pinned: number; by_category: Record<string, number> };
type Candidate = { title: string; content: string; category: string; confidence: number; importance?: number; source_id?: string };
type Draft = { title: string; content: string; category: string; importance: number; pinned: boolean };
const CATEGORIES = ["fact", "preference", "procedure", "persona", "goal", "skill"];
const emptyDraft = (): Draft => ({ title: "", content: "", category: "fact", importance: 3, pinned: false });
const categoryLabel = (category: string) => category.charAt(0).toUpperCase() + category.slice(1);
const errorMessage = (error: unknown) => error instanceof Error ? error.message : String(error);
const formatDate = (date: string | null) => date ? new Date(date).toLocaleString() : "Never";

function groupLabel(iso: string) {
  const timestamp = new Date(iso).getTime(); const today = new Date(); today.setHours(0, 0, 0, 0);
  const yesterday = new Date(today); yesterday.setDate(yesterday.getDate() - 1);
  if (timestamp >= today.getTime()) return "Today";
  if (timestamp >= yesterday.getTime()) return "Yesterday";
  if (timestamp >= today.getTime() - 6 * 86400000) return "This week";
  return "Earlier";
}

export default function MemoryView() {
  const [items, setItems] = useState<Memory[]>([]);
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [pinnedOnly, setPinnedOnly] = useState(false);
  const [selected, setSelected] = useState<Memory | null>(null);
  const [editor, setEditor] = useState<Memory | "new" | null>(null);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [formError, setFormError] = useState("");
  const [recallQ, setRecallQ] = useState("");
  const [recallResult, setRecallResult] = useState<{ query: string; memories: Memory[] } | null>(null);
  const [recalling, setRecalling] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState("");
  const [stats, setStats] = useState<MemoryStats | null>(null);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [extracting, setExtracting] = useState(false);
  const [candidates, setCandidates] = useState<Candidate[] | null>(null);
  const [chosen, setChosen] = useState<number[]>([]);
  const sequence = useRef(0);
  const mutation = useRef(false);
  const { confirm, dialog } = useConfirmation();

  const refreshStats = useCallback(async () => {
    try { setStats(await api<MemoryStats>("/memories/stats")); } catch { setStats(null); }
  }, []);
  const load = useCallback(async () => {
    const request = ++sequence.current; setLoading(true); setError("");
    const params = new URLSearchParams({ ...(query ? { q: query } : {}), ...(category ? { category } : {}), ...(pinnedOnly ? { pinned_only: "true" } : {}), archived: "false", limit: "100" });
    try {
      const [memories, nextStats] = await Promise.all([api<Memory[]>(`/memories?${params}`), api<MemoryStats>("/memories/stats").catch(() => null)]);
      if (request !== sequence.current) return;
      setItems(memories); setStats(nextStats);
      setSelected((current) => memories.find((memory) => memory.id === current?.id) || memories[0] || null);
    } catch (failure) { if (request === sequence.current) setError(errorMessage(failure)); }
    finally { if (request === sequence.current) setLoading(false); }
  }, [query, category, pinnedOnly]);
  useEffect(() => { const timer = window.setTimeout(() => setQuery(q), 220); return () => window.clearTimeout(timer); }, [q]);
  useEffect(() => { void load(); return () => { sequence.current++; }; }, [load]);
  useEffect(() => { if (!toast) return; const timer = window.setTimeout(() => setToast(""), 3500); return () => window.clearTimeout(timer); }, [toast]);
  const groups = useMemo(() => {
    const grouped: Record<string, Memory[]> = {};
    items.forEach((memory) => (grouped[groupLabel(memory.updated_at)] ||= []).push(memory));
    return ["Today", "Yesterday", "This week", "Earlier"].filter((label) => grouped[label]).map((label) => ({ label, items: grouped[label] }));
  }, [items]);
  const filtersApplied = !!(q || category || pinnedOnly);
  function openEditor(memory?: Memory) { setDraft(memory ? { title: memory.title, content: memory.content, category: memory.category, importance: memory.importance, pinned: memory.pinned } : emptyDraft()); setFormError(""); setEditor(memory || "new"); }
  function applyUpdated(memory: Memory) { setItems((current) => current.map((item) => item.id === memory.id ? memory : item).filter((item) => !pinnedOnly || item.pinned)); setSelected((current) => current?.id === memory.id ? memory : current); setRecallResult((current) => current ? { ...current, memories: current.memories.map((item) => item.id === memory.id ? memory : item) } : null); }

  async function saveMemory(event: React.FormEvent) {
    event.preventDefault(); if (!editor || !draft.content.trim() || mutation.current) return;
    mutation.current = true; setSaving(true); setFormError("");
    try {
      const isNew = editor === "new";
      const body = { title: isNew ? draft.title.trim() || undefined : draft.title, content: isNew ? draft.content.trim() : draft.content, category: draft.category, importance: draft.importance, pinned: draft.pinned, ...(isNew ? { kind: "user" } : {}) };
      const memory = await api<Memory>(isNew ? "/memories" : `/memories/${editor.id}`, { method: isNew ? "POST" : "PATCH", body });
      if (isNew) { setItems((current) => [memory, ...current]); setSelected(memory); } else { applyUpdated(memory); setSelected(memory); }
      setEditor(null); setToast(isNew ? "Memory saved" : "Memory updated"); await refreshStats();
    } catch (failure) { setFormError(errorMessage(failure)); }
    finally { mutation.current = false; setSaving(false); }
  }
  async function togglePin(memory: Memory) {
    if (mutation.current) return; mutation.current = true; setBusyId(memory.id); setError("");
    try { applyUpdated(await api<Memory>(`/memories/${memory.id}`, { method: "PATCH", body: { pinned: !memory.pinned } })); setToast(memory.pinned ? "Memory unpinned" : "Memory pinned to context"); await refreshStats(); }
    catch (failure) { setError(errorMessage(failure)); }
    finally { mutation.current = false; setBusyId(""); }
  }
  async function archive(memory: Memory) {
    if (mutation.current || !await confirm({ title: "Archive this memory?", description: `“${memory.title}” will be removed from active memory and recall.`, confirmLabel: "Archive memory", danger: true })) return;
    mutation.current = true; setBusyId(memory.id); setError("");
    try { await api(`/memories/${memory.id}`, { method: "DELETE" }); setItems((current) => current.filter((item) => item.id !== memory.id)); setSelected((current) => current?.id === memory.id ? items.find((item) => item.id !== memory.id) || null : current); setRecallResult((current) => current ? { ...current, memories: current.memories.filter((item) => item.id !== memory.id) } : null); setToast("Memory archived"); await refreshStats(); }
    catch (failure) { setError(errorMessage(failure)); }
    finally { mutation.current = false; setBusyId(""); }
  }
  async function doRecall(event: React.FormEvent) {
    event.preventDefault(); if (!recallQ.trim() || recalling) return;
    setRecalling(true); setError("");
    try { setRecallResult(await api<{ memories: Memory[]; query: string }>("/memories/recall", { method: "POST", body: { query: recallQ.trim(), top_k: 6 } })); }
    catch (failure) { setError(errorMessage(failure)); }
    finally { setRecalling(false); }
  }
  async function extractFromChat() {
    if (extracting || mutation.current) return; setExtracting(true); setError("");
    try {
      const history: unknown = JSON.parse(localStorage.getItem("guardrails_chat_history") || "[]");
      const last = Array.isArray(history) ? history.at(-1) as { prompt?: string; result?: { response?: string } } | undefined : undefined;
      if (!last?.prompt) { setToast("Run a chat request before extracting memories."); return; }
      const preview = await api<{ candidates: Candidate[] }>("/memories/extract/preview", { method: "POST", body: { prompt: last.prompt, response: last.result?.response } });
      if (!preview.candidates.length) { setToast("No memory candidates found in the last chat."); return; }
      const review = preview.candidates.slice(0, 5); setCandidates(review); setChosen(review.map((_, index) => index)); setFormError("");
    } catch (failure) { setError(errorMessage(failure)); }
    finally { setExtracting(false); }
  }
  async function confirmExtraction() {
    if (!candidates || !chosen.length || mutation.current) return;
    mutation.current = true; setSaving(true); setFormError("");
    try { const created = await api<Memory[]>("/memories/extract/confirm", { method: "POST", body: { items: candidates.filter((_, index) => chosen.includes(index)) } }); setCandidates(null); setToast(`${created.length} ${created.length === 1 ? "memory" : "memories"} saved`); await load(); }
    catch (failure) { setFormError(errorMessage(failure)); }
    finally { mutation.current = false; setSaving(false); }
  }

  return <div className="memory-page">
    <PageHeader eyebrow="CONTEXT LIBRARY" title="Memory" description="Keep useful facts and preferences close. Pin what should follow every request." actions={<><Button icon="sparkles" loading={extracting} disabled={saving || !!busyId} onClick={() => void extractFromChat()}>Extract from last chat</Button><Button variant="primary" icon="plus" disabled={saving || !!busyId} onClick={() => openEditor()}>New memory</Button></>} />
    {toast && <Notice tone="success">{toast}</Notice>}{error && <Notice tone="danger">{error}</Notice>}
    <div className="memory-summary"><div><span>Active memories</span><strong>{stats ? stats.total.toLocaleString() : "—"}</strong></div><div><span>Pinned to context</span><strong>{stats ? stats.pinned.toLocaleString() : "—"}</strong></div><div><span>Categories in use</span><strong>{stats ? Object.keys(stats.by_category).length : "—"}</strong></div><p>Pinned memories are included when your chat context is assembled.</p></div>
    <Panel className="memory-controls"><div className="memory-search-row"><Field label="Search memories"><input className="ui-input" type="search" value={q} onChange={(event) => setQ(event.target.value)} placeholder="Search facts, preferences, or procedures" /></Field><label className="memory-pinned-filter"><input type="checkbox" checked={pinnedOnly} onChange={(event) => setPinnedOnly(event.target.checked)} />Pinned only</label>{filtersApplied && <Button variant="ghost" onClick={() => { setQ(""); setQuery(""); setCategory(""); setPinnedOnly(false); }}>Reset filters</Button>}</div><div className="ui-tabs memory-category-tabs" aria-label="Memory category">{["", ...CATEGORIES].map((value) => <button type="button" key={value || "all"} className={category === value ? "is-active" : ""} aria-pressed={category === value} onClick={() => setCategory(value)}>{value ? categoryLabel(value) : "All categories"}</button>)}</div></Panel>
    <Panel title="Recall from memory" description="Ask a question to find relevant saved context." className="memory-recall-panel"><form className="memory-recall-form" onSubmit={(event) => void doRecall(event)}><Field label="Recall query"><input className="ui-input" value={recallQ} onChange={(event) => setRecallQ(event.target.value)} maxLength={2000} placeholder="What do you know about my project?" /></Field><Button variant="primary" type="submit" icon="search" loading={recalling} disabled={!recallQ.trim()}>Recall</Button>{recallResult && <Button onClick={() => setRecallResult(null)}>Clear results</Button>}</form>{recallResult && <div className="memory-recall-results"><div className="memory-recall-title"><strong>Results for “{recallResult.query}”</strong><Badge>{recallResult.memories.length} matches</Badge></div>{!recallResult.memories.length ? <EmptyState icon="search" title="No matching memories" description="Try a broader query or save more context." /> : recallResult.memories.map((memory) => <button type="button" className={`memory-recall-item${selected?.id === memory.id ? " is-selected" : ""}`} key={memory.id} onClick={() => setSelected(memory)}><Badge>{categoryLabel(memory.category)}</Badge><strong>{memory.title}</strong><span>{Math.round(memory.confidence * 100)}% confidence</span><AppIcon name="chevron" size={15} /></button>)}</div>}</Panel>
    <div className="memory-workspace">
      <section className="memory-list" aria-label="Saved memories">{loading ? <LoadingState label="Loading memories" /> : !items.length ? <Panel><EmptyState icon={filtersApplied ? "search" : "layers"} title={filtersApplied ? "No memories match your filters" : "Your context library starts here"} description={filtersApplied ? "Reset your filters to see all active memories." : "Create a memory or extract useful context from a recent chat."} action={<Button variant="primary" icon={filtersApplied ? "refresh" : "plus"} onClick={() => filtersApplied ? (setQ(""), setQuery(""), setCategory(""), setPinnedOnly(false)) : openEditor()}>{filtersApplied ? "Reset filters" : "Create first memory"}</Button>} /></Panel> : groups.map((group) => <div className="memory-group" key={group.label}><div className="memory-group-label"><h2>{group.label}</h2><span>{group.items.length}</span></div>{group.items.map((memory) => <article key={memory.id} className={`memory-card${selected?.id === memory.id ? " is-selected" : ""}${memory.pinned ? " is-pinned" : ""}`}><button type="button" className="memory-card-content" onClick={() => setSelected(memory)} aria-pressed={selected?.id === memory.id}><div className="memory-card-tags"><Badge>{categoryLabel(memory.category)}</Badge>{memory.pinned && <Badge tone="success">Pinned</Badge>}<span>{new Date(memory.updated_at).toLocaleDateString()}</span></div><h3>{memory.title}</h3><p>{memory.content}</p></button><div className="memory-card-footer"><span>{memory.source_type || "manual"} · Importance {memory.importance}/5</span><Button variant="ghost" disabled={saving || !!busyId} onClick={() => void togglePin(memory)}>{memory.pinned ? "Unpin" : "Pin"}</Button><Button variant="ghost" disabled={saving || !!busyId} onClick={() => openEditor(memory)}>Edit</Button></div></article>)}</div>)}</section>
      <div className="memory-detail">{!selected ? <Panel><EmptyState icon="layers" title="Select a memory" description="Open a saved memory to inspect its context and source." /></Panel> : <Panel title="Memory details" actions={<Badge tone={selected.pinned ? "success" : "neutral"}>{selected.pinned ? "Pinned to context" : "Available for recall"}</Badge>}><div className="memory-detail-heading"><span className="memory-detail-category">{categoryLabel(selected.category)} · {selected.kind}</span><h2>{selected.title}</h2></div><div className="memory-content">{selected.content}</div><dl className="memory-properties"><div><dt>Importance</dt><dd>{selected.importance} of 5</dd></div><div><dt>Confidence</dt><dd>{Math.round(selected.confidence * 100)}%</dd></div><div><dt>Source</dt><dd>{selected.source_type || "manual"}</dd></div>{selected.source_id && <div><dt>Source ID</dt><dd className="ui-mono">{selected.source_id}</dd></div>}<div><dt>Created</dt><dd>{formatDate(selected.created_at)}</dd></div><div><dt>Updated</dt><dd>{formatDate(selected.updated_at)}</dd></div><div><dt>Last recalled</dt><dd>{formatDate(selected.last_accessed)}</dd></div></dl><div className="memory-detail-actions"><Button variant="primary" disabled={saving || !!busyId} onClick={() => openEditor(selected)}>Edit memory</Button><Button loading={busyId === selected.id} disabled={saving || !!busyId} onClick={() => void togglePin(selected)}>{selected.pinned ? "Unpin" : "Pin to context"}</Button><Button variant="danger" disabled={saving || !!busyId} onClick={() => void archive(selected)}>Archive</Button></div></Panel>}<div className="memory-tip"><AppIcon name="shield" size={17} /><p>Keep memories specific and current. Review extracted context before adding it to your library.</p></div></div>
    </div>
    <Dialog open={!!editor} onClose={() => setEditor(null)} dismissible={!saving} title={editor === "new" ? "Create a memory" : "Edit memory"} description="Save context that helps future requests." footer={<><Button disabled={saving} onClick={() => setEditor(null)}>Cancel</Button><Button variant="primary" type="submit" form="memory-edit-form" loading={saving} disabled={!draft.content.trim()}>Save memory</Button></>}>
      {formError && <Notice tone="danger">{formError}</Notice>}<form id="memory-edit-form" className="ui-form" onSubmit={(event) => void saveMemory(event)}><Field label="Title" hint="Leave blank to derive a title from the content."><input className="ui-input" value={draft.title} maxLength={160} onChange={(event) => setDraft((current) => ({ ...current, title: event.target.value }))} /></Field><Field label="Memory content"><textarea className="ui-input memory-edit-content" required maxLength={4000} value={draft.content} onChange={(event) => setDraft((current) => ({ ...current, content: event.target.value }))} placeholder="A fact, preference, procedure, or goal to remember" /></Field><div className="ui-grid"><Field label="Category"><select className="ui-input" value={draft.category} onChange={(event) => setDraft((current) => ({ ...current, category: event.target.value }))}>{CATEGORIES.map((value) => <option key={value} value={value}>{categoryLabel(value)}</option>)}</select></Field><Field label="Importance"><select className="ui-input" value={draft.importance} onChange={(event) => setDraft((current) => ({ ...current, importance: Number(event.target.value) }))}>{[1, 2, 3, 4, 5].map((value) => <option key={value} value={value}>{value} of 5</option>)}</select></Field></div><label className="memory-pinned-filter"><input type="checkbox" checked={draft.pinned} onChange={(event) => setDraft((current) => ({ ...current, pinned: event.target.checked }))} />Pin to every chat context</label></form>
    </Dialog>
    <Dialog open={!!candidates} onClose={() => setCandidates(null)} dismissible={!saving} title="Review extracted memories" description="Choose the context you want to save from your last chat." footer={<><Button disabled={saving} onClick={() => setCandidates(null)}>Cancel</Button><Button variant="primary" loading={saving} disabled={!chosen.length} onClick={() => void confirmExtraction()}>Save {chosen.length} {chosen.length === 1 ? "memory" : "memories"}</Button></>}>
      {formError && <Notice tone="danger">{formError}</Notice>}<div className="memory-candidates">{candidates?.map((candidate, index) => <label className="memory-candidate" key={index}><input type="checkbox" checked={chosen.includes(index)} onChange={(event) => setChosen((current) => event.target.checked ? [...current, index] : current.filter((item) => item !== index))} /><div><Badge>{categoryLabel(candidate.category)}</Badge><h3>{candidate.title}</h3><p>{candidate.content}</p>{typeof candidate.confidence === "number" && <span>{Math.round(candidate.confidence * 100)}% confidence</span>}</div></label>)}</div>
    </Dialog>{dialog}
  </div>;
}
