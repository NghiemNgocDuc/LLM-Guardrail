import { useRef, useState } from "react";
import { api, ApiError } from "../utils/api";
import AppIcon from "../components/AppIcon";
import { Badge, Button, EmptyState, Notice, PageHeader, Panel } from "../components/ui";
import "../styles/resources.css";

type Decision = { decision: "ALLOW" | "DENY"; ruleId?: string };
type Mandate = { id: string; policy_context: { pinned_rule: string } };
type Run = { run_id: string; runtime_id: string; mandate_id: string; capability: string };
type Trace = { text: string; kind: "info" | "success" | "deny" };
export default function MandateFlowView() {
  const [trace, setTrace] = useState<Trace[]>([]), [evidence, setEvidence] = useState<Record<string, any> | null>(null), [bench, setBench] = useState<Record<string, any> | null>(null);
  const [running, setRunning] = useState(false), [benchmarking, setBenchmarking] = useState(false), [phase, setPhase] = useState(-1), [error, setError] = useState(""), [completed, setCompleted] = useState(false);
  const pending = useRef(false);
  function push(text: string, kind: Trace["kind"] = "info") { setTrace(items => [...items, { text, kind }]); }
  async function runDemo() {
    if (pending.current) return; pending.current = true; setRunning(true); setTrace([]); setEvidence(null); setError(""); setCompleted(false); setPhase(0);
    try {
      const mandate = await api<Mandate>("/mandate", { method: "POST", body: { scopes: ["support.list_tickets", "payments.list_failures", "cases.lookup_subject", "crm.resolve_customer", "payments.aggregate_failures"] } });
      push("Created mandate " + mandate.id.slice(0, 8) + " · pinned rule " + mandate.policy_context.pinned_rule, "success");
      const run = await api<Run>("/runs", { method: "POST", body: { mandate_id: mandate.id } });
      push("Started run " + run.run_id.slice(0, 8) + " · runtime " + run.runtime_id, "success"); setPhase(1);
      const headers = { Authorization: "Bearer " + run.capability };
      async function call(tool: string, handle?: string) {
        const value = await api<Decision>("/gateway/call", { method: "POST", headers, body: { tool, handle, run_id: run.run_id } });
        push(tool + " → " + value.decision + (value.ruleId ? " · " + value.ruleId : ""), value.decision === "ALLOW" ? "success" : "deny"); return value;
      }
      async function mint(kind: string, provenance?: string) {
        const value = await api<{ handle: string; provenance: string }>("/references/mint", { method: "POST", body: { kind, provenance } });
        push("Minted " + kind + " · " + value.provenance); return value.handle;
      }
      const support = await mint("support_case");
      await call("support.list_tickets"); await call("cases.lookup_subject", support); await call("crm.resolve_customer", support);
      const payment = await mint("payment_case", "PAYMENT_AGGREGATE_ONLY");
      await call("payments.list_failures"); await call("cases.lookup_subject", payment);
      const denied = await call("crm.resolve_customer", payment);
      if (denied.decision !== "DENY" || denied.ruleId !== "NO_PAYMENT_REIDENTIFICATION") throw new Error("The payment reference was not blocked by the expected rule.");
      await call("payments.aggregate_failures");
      const secondSupport = await mint("support_case");
      await call("support.list_tickets"); await call("cases.lookup_subject", secondSupport); await call("crm.resolve_customer", secondSupport);
      setPhase(2);
      const receipt = await api<Record<string, any>>("/runs/" + run.run_id + "/evidence"); setEvidence(receipt);
      if (receipt.crmCounter !== 2) throw new Error("Evidence mismatch: expected two CRM fixture calls, received " + receipt.crmCounter + ".");
      push("Evidence verified · CRM fixture was called exactly twice", "success");
      const retry = await api<Run>("/runs/" + run.run_id + "/retry", { method: "POST" });
      const retryDecision = await api<Decision>("/gateway/call", { method: "POST", headers: { Authorization: "Bearer " + retry.capability }, body: { tool: "crm.resolve_customer", handle: payment, run_id: retry.run_id } });
      if (retryDecision.decision !== "DENY" || retryDecision.ruleId !== "NO_PAYMENT_REIDENTIFICATION") throw new Error("The provenance rule did not persist on retry.");
      push("Retry preserved payment provenance → DENY", "deny"); setPhase(3);
      await api("/mandate/" + mandate.id + "/revoke", { method: "POST" }); push("Revoked mandate " + mandate.id.slice(0, 8), "success");
      let revocationVerified = false;
      try { await api("/gateway/call", { method: "POST", headers, body: { tool: "support.list_tickets" } }); }
      catch (error) { if (error instanceof ApiError && error.status === 401) revocationVerified = true; else throw error; }
      if (!revocationVerified) throw new Error("The revoked capability unexpectedly remained usable.");
      push("Revoked capability rejected with HTTP 401", "deny"); setCompleted(true);
    } catch (error) { const message = error instanceof Error ? error.message : "The demo couldn't complete."; setError(message); push(message, "deny"); }
    finally { pending.current = false; setRunning(false); }
  }
  async function benchmark() {
    if (pending.current) return; pending.current = true; setBenchmarking(true); setError("");
    try { setBench(await api("/mandate/bench", { method: "POST", body: { iterations: 100 } })); }
    catch (error) { setError(error instanceof Error ? error.message : "The benchmark couldn't complete."); }
    finally { pending.current = false; setBenchmarking(false); }
  }
  return <div className="mandate-page">
    <PageHeader eyebrow="Provenance gateway" title="A permission that remembers its origin." description="Follow a reference through support and payment workflows. Verify that provenance rules survive retries and that revocation closes the capability." actions={<Button variant="primary" icon="arrow" loading={running} disabled={benchmarking} onClick={() => void runDemo()}>{completed ? "Run demo again" : "Run 10-call demo"}</Button>} />
    {error && <Notice tone="danger">{error}</Notice>}{completed && <Notice tone="success">Demo complete. The payment reference stayed blocked, two support calls reached CRM, and the revoked capability was rejected.</Notice>}
    <div className="mandate-intro"><Panel title="Same tool. Different provenance." description="The demo evaluates the same CRM tool with two reference origins."><div className="mandate-paths"><div className="mandate-path"><AppIcon name="team" size={23} /><div><strong>Support → CRM</strong><p>A support reference may resolve its customer.</p></div><Badge tone="success">Expected: allow</Badge></div><div className="mandate-path"><AppIcon name="card" size={23} /><div><strong>Payment → CRM</strong><p>An aggregate-only payment reference must stay anonymous.</p></div><Badge tone="warning">Expected: deny</Badge></div></div></Panel><Panel title="What the demo verifies" description="These are fixture checks with real gateway responses."><ol className="resource-checklist"><li>A mandate pins the policy and starts a capability-scoped run.</li><li>Ten tool calls test support access, payment denial, and aggregate recovery.</li><li>An evidence receipt counts actual CRM fixture calls.</li><li>A retry keeps provenance; revocation rejects the old capability.</li></ol></Panel></div>
    <Panel title="Execution trace" description={running ? "Running the gateway checks…" : completed ? "All checks completed." : trace.length ? "Review the trace and retry after resolving the error." : "Run the demo to inspect each decision."} actions={<Badge tone={running ? "info" : completed ? "success" : error ? "danger" : "neutral"}>{running ? "In progress" : completed ? "Verified" : error ? "Incomplete" : "Ready"}</Badge>}>
      <div className="mandate-progress" aria-label="Demo stages">{["Create capability", "Evaluate tools", "Verify & retry", "Revoke access"].map((label, index) => <div key={label} data-state={phase === index && running ? "active" : phase >= index ? "complete" : "pending"}><span>{phase > index || completed ? "✓" : "0" + (index + 1)}</span><strong>{label}</strong></div>)}</div>
      {trace.length ? <ol className="mandate-trace" aria-label="Gateway execution decisions">{trace.map((item, index) => <li key={index} data-kind={item.kind}><span>{String(index + 1).padStart(2, "0")}</span><AppIcon name={item.kind === "success" ? "check" : item.kind === "deny" ? "shield" : "arrow"} size={14} /><div>{item.text}</div></li>)}</ol> : <EmptyState icon="code" title="Every decision leaves a trace." description="Start the fixture demo to see allowed calls, blocked calls, retries, and revocation in order." />}
      <span className="sr-only" role="status">{running ? "Running stage " + (phase + 1) : completed ? "All demo checks verified." : error ? "Demo incomplete: " + error : ""}</span>
    </Panel>
    <div className="ui-grid"><Panel title="Evidence receipt" description="A blocked payment-to-CRM call must never reach the fixture.">{evidence ? <><div className="mandate-evidence-summary"><strong>{evidence.crmCounter ?? "—"}</strong><div><Badge tone={evidence.crmCounter === 2 ? "success" : "danger"}>{evidence.crmCounter === 2 ? "Expected count verified" : "Count mismatch"}</Badge><p>CRM calls recorded by the fixture</p></div></div><details className="resource-raw"><summary>Inspect the full receipt</summary><pre>{JSON.stringify(evidence, null, 2)}</pre></details></> : <EmptyState icon="logs" title="Evidence appears after the run." description="The receipt records the decisions and actual fixture calls." />}</Panel>
    <Panel title="Runtime benchmark" description="Compare Go and Python on 100 iterations in this deployment." actions={<Button icon="chart" loading={benchmarking} disabled={running} onClick={() => void benchmark()}>Run benchmark</Button>}>{bench ? <><Notice tone={bench.go_available ? "success" : "info"}>{bench.go_available ? Number.isFinite(bench.speedup_go_vs_python) ? "Measured Go / Python speedup: " + bench.speedup_go_vs_python.toFixed(2) + "×." : "Both runtimes responded. Inspect the timings below." : "Go runtime unavailable. Results include the Python fallback only."}</Notice><details className="resource-raw" open><summary>Inspect benchmark timings</summary><pre>{JSON.stringify(bench, null, 2)}</pre></details></> : <EmptyState icon="activity" title="Measure your runtime." description="Run the benchmark to get actual timings. Results depend on the current deployment." />}</Panel></div>
  </div>;
}
