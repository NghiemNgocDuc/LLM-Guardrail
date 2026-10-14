import { useCallback, useEffect, useRef, useState } from "react";
import { api, BASE_URL } from "../utils/api";
import AppIcon from "../components/AppIcon";
import { Badge, Button, EmptyState, LoadingState, Notice, PageHeader, Panel, TableWrap } from "../components/ui";
import type { ServiceHealth } from "../api-supplementary";
import "../styles/observability.css";

type BasicHealth = { status: string; env: string; backend: string; database: string };
type DetailedHealth = { overall: string; database: ServiceHealth; redis: ServiceHealth; vectorstore: ServiceHealth };
type BreakerHealth = { overall: string; breakers: Record<string, string> };
type BasicSnapshot = { data: BasicHealth; httpStatus: number; roundTripMs: number };

async function getBasicHealth(): Promise<BasicSnapshot> {
  const started = performance.now();
  const response = await fetch(`${BASE_URL}/health`, { cache: "no-store" });
  const data = await response.json() as BasicHealth;
  if ((!response.ok && response.status !== 503) || typeof data.status !== "string") throw new Error(`Health endpoint returned HTTP ${response.status}.`);
  return { data, httpStatus: response.status, roundTripMs: Math.round(performance.now() - started) };
}

function ServiceCard({ name, description, data, optional = false, initialized = false }: {
  name: string; description: string; data?: ServiceHealth; optional?: boolean; initialized?: boolean;
}) {
  const unconfigured = data?.status === "not_configured";
  const tone = !data || unconfigured ? "neutral" : data.status === "ok" ? "success" : "danger";
  const status = !data ? "Unavailable" : unconfigured ? "Not configured" : data.status === "ok" ? initialized ? "Initialized" : "Responding" : data.status.replaceAll("_", " ");
  return <div className="obs-service-card">
    <div className="obs-service-heading"><span className="obs-service-icon"><AppIcon name="layers" /></span><h3>{name}</h3><Badge tone={tone}>{status}</Badge></div>
    <p>{description}</p>
    <div className="obs-service-bottom">{typeof data?.latency_ms === "number" ? <><span>Check latency</span><strong>{data.latency_ms.toLocaleString()} <small>ms</small></strong></> : <span>{unconfigured && optional ? "Optional dependency" : initialized ? "Initialization state reported by the API" : "No latency reported"}</span>}</div>
    {(data?.detail || data?.note) && <p className="obs-service-note">{data.detail || data.note}</p>}
  </div>;
}

