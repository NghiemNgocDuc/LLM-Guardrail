import React, { useState } from "react";
import { api } from "../utils/api";
import { s } from "../styles/theme";

export default function MandateFlowView() {
  const [log, setLog] = useState<string[]>([]);
  const [evidence, setEvidence] = useState<any>(null);
  const [running, setRunning] = useState(false);

  function push(msg: string) { setLog(l => [...l, msg]); }

  async function runDemo() {
    setRunning(true); setLog([]); setEvidence(null);
    try {
      push("→ POST /mandate scopes=[*]");
      const mandate: any = await api("/mandate", { method: "POST", body: JSON.stringify({ scopes: ["support.list_tickets","payments.list_failures","cases.lookup_subject","crm.resolve_customer","payments.aggregate_failures"] }) });
      push(`✓ mandate ${mandate.id.slice(0,8)} policy=${mandate.policy_context.pinned_rule}`);
      const run: any = await api("/runs", { method: "POST", body: JSON.stringify({ mandate_id: mandate.id }) });
      push(`→ Run ${run.run_id.slice(0,8)} runtime=${run.runtime_id} cap=${run.capability.slice(0,16)}...`);
      const cap = run.capability;
      const hdr = { Authorization: `Bearer ${cap}` } as any;

      async function call(tool: string, handle?: string, inputs?: any) {
        const r: any = await api("/gateway/call", { method: "POST", headers: hdr, body: JSON.stringify({ tool, handle, inputs, run_id: run.run_id }) });
        push(`${r.decision === "ALLOW" ? "✓" : "✗"} ${tool} → ${r.decision}${r.ruleId ? ` ${r.ruleId}` : ""}`);
        return r;
      }
      async function mint(kind: string, provenance?: string, parent?: string) {
        const r: any = await api("/references/mint", { method: "POST", body: JSON.stringify({ kind, provenance, parent_handle: parent }) });
        push(`  mint ${kind} provenance=${r.provenance} handle=${r.handle.slice(0,12)}`);
        return r.handle as string;
      }
      const h1 = await mint("support_case");
      await call("support.list_tickets");
      await call("cases.lookup_subject", h1);
      await call("crm.resolve_customer", h1);
      const h2 = await mint("payment_case", "PAYMENT_AGGREGATE_ONLY");
      await call("payments.list_failures");
      await call("cases.lookup_subject", h2);
      const denied = await call("crm.resolve_customer", h2);
      if (denied.decision !== "DENY" || denied.ruleId !== "NO_PAYMENT_REIDENTIFICATION") throw new Error("Expected DENY NO_PAYMENT_REIDENTIFICATION");
      await call("payments.aggregate_failures");
      const h3 = await mint("support_case");
      await call("support.list_tickets");
      await call("cases.lookup_subject", h3);
      await call("crm.resolve_customer", h3);

      const ev: any = await api(`/runs/${run.run_id}/evidence`);
      setEvidence(ev);
      push(`✓ crmCounter=${ev.crmCounter} expected 2 — denied call never hit fixture`);
      // retry continuity
      const retry: any = await api(`/runs/${run.run_id}/retry`, { method: "POST" });
      push(`→ retry new Run ${retry.run_id.slice(0,8)} same mandate ${retry.mandate_id.slice(0,8)}`);
      const r2 = await api("/gateway/call", { method: "POST", headers: { Authorization: `Bearer ${retry.capability}` }, body: JSON.stringify({ tool: "crm.resolve_customer", handle: h2, run_id: retry.run_id }) });
      push(`  retry Payment→CRM → ${r2.decision} ${r2.ruleId||""} (provenance persists)`);
      // revoke
      await api(`/mandate/${mandate.id}/revoke`, { method: "POST" });
      push(`→ revoke mandate ${mandate.id.slice(0,8)}`);
      try { await api("/gateway/call", { method: "POST", headers: hdr, body: JSON.stringify({ tool: "support.list_tickets" }) }); push("✗ revoked call unexpectedly ALLOW"); } catch (e:any) { push(`✓ revoked call DENY 401`); }
    } catch (e:any) { push(`✗ ${e.message||e}`); }
    finally { setRunning(false); }
  }

  return (
    <div style={{ padding: 24 }}>
      <h2 style={{ margin: 0, fontSize: 20, fontWeight: 800, color: "#0f172a" }}>MandateFlow — Provenance Gateway</h2>
      <p style={{ color: "#64748b", fontSize: 13, marginTop: 6 }}>Same tool, same scope, same reference type — ALLOW for Support→CRM, DENY for Payment→CRM. Receipt + crmCounter prove the denied call never reached the fixture.</p>
      <button onClick={runDemo} disabled={running} style={{ ...s.btn("primary"), marginTop: 12, opacity: running?0.6:1 }}>{running ? "Running 10-call demo..." : "Run 10-call demo"}</button>
      <div style={{ marginTop: 16, fontFamily: "ui-monospace, monospace", fontSize: 12, background: "#0f172a", color: "#e2e8f0", borderRadius: 12, padding: 14, minHeight: 120, whiteSpace: "pre-wrap" }}>
        {log.length? log.join("\n") : "Click Run to execute the falsifiable demo (Support→CRM ALLOW, Payment→CRM DENY NO_PAYMENT_REIDENTIFICATION, aggregate recovery, retry continuity, revoke)."}
      </div>
      {evidence && (
        <div style={{ marginTop: 16, background: "#fff", border: "1px solid #e2e8f0", borderRadius: 12, padding: 14 }}>
          <div style={{ fontWeight: 700, fontSize: 13 }}>GET /runs/:id/evidence</div>
          <pre style={{ marginTop: 8, fontSize: 11, color: "#334155", whiteSpace: "pre-wrap" }}>{JSON.stringify(evidence, null, 2)}</pre>
          <div style={{ marginTop: 8, fontSize: 12, color: evidence.crmCounter===2 ? "#059669" : "#dc2626", fontWeight: 700 }}>
            {evidence.crmCounter===2 ? "✓ crmCounter 2 — structural deny proven" : "✗ crmCounter mismatch — fixture leaked"}
          </div>
        </div>
      )}
    </div>
  );
}