export default function HealthView() {
  const [basic, setBasic] = useState<BasicSnapshot | null>(null);
  const [detailed, setDetailed] = useState<DetailedHealth | null>(null);
  const [breakers, setBreakers] = useState<BreakerHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [errors, setErrors] = useState<string[]>([]);
  const [lastChecked, setLastChecked] = useState<Date | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const busy = useRef(false);
  const mounted = useRef(true);

  const check = useCallback(async () => {
    if (busy.current) return;
    busy.current = true; setLoading(true);
    const results = await Promise.allSettled([getBasicHealth(), api<DetailedHealth>("/health/detailed"), api<BreakerHealth>("/health/breakers")]);
    if (mounted.current) {
      if (results[0].status === "fulfilled") setBasic(results[0].value);
      if (results[1].status === "fulfilled") setDetailed(results[1].value);
      if (results[2].status === "fulfilled") setBreakers(results[2].value);
      const names = ["API availability", "Dependency checks", "Circuit breakers"];
      setErrors(results.flatMap((result, index) => result.status === "rejected" ? [`${names[index]}: ${result.reason instanceof Error ? result.reason.message : String(result.reason)}`] : []));
      if (results.every((result) => result.status === "fulfilled")) setLastChecked(new Date());
      setLoading(false);
    }
    busy.current = false;
  }, []);
  useEffect(() => { mounted.current = true; void check(); return () => { mounted.current = false; }; }, [check]);
  useEffect(() => { if (!autoRefresh) return; const timer = window.setInterval(() => void check(), 30_000); return () => window.clearInterval(timer); }, [autoRefresh, check]);
  const degraded = basic?.data.status === "degraded" || detailed?.overall === "degraded" || breakers?.overall === "degraded";
  const hasSnapshot = !!(basic || detailed || breakers);
  const overall = errors.length ? "Checks incomplete" : degraded ? "Needs attention" : hasSnapshot ? "Core services responding" : "Checking system";

  return <div className="obs-page">
    <PageHeader eyebrow="OPERATIONS" title="System health" description="Current API availability, dependencies, and provider circuit states." actions={<Button icon="refresh" loading={loading} onClick={() => void check()}>Refresh checks</Button>} />
    <div className="obs-health-summary"><span className={`obs-health-symbol${degraded || errors.length ? " is-warning" : ""}`}><AppIcon name="activity" size={25} /></span><div><h2>{overall}</h2><p>{lastChecked ? `Last complete check ${lastChecked.toLocaleString()}` : "Waiting for a complete set of checks"}{errors.length && lastChecked ? " · Previous results remain visible" : ""}</p></div><label className="obs-checkbox"><input type="checkbox" checked={autoRefresh} onChange={(event) => setAutoRefresh(event.target.checked)} />Refresh every 30 seconds</label></div>
    {!!errors.length && <Notice tone="danger"><strong>Some checks couldn't complete.</strong><ul>{errors.map((error) => <li key={error}>{error}</li>)}</ul></Notice>}
    {loading && !hasSnapshot ? <LoadingState label="Checking system health" /> : <>
      <div className="obs-services-grid"><ServiceCard name="PostgreSQL" description="Database query availability." data={detailed?.database} /><ServiceCard name="Redis" description="Shared rate limiting and cache availability." data={detailed?.redis} optional /><ServiceCard name="Vector store" description="Semantic memory initialization." data={detailed?.vectorstore} optional initialized /></div>
      <div className="obs-health-panels">
        <Panel title="API availability" description="The public health endpoint used by uptime monitoring.">
          {basic ? <dl className="obs-properties"><div><dt>Availability</dt><dd><Badge tone={basic.data.status === "ok" ? "success" : "danger"}>{basic.data.status === "ok" ? "Responding" : "Degraded"}</Badge></dd></div><div><dt>HTTP status</dt><dd className="obs-mono">{basic.httpStatus}</dd></div><div><dt>API round trip</dt><dd>{basic.roundTripMs.toLocaleString()} ms</dd></div><div><dt>Database</dt><dd>{basic.data.database}</dd></div><div><dt>Environment</dt><dd className="obs-mono">{basic.data.env}</dd></div><div><dt>Default provider</dt><dd className="obs-mono">{basic.data.backend}</dd></div></dl> : <EmptyState icon="activity" title="API check unavailable" description="Refresh to retry the availability check." />}
        </Panel>
        <Panel title="Provider circuit breakers" description="Circuit state controls whether a provider accepts another request.">
          {!breakers ? <EmptyState icon="layers" title="Circuit states unavailable" description="Refresh to retry this check." /> : Object.keys(breakers.breakers || {}).length === 0 ? <EmptyState icon="shield" title="No provider circuits registered" description="Circuit states appear after traffic reaches a model provider." /> : <TableWrap label="Provider circuit states"><table className="obs-table"><thead><tr><th>Provider</th><th>State</th><th>Request behavior</th></tr></thead><tbody>{Object.entries(breakers.breakers).map(([name, state]) => <tr key={name}><td className="obs-mono">{name}</td><td><Badge tone={state === "closed" ? "success" : state === "open" ? "danger" : "warning"}>{state.replaceAll("_", " ")}</Badge></td><td>{state === "closed" ? "Accepting requests" : state === "open" ? "Requests paused" : "Allowing a recovery probe"}</td></tr>)}</tbody></table></TableWrap>}
        </Panel>
      </div>
      <p className="obs-footnote">These are current checks. Historical uptime is available through your external uptime monitor.</p>
    </>}
  </div>;
}
