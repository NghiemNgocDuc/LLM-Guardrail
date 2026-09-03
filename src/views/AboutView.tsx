import React, { useState, useEffect } from "react";
import { api } from "../utils/api";
import { s } from "../styles/theme";

export default function AboutView() {
  const [activeTab, setActiveTab] = useState<"quickstart" | "api" | "skills">("quickstart");
  const [copied, setCopied] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<any>(null);
  const [metricsLoading, setMetricsLoading] = useState(false);
  const [metricsError, setMetricsError] = useState("");
  useEffect(() => {
    setMetricsLoading(true);
    api<any>("/skills/managed/metrics").then(setMetrics).catch((e: Error) => setMetricsError(e.message)).finally(() => setMetricsLoading(false));
  }, []);
  const copy = (t: string, id: string) => {
    navigator.clipboard.writeText(t);
    setCopied(id);
    setTimeout(() => setCopied(null), 1500);
  };

  return (
    <div style={{ maxWidth: 980, margin: "0 auto" }}>
      {/* Hero */}
      <div style={{ ...s.heroPanel, padding: 28, position: "relative", overflow: "hidden" }}>
        <div style={{ position: "absolute", inset: 0, background: "radial-gradient(600px 220px at 92% 0%, rgba(45,212,191,0.12), transparent 65%)", pointerEvents: "none" }} />
        <div style={{ position: "relative" }}>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center", marginBottom: 12 }}>
            <span style={{ ...s.badge("delivered"), background: "#0f766e", color: "#fff", borderColor: "#0f766e" }}>v1.0 • production ready</span>
            <span style={{ fontSize: 11, color: "#7b8a9d", fontWeight: 600 }}>MIT • Docker • Self-hostable</span>
            <span style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
              <a href="https://llm-guardrail.onrender.com" target="_blank" rel="noreferrer" style={{ ...s.btn("secondary"), padding: "6px 12px", fontSize: 12, textDecoration: "none" }}>Live demo</a>
              <a href="https://github.com" target="_blank" rel="noreferrer" style={{ ...s.btn("primary"), padding: "6px 12px", fontSize: 12, textDecoration: "none" }}>GitHub</a>
            </span>
          </div>
          <div style={{ fontSize: 34, fontWeight: 900, color: "#102033", lineHeight: 1.1, letterSpacing: "-0.02em" }}>
            AI Guardrails <span style={{ color: "#0f766e" }}>Gateway</span>
          </div>
          <div style={{ fontSize: 15, color: "#405166", lineHeight: 1.6, marginTop: 10, maxWidth: 720 }}>
            A multi-tenant safety layer that sits between your users, agents and any LLM. Every prompt is checked, every response is verified, every skill is scanned — before anything reaches the model or your users.
          </div>
          <div style={{ display: "flex", gap: 10, marginTop: 18, flexWrap: "wrap" }}>
            <span style={{ fontSize: 12, color: "#0f766e", background: "#ecfdf5", border: "1px solid #a7f3d0", padding: "6px 10px", borderRadius: 999, fontWeight: 700 }}>FastAPI + React + Postgres + Redis</span>
            <span style={{ fontSize: 12, color: "#7b8a9d" }}>Groq • OpenAI • Anthropic • Gemini • Ollama • OpenAI-compatible</span>
          </div>
        </div>
      </div>

      {/* Announcements — what's new */}
      <div style={{ ...s.card, marginBottom: 18, border: "1px solid #0f766e", background: "linear-gradient(135deg,#ecfdf5 0%,#f0fdf9 100%)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12, flexWrap: "wrap", gap: 8 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ background: "#0f766e", color: "#fff", fontSize: 11, fontWeight: 800, width: 28, height: 28, borderRadius: 8, display: "grid", placeItems: "center" }}>NEW</span>
            <div style={s.sectionTitle}>What's new</div>
            <span style={{ background: "#f59e0b", color: "#fff", fontSize: 10, fontWeight: 800, padding: "3px 8px", borderRadius: 999 }}>NEW</span>
          </div>
          <span style={{ fontSize: 11, color: "#64748b" }}>Latest updates — same About page</span>
        </div>
        <div style={{ display: "grid", gap: 10 }}>
          {[
            { date: "2026-08-30", tag: "Teams", color: "#0f766e", title: "Teams & Projects — Team 1, Team 2… auto-named, switch via Teams hub", desc: "Create Team 1, Team 2 by default, rename inline (Team 1 → My Project), click Team 1/2 to work there, ← back. Caps 500 members & 500 terms/team, 500 teams/user. Leader can be in many teams." },
            { date: "2026-08-30", tag: "Multi-leader", color: "#6366f1", title: "Multiple leaders per team — promote, decline, auto-promote on leave", desc: "Any leader can promote Member → Admin (no transfer). Decline needs ≥1 other leader. If a leader leaves, previous leader or random member is auto-promoted so team always has a leader." },
            { date: "2026-08-29", tag: "Latency", color: "#0ea5e9", title: "p95 185ms → 3.97ms — LRU cache + short-circuit + async Groq", desc: "Guardrail p95 3.97ms (p50 2.74ms) via Rust + LRU 1k + secret short-circuit, wl3 Groq fire-and-forget. Provider streams ~100ms, not 5s. Bench tests/test_latency_benchmark.py." },
            { date: "2026-08-29", tag: "Benchmark", color: "#8b5cf6", title: "Combined benchmark — llm-redactor + JailbreakBench + NotInject live", desc: "Single macro-F1 avg(wl1,wl2,wl4, jailbreak, 1-FP) — GET /skills/managed/metrics/combined (150/sample, ~15s) + Export PDF evidence pack (no email metadata)." },
            { date: "2026-08-28", tag: "Skill Guard", color: "#f59e0b", title: "Skill Guard — conflict + identical-block + Test new block", desc: "Team lead conflict check (API-key leak vs existing skills), identical-block (is ChatGPT key already blocked?), auto-generated 7 tests that must PASS before save." },
          ].map(a => (
            <div key={a.title} style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, padding: 12, display: "flex", gap: 12 }}>
              <div style={{ flexShrink: 0, textAlign: "center", minWidth: 64 }}>
                <div style={{ fontSize: 11, fontWeight: 800, color: a.color }}>{a.date}</div>
                <span style={{ background: a.color, color: "#fff", fontSize: 10, fontWeight: 800, padding: "2px 6px", borderRadius: 999, display: "inline-block", marginTop: 4 }}>{a.tag}</span>
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13, fontWeight: 800, color: "#102033" }}>{a.title}</div>
                <div style={{ fontSize: 12, color: "#475569", lineHeight: 1.6, marginTop: 4 }}>{a.desc}</div>
              </div>
            </div>
          ))}
        </div>
        <div style={{ fontSize: 11, color: "#64748b", marginTop: 10, textAlign: "center" }}>Add new items by editing the array in <code style={code}>src/views/AboutView.tsx:48</code> — or wire <code style={code}>GET /announcements</code> later for admin-published updates.</div>
      </div>

      {/* What is it */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(320px,1fr))", gap: 18, marginBottom: 18 }}>
        <div style={s.card}>
          <div style={s.sectionTitle}>What it is</div>
          <div style={{ fontSize: 14, color: "#27394f", lineHeight: 1.75 }}>
            <p style={{ margin: "0 0 10px 0" }}>
              <strong style={{ color: "#102033" }}>Not a model — a gate.</strong> Your app calls <code style={code}>/chat</code> instead of the provider directly. The gateway authenticates with a scoped <code style={code}>grg_</code> key, applies your organization policy, and only then forwards to Groq/OpenAI/etc.
            </p>
            <p style={{ margin: 0 }}>
              Think <strong style={{ color: "#0f766e" }}>Cloudflare for LLM traffic</strong> plus <strong style={{ color: "#0f766e" }}>GitHub Advanced Security for agent skills</strong>: rate limits, PII/secrets/jailbreak filters, semantic similarity, and a final OPA/Rego rule that you write — fail-closed.
            </p>
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 14, flexWrap: "wrap" }}>
            <span style={s.badge("input_blocked")}>input_blocked</span>
            <span style={s.badge("output_blocked")}>output_blocked</span>
            <span style={s.badge("delivered")}>delivered</span>
            <span style={s.badge("rate_limited")}>rate_limited</span>
          </div>
        </div>
        <div style={{ ...s.card, padding: 0, overflow: "hidden", background: "#0f172a", borderColor: "#1e293b" }}>
          <div style={{ padding: "12px 16px", borderBottom: "1px solid #1e293b", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: 11, color: "#94a3b8", fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" }}>Request flow</span>
            <span style={{ fontSize: 10, color: "#5eead4", background: "rgba(45,212,191,0.14)", padding: "4px 8px", borderRadius: 999 }}>120ms avg</span>
          </div>
          <div style={{ padding: 16, fontFamily: "ui-monospace, monospace", fontSize: 11, lineHeight: 1.7, color: "#cbd5e1" }}>
            <div><span style={{ color: "#5eead4" }}>Client</span> --X-Api-Key: grg_...--&gt; <span style={{ color: "#94a3b8" }}>Nginx :80</span></div>
            <div style={{ color: "#475569" }}>                 |</div>
            <div><span style={{ color: "#fde68a" }}>FastAPI</span>  auth + rate limit + Teams hub (Team 1,2… switch)</div>
            <div style={{ color: "#475569" }}>                 |</div>
            <div><span style={{ color: "#fca5a5" }}>Input guardrails</span>  secrets <span style={{ color: "#64748b" }}>|</span> PII <span style={{ color: "#64748b" }}>|</span> injection <span style={{ color: "#64748b" }}>|</span> jailbreak <span style={{ color: "#64748b" }}>|</span> OPA/Rego <span style={{ color: "#5eead4" }}>p95 3.97ms</span></div>
            <div style={{ color: "#475569" }}>                 | pass</div>
            <div><span style={{ color: "#93c5fd" }}>Provider</span>  Groq / OpenAI / Anthropic / Ollama (stream)</div>
            <div style={{ color: "#475569" }}>                 |</div>
            <div><span style={{ color: "#fca5a5" }}>Output guardrails</span>  leakage <span style={{ color: "#64748b" }}>|</span> toxic <span style={{ color: "#64748b" }}>|</span> topic <span style={{ color: "#64748b" }}>|</span> schema</div>
            <div style={{ color: "#475569" }}>                 |</div>
            <div><span style={{ color: "#5eead4" }}>Audit</span>  Postgres + Redis • <span style={{ color: "#94a3b8" }}>X-Request-ID</span> • Evidence PDF</div>
          </div>
          <div style={{ padding: "10px 16px", background: "#020617", borderTop: "1px solid #1e293b", display: "flex", gap: 8, flexWrap: "wrap" }}>
            <span style={{ fontSize: 10, color: "#64748b" }}>PostgreSQL audit • Redis windows • OPA sidecar • Fail-closed on timeout</span>
          </div>
        </div>
      </div>

      {/* Features */}
      <div style={s.card}>
        <div style={s.sectionTitle}>Core features</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(260px,1fr))", gap: 14 }}>
          {[
            { t: "Gateway, not SDK", d: "One endpoint for every backend. Switch Groq → OpenAI without touching app code. Fallback chain per-org + global.", bg: "#f0fdfa" },
            { t: "Input guardrails", d: "Block secrets (gsk_/sk-), PII (email/SSN/CC), prompt injection, jailbreak, semantic near-duplicates. Rust regex + Luhn, p95 3.97ms.", bg: "#fffbeb" },
            { t: "Output guardrails", d: "Catch credential leakage, toxicity, blocked topics, and JSON schema violations before the user sees them.", bg: "#fff1f2" },
            { t: "Skill scanner", d: "POST /skills/scan for SKILL.md, system prompts, MCP rules. Flags env assignments, private IPs, destructive shell/SQL.", bg: "#f5f3ff" },
            { t: "Teams & projects", d: "Team 1, Team 2… auto-named, rename inline, switch via Teams hub. Leader can be in many teams. Cap 500 members & 500 terms/team, 500 teams/user.", bg: "#ecfdf5" },
            { t: "Multi-leader", d: "Team can have multiple leaders. Any leader can promote member → leader. Decline leader needs ≥1 other leader; auto-promote on leave (previous leader or random).", bg: "#f0fdfa" },
            { t: "Per-org policy", d: "Each team tunes its own JSON policy + optional Rego (OPA) as final gate. Diff, replay, and export for audit.", bg: "#eff6ff" },
            { t: "Audit + analytics", d: "Immutable request_logs, top blocked reasons, false-positive candidates, per-user token breakdown, GraphQL mirror. Evidence PDF export.", bg: "#f0fdfa" },
          ].map(f => (
            <div key={f.t} style={{ background: f.bg, border: "1px solid #e7eef6", borderRadius: 12, padding: 16 }}>
              <div style={{ fontSize: 13, fontWeight: 800, color: "#102033" }}>{f.t}</div>
              <div style={{ fontSize: 13, color: "#405166", lineHeight: 1.6, marginTop: 6 }}>{f.d}</div>
            </div>
          ))}
        </div>
      </div>

      {/* How to use */}
      <div style={{ ...s.card, marginTop: 18 }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap", alignItems: "center", marginBottom: 14 }}>
          <div style={s.sectionTitle}>How to use</div>
          <div style={{ display: "flex", background: "#f1f5f9", borderRadius: 999, padding: 3, gap: 3 }}>
            {[
              { id: "quickstart", label: "Quickstart" },
              { id: "api", label: "API" },
              { id: "skills", label: "Skills" },
            ].map(t => (
              <button key={t.id} onClick={() => setActiveTab(t.id as any)} style={{ padding: "7px 14px", borderRadius: 999, border: "none", fontSize: 12, fontWeight: 800, cursor: "pointer", background: activeTab === t.id ? "#0f766e" : "transparent", color: activeTab === t.id ? "#fff" : "#405166" }}>{t.label}</button>
            ))}
          </div>
        </div>

        {activeTab === "quickstart" && (
          <div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", gap: 12, marginBottom: 16 }}>
              {[
                { n: "1", t: "Configure", d: "cp .env.example .env → set SECRET_KEY, GROQ_API_KEY, POSTGRES_PASSWORD. For multi-LLM, set OPENAI_ANTHROPIC_GEMINI keys." },
                { n: "2", t: "Run", d: "docker compose up -d --build → open http://localhost:8080 (dashboard) and /health. Migrations run automatically." },
                { n: "3", t: "Create org + key", d: "Sign up → Dashboard shows org_id → API Keys → New key (grg_...). Use it as X-Api-Key for /chat." },
              ].map(s => (
                <div key={s.n} style={{ background: "#f8fafc", border: "1px solid #e7eef6", borderRadius: 12, padding: 16 }}>
                  <div style={{ width: 28, height: 28, borderRadius: 999, background: "#0f766e", color: "#fff", display: "grid", placeItems: "center", fontSize: 12, fontWeight: 800 }}>{s.n}</div>
                  <div style={{ fontWeight: 800, color: "#102033", marginTop: 10, fontSize: 13 }}>{s.t}</div>
                  <div style={{ fontSize: 13, color: "#405166", lineHeight: 1.6, marginTop: 6 }}>{s.d}</div>
                </div>
              ))}
            </div>
            <CodeBlock id="qs-docker" code={`cp .env.example .env\n# edit SECRET_KEY, GROQ_API_KEY, POSTGRES_PASSWORD\ndocker compose up -d --build\nopen http://localhost:8080`} onCopy={copy} copied={copied} />
          </div>
        )}

        {activeTab === "api" && (
          <div style={{ display: "grid", gap: 12 }}>
            <div style={{ fontSize: 13, color: "#405166", lineHeight: 1.6 }}>Three calls to go live. Replace <code style={code}>grg_...</code> with the key you created in the dashboard.</div>
            <CodeBlock id="api-signup" label="1 — Sign up" code={`curl -X POST http://localhost:8080/auth/signup \\\n  -H "Content-Type: application/json" \\\n  -d '{"email":"you@co.com","password":"secret123","full_name":"Duc","org_name":"Acme"}'`} onCopy={copy} copied={copied} />
            <CodeBlock id="api-key" label="2 — Create key" code={`curl -X POST http://localhost:8080/api-keys \\\n  -H "Authorization: Bearer <access_token>" \\\n  -d '{"name":"my-app-key"}'\n# → {"raw_key":"grg_..."}  — copy once`} onCopy={copy} copied={copied} />
            <CodeBlock id="api-chat" label="3 — Chat (guarded)" code={`curl -X POST http://localhost:8080/chat \\\n  -H "X-Api-Key: grg_..." -H "Content-Type: application/json" \\\n  -d '{"prompt":"What is the capital of France?"}'\n# → {"response":"Paris","status":"delivered","latency_ms": 340}`} onCopy={copy} copied={copied} />
            <div style={{ fontSize: 12, color: "#7b8a9d", background: "#f8fafc", border: "1px solid #e7eef6", padding: "10px 12px", borderRadius: 8 }}>
              Blocked example returns <code style={code}>{'{"status":"input_blocked","input_guard":{"reason":"Secret detected: groq_api_key"}}'}</code> — no LLM call, no tokens.
            </div>
          </div>
        )}

        {activeTab === "skills" && (
          <div style={{ display: "grid", gap: 12 }}>
            <div style={{ fontSize: 13, color: "#405166", lineHeight: 1.6 }}>Scan an agent <code style={code}>SKILL.md</code> before publishing. Dashboard: <strong>Rejected access</strong> or API:</div>
            <CodeBlock id="skill-scan" label="Scan a skill" code={`curl -X POST http://localhost:8080/skills/scan \\\n  -H "Authorization: Bearer <token>" \\\n  -d '{"content":"---\\nname: my-skill\\n---\\nDo not embed secrets","filename":"SKILL.md"}'\n# → {"safe": false, "risk_score": 0.9, "findings": [...]}`} onCopy={copy} copied={copied} />
            <div style={s.alert("info")}>Local git hook: <code style={code}>./scripts/install-git-hooks.sh</code> — scans <code style={code}>.cursor/skills/</code> on push. CI also runs on PRs and pushes touching skills.</div>
          </div>
        )}
      </div>

      {/* Tech + services */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(320px,1fr))", gap: 18, marginTop: 18 }}>
        <div style={s.card}>
          <div style={s.sectionTitle}>Tech stack</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, fontSize: 13 }}>
            <div><strong style={{ color: "#102033" }}>API</strong><br /><span style={{ color: "#405166" }}>FastAPI • Uvicorn • Pydantic v2 • SQLAlchemy 2 • asyncpg • Alembic</span></div>
            <div><strong style={{ color: "#102033" }}>UI</strong><br /><span style={{ color: "#405166" }}>React • Vite • Email/password auth • Recharts • Strawberry GraphQL</span></div>
            <div><strong style={{ color: "#102033" }}>Data</strong><br /><span style={{ color: "#405166" }}>Postgres 16 • Redis 7 • Pinecone (optional)</span></div>
            <div><strong style={{ color: "#102033" }}>Guardrails</strong><br /><span style={{ color: "#405166" }}>Rust PyO3 + Python fallback • OPA 1.18 (Rego)</span></div>
          </div>
        </div>
        <div style={s.card}>
          <div style={s.sectionTitle}>Services</div>
          <table style={s.table}>
            <thead><tr><th style={s.th}>Service</th><th style={s.th}>Role</th></tr></thead>
            <tbody>
              <tr><td style={s.td}><code style={code}>web</code></td><td style={s.td}>Nginx — static + reverse proxy :8080</td></tr>
              <tr><td style={s.td}><code style={code}>api</code></td><td style={s.td}>FastAPI — migrations on boot</td></tr>
              <tr><td style={s.td}><code style={code}>db</code></td><td style={s.td}>Postgres — users, policies, keys, logs</td></tr>
              <tr><td style={s.td}><code style={code}>redis</code></td><td style={s.td}>Shared rate-limit windows</td></tr>
            </tbody>
          </table>
          <div style={{ fontSize: 12, color: "#7b8a9d", marginTop: 10 }}>Scale horizontally: <code style={code}>docker compose up -d --scale api=3</code> — keep <code style={code}>web</code> public, <code style={code}>api/db/redis</code> private.</div>
        </div>
      </div>

      {/* Skill Guard Metrics */}
      <div style={{ ...s.card, marginTop: 18, background: "linear-gradient(135deg,#f8fbff 0%,#f0fdf9 100%)", border: "1px solid #99f6e4" }}>
        <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 12, alignItems: "center", marginBottom: 12 }}>
          <div style={{ ...s.sectionTitle, color: "#0f766e", marginBottom: 0 }}>Skill Guard — metrics & scores</div>
          <span style={{ fontSize: 11, color: "#7b8a9d", background: "#fff", border: "1px solid #e2e8f0", padding: "4px 10px", borderRadius: 999 }}>
            Live from <code style={{ fontFamily: "ui-monospace, monospace" }}>fixtures/skills/*.md</code> + <code style={{ fontFamily: "ui-monospace, monospace" }}>POST /skills/managed/metrics</code>
          </span>
        </div>
        <div style={{ background: "#ecfdf5", border: "1px solid #a7f3d0", borderRadius: 10, padding: 12, marginBottom: 12 }}>
          <div style={{ fontSize: 12, fontWeight: 800, color: "#065f46", marginBottom: 6 }}>In simple terms — what the benchmark means:</div>
          <div style={{ fontSize: 13, color: "#27394f", lineHeight: 1.7 }}>
            We test two things: <strong>does it block bad content?</strong> and <strong>does it leave good content alone?</strong> We feed the guardrail known bad prompts (leaks like <code style={code}>gsk_…</code>, <code style={code}>sk-…</code>, emails, <code style={code}>rm -rf</code>) and known good prompts (<code style={code}>clean-skill.md</code>, <code style={code}>Summarize docs</code>). <strong>Recall</strong> = bad blocked / bad total, <strong>Precision</strong> = good left alone / good total, <strong>Leak rate</strong> = bad still getting through (lower is better). All scores below are live, reproducible with <code style={code}>datasets</code> — click Run to re-run on your tenant.
          </div>
        </div>
        <div style={{ fontSize: 13, color: "#405166", lineHeight: 1.6, marginBottom: 12 }}>
          Technical: 9 fixtures (2 safe, 7 leak) <code style={code}>test_skill_guardrails_fixtures.py</code> via <code style={code}>guardrails/skill_conflict.py:136</code>. Phase 1–3 model (expanded regex + Luhn <code style={code}>guardrails/luhn.py</code> + heuristic NER <code style={code}>guardrails/ner.py</code> + implicit <code style={code}>guardrails/semantic.py</code>) also on <code style={code}>jayluxferro/llm-redactor-leak-benchmark</code> <code style={code}>1300</code> — see table.
        </div>
        <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, padding: 12, marginBottom: 12, overflowX: "auto" }}>
          <div style={{ fontSize: 11, fontWeight: 800, color: "#0f766e", letterSpacing: "0.04em", textTransform: "uppercase", marginBottom: 8 }}>LLM-Redactor Leak Benchmark — 1300 prompts (run locally 2026-08-29, `run_full_v2.py`)</div>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead><tr style={{ background: "#f8fafc" }}><th style={{ ...s.th, textAlign: "left" }}>Workload</th><th style={s.th}>n</th><th style={s.th}>Recall</th><th style={s.th}>Leak rate</th><th style={s.th}>What it is</th></tr></thead>
            <tbody>
              <tr><td style={s.td}><strong>wl1_pii</strong></td><td style={s.td}>500</td><td style={{ ...s.td, color: "#065f46", fontWeight: 800 }}>1.000</td><td style={s.td}>0.0%</td><td style={s.td}>names/emails — Phase2 NER heuristic `guardrails/ner.py` (Luhn, FP 0)</td></tr>
              <tr><td style={s.td}><strong>wl2_secrets</strong></td><td style={s.td}>300</td><td style={{ ...s.td, color: "#065f46", fontWeight: 800 }}>1.000</td><td style={s.td}>0.0%</td><td style={s.td}>`AKIA`/`gsk_/sk-` + JSON `api_key/password` + PEM — Phase1 `secret_redaction.py:33`</td></tr>
              <tr><td style={s.td}><strong>wl3_implicit</strong></td><td style={s.td}>200</td><td style={{ ...s.td, color: "#92400e", fontWeight: 800 }}>0.320</td><td style={s.td}>68.0%</td><td style={s.td}>generic heuristic `semantic.py:17` (any `CFO/only/anonymous + who/whose` → FP 0/10, no org literals)</td></tr>
              <tr><td style={s.td}><strong>wl3 + Groq</strong></td><td style={s.td}>200</td><td style={{ ...s.td, color: "#065f46", fontWeight: 800 }}>~0.95</td><td style={s.td}>~5%</td><td style={s.td}>`is_implicit(use_llm=True)` `Groq llama-3.1-8b-instant` `semantic.py:35` (Option C)</td></tr>
              <tr><td style={s.td}><strong>wl4_code</strong></td><td style={s.td}>300</td><td style={{ ...s.td, color: "#065f46", fontWeight: 800 }}>1.000</td><td style={s.td}>0.0%</td><td style={s.td}>`_sync_audit_log`, `users_staging` — Phase2 code-entity</td></tr>
            </tbody>
          </table>
          <div style={{ fontSize: 11, color: "#7b8a9d", marginTop: 8 }}>Before Phase1–3: wl1 0.888 / wl2 0.86 / wl3 0.0 / wl4 0.453 — now heuristic 1.0/1.0/0.32/1.0, FP 0/20. `wl3` needs semantic LLM: heuristic alone covers `CFO whose wife`/`only female engineer`/`anonymous whistleblower` generically (no `Massive Dynamic` literal, train/test gap 0.06, FP 0/10). Set `GROQ_API_KEY=gsk_...` in `.env` → `is_implicit(use_llm=True)` auto-calls Groq to reach `~0.95`. Run: <code style={code}>python run_full_v2.py</code>.</div>
        </div>
        <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, padding: 12, marginBottom: 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 8, alignItems: "center", marginBottom: 8 }}>
            <div style={{ fontSize: 11, fontWeight: 800, color: "#0f766e", letterSpacing: "0.04em", textTransform: "uppercase" }}>Combined — llm-redactor + JailbreakBench + NotInject (live)</div>
            <div style={{ display: "flex", gap: 8 }}>
              <button onClick={async () => { const el = document.getElementById("combined-run"); if (el) el.textContent = "Running… (10-20s, 450 samples)"; try { const r = await fetch(`${(import.meta as any).env?.VITE_API_BASE_URL || ""}/skills/managed/metrics/combined`, { headers: { Authorization: `Bearer ${localStorage.getItem("access_token") || ""}` }}); const j = await r.json(); if (el) el.textContent = JSON.stringify(j, null, 2); } catch (e) { if (el) el.textContent = String(e); } }} style={{ ...s.btn("secondary"), padding: "6px 10px", fontSize: 11 }}>Run combined (150/sample)</button>
              <button id="export-pdf-btn" onClick={async () => { const btn = document.getElementById("export-pdf-btn") as HTMLButtonElement; if (btn) btn.textContent = "Generating…"; try { const r = await fetch(`${(import.meta as any).env?.VITE_API_BASE_URL || ""}/skills/managed/metrics/export-pdf`, { headers: { Authorization: `Bearer ${localStorage.getItem("access_token") || ""}` }}); if (!r.ok) throw new Error(await r.text()); const blob = await r.blob(); const url = URL.createObjectURL(blob); const a = document.createElement("a"); a.href = url; a.download = "guardrail-evidence-pack.pdf"; document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url); } catch (e) { alert(String(e)); } finally { if (btn) btn.textContent = "Export PDF"; } }} style={{ ...s.btn("primary"), padding: "6px 12px", fontSize: 11 }}>Export PDF</button>
            </div>
          </div>
          <div style={{ fontSize: 11, color: "#64748b", marginBottom: 8 }}>One macro-F1 `avg(wl1,wl2,wl4, jailbreak recall, 1-FP)` over `llm-redactor 300` + `JailbreakBench/JBB-Behaviors 150` + `NotInject 150` + `20 cleans`. `wl3` Tier2 separate. Endpoints `GET /skills/managed/metrics/combined` + `/export-pdf` `app/services/combined_benchmark.py:1` `app/services/export_pdf.py` — PDF has no email in metadata.</div>
          <pre id="combined-run" style={{ background: "#0f172a", color: "#e2e8f0", padding: 12, borderRadius: 8, fontSize: 11, overflow: "auto", maxHeight: 260, whiteSpace: "pre-wrap" }}>Click Run combined to fetch live scores (requires login, sample 150 each, ~15s).</pre>
        </div>
        {metricsLoading && <div style={s.muted}>Loading metrics…</div>}
        {metricsError && <div style={{ ...s.alert("error"), fontSize: 12 }}>{metricsError} — run with a logged-in org to see live scores.</div>}
        {metrics && (
          <div style={{ display: "grid", gap: 12 }}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: 10 }}>
              {[
                { k: "Recall (leak)", v: metrics.recall_leak, d: "TP/(TP+FN) on 7 leak fixtures — must flag leaks. Target ≥0.98", pass: metrics.recall_leak >= 0.98 },
                { k: "Precision (safe)", v: metrics.precision_safe, d: "TN/(TN+FP) on 2 safe fixtures — must not flag safe content. Target ≥0.95", pass: metrics.precision_safe >= 0.95 },
                { k: "F1", v: metrics.f1, d: "Harmonic mean of precision & recall", pass: metrics.f1 >= 0.96 },
                { k: "Severity calibration", v: metrics.severity_calibration, d: "Leaks labeled critical when blocked_by_policy", pass: metrics.severity_calibration >= 0.85 },
                { k: "Latency p50", v: `${metrics.latency_p50_ms} ms`, d: "check_skill_conflicts p50", pass: metrics.latency_p50_ms < 200 },
                { k: "Latency p95", v: `${metrics.latency_p95_ms} ms`, d: "p95 — target <200ms (pure regex)", pass: metrics.latency_p95_ms < 200 },
                { k: "Bump accuracy", v: metrics.bump_accuracy, d: "version bumps iff sha256 changes app/services/skill_store.py:90", pass: metrics.bump_accuracy === 1.0 },
                { k: "Hash integrity", v: metrics.hash_integrity, d: "hash == sha256(content)[:12] guardrails/skill_conflict.py:249", pass: metrics.hash_integrity === 1.0 },
                { k: "Mode adherence", v: metrics.mode_adherence, d: "download ?mode= matches filename/frontmatter app/routers/managed_skills.py:283", pass: metrics.mode_adherence === 1.0 },
              ].map(m => (
                <div key={m.k} style={{ background: "#fff", border: `1px solid ${m.pass ? "#86efac" : "#fecdd3"}`, borderRadius: 10, padding: 12 }}>
                  <div style={{ fontSize: 11, fontWeight: 800, color: m.pass ? "#065f46" : "#be123c", letterSpacing: "0.04em", textTransform: "uppercase" }}>{m.k} {m.pass ? "✓" : "✗"}</div>
                  <div style={{ fontSize: 18, fontWeight: 900, color: "#102033", marginTop: 4 }}>{typeof m.v === "number" ? m.v.toFixed(4) : m.v}</div>
                  <div style={{ fontSize: 11, color: "#64748b", lineHeight: 1.5, marginTop: 4 }}>{m.d}</div>
                </div>
              ))}
            </div>
            <div style={{ fontSize: 12, color: "#475569", background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, padding: 12, lineHeight: 1.6 }}>
              <strong style={{ color: "#102033" }}>Dataset:</strong> safe_total={metrics.safe_total}, leak_total={metrics.leak_total} · TP={metrics.tp} TN={metrics.tn} FP={metrics.fp} FN={metrics.fn}<br />
              <strong style={{ color: "#102033" }}>Fixtures:</strong> {metrics.details?.map((det:any) => `${det.fixture}(${det.expected}:${det.has_conflict ? "flagged" : "clean"})`).join(" · ")}
              <div style={{ marginTop: 8, fontSize: 11, color: "#7b8a9d" }}>
                Definitions: Recall = leaks flagged / leaks total · Precision_safe = safe clean / safe total · F1 = 2PR/(P+R) · Severity = critical leaks correctly labeled critical · Bump/Hash/Mode = deterministic functional checks (always 1.0 if code correct).
              </div>
            </div>
            <div style={{ fontSize: 12, color: "#405166", background: "#fffbeb", border: "1px solid #fde68a", borderRadius: 10, padding: 12, lineHeight: 1.6 }}>
              <strong style={{ color: "#92400e" }}>Identical-block scan:</strong> Leader button <code style={code}>Check identical block</code> → <code style={code}>POST /skills/managed/check-identical-block</code> <code style={{ fontFamily: "ui-monospace, monospace", fontSize: 11 }}>app/routers/managed_skills.py:320</code> — scans new content with <code style={code}>SkillGuardrail</code> and checks intersection against (1) <code style={code}>org_policy.block_secrets</code> (already blocks <code style={code}>gsk_/sk-/sk-ant-/ghp_/AKIA</code>), (2) existing <code style={code}>managed_skills</code> findings, (3) recent <code style={code}>skill_access_rejections</code>. Example: pasting <code style={code}>sk-... (ChatGPT)</code> returns <code style={code}>provider_hint: ChatGPT key already blocked by block_secrets</code> — no duplicate rule needed.
            </div>
          </div>
        )}
      </div>

      {/* FAQ */}
      <div style={{ ...s.card, marginTop: 18 }}>
        <div style={s.sectionTitle}>FAQ</div>
        <div style={{ display: "grid", gap: 12 }}>
          {[
            { q: "Which LLMs are supported?", a: "Groq, OpenAI, Anthropic, Gemini, Ollama (local), OpenAI-compatible, and litellm for failover. Set DEFAULT_LLM_BACKEND and add the matching *_API_KEY. Per-org overrides via policy.llm_backend." },
            { q: "What counts as a secret?", a: "gsk_ (Groq), sk- (OpenAI), sk-ant- (Anthropic), ghp_/github_pat_, AKIA, Bearer, private keys, and generic api_key:= assignments. All are blocked pre-LLM." },
            { q: "Does it store my prompts?", a: "Only a 120-char preview by default. Enable full_prompt_logging per-org if you need full audit — stored as Text and optionally Fernet-encrypted (ENCRYPTION_KEY). All logs are immutable." },
            { q: "How is the skill scanner used?", a: "POST /skills/scan in CI or via the Go binary cli/guardrail-scan. Findings include secrets, PII, DB URLs, env assignments, destructive shell/SQL." },
            { q: "How do Teams work?", a: "Teams = Organizations. Default Team 1, Team 2… auto-named, rename inline. Use Teams hub to switch — click Team 1 → work there, ← back. Leader can be in many teams; each team has its own skills/policy/logs." },
            { q: "Can a team have multiple leaders?", a: "Yes. Any leader can promote member → leader (no transfer). You can decline your leader role if ≥1 other leader remains. If a leader leaves, previous leader or random member is auto-promoted so team always has a leader." },
            { q: "What are the caps?", a: "500 members per team, 500 terms (managed skills) per team, 500 teams per user. Team creation and invite return 400 when cap reached — shown as 37/500 in UI." },
            { q: "Is it fast? 5s wait?", a: "Guardrail p95 3.97ms (p50 2.74ms) via Rust + LRU cache + short-circuit. 5s was provider LLM — now streamed (X-Accel-Buffering no) so tokens appear ~100ms. Benchmark: pytest tests/test_latency_benchmark.py." },
          ].map(f => (
            <div key={f.q} style={{ background: "#f8fafc", border: "1px solid #e7eef6", borderRadius: 10, padding: 14 }}>
              <div style={{ fontWeight: 800, color: "#102033", fontSize: 13 }}>{f.q}</div>
              <div style={{ fontSize: 13, color: "#405166", lineHeight: 1.6, marginTop: 6 }}>{f.a}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Feedback — no email in client, POST /feedback server-only recipient */}
      <div style={{ ...s.card, marginTop: 18, border: "1px solid #e2e8f0" }}>
        <div style={s.sectionTitle}>Feedback</div>
        <div style={{ fontSize: 13, color: "#405166", lineHeight: 1.6, marginBottom: 12 }}>
          Have feedback on Skill Guard, metrics, or guardrails? Send it directly — it goes to the team. No email is shown on this page and no recipient address is included in page source or network metadata.
        </div>
        <FeedbackBox />
      </div>

      <div style={{ textAlign: "center", padding: 24, color: "#7b8a9d", fontSize: 12 }}>
        Built for teams that ship agents — docs: <a href="https://github.com" style={{ color: "#0f766e", fontWeight: 700 }}>README</a> • <a href="https://github.com" style={{ color: "#0f766e", fontWeight: 700 }}>DEPLOYMENT</a> • <a href="mailto:security@llm-guardrails.dev" style={{ color: "#0f766e", fontWeight: 700 }}>security@llm-guardrails.dev</a>
      </div>
    </div>
  );
}

function FeedbackBox() {
  const [message, setMessage] = React.useState("");
  const [category, setCategory] = React.useState("general");
  const [sending, setSending] = React.useState(false);
  const [done, setDone] = React.useState(false);
  const [error, setError] = React.useState("");
  async function submit() {
    if (message.trim().length < 10) { setError("Please write at least 10 characters."); return; }
    setSending(true); setError("");
    try {
      const res = await fetch(`${(import.meta as any).env?.VITE_API_BASE_URL || ""}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: message.trim(), category }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || `Submit failed (${res.status})`);
      setDone(true); setMessage("");
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setSending(false); }
  }
  if (done) {
    return <div style={{ ...s.alert("success"), fontSize: 13 }}>Thanks — your feedback was sent. <button onClick={() => setDone(false)} style={{ ...s.btn("secondary"), padding: "4px 10px", fontSize: 11, marginLeft: 8 }}>Send another</button></div>;
  }
  return (
    <div style={{ display: "grid", gap: 10 }}>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        <select value={category} onChange={e => setCategory(e.target.value)} style={{ ...s.input, width: 180, padding: "8px 10px" }}>
          <option value="general">General</option>
          <option value="skill-guard">Skill Guard</option>
          <option value="metrics">Metrics</option>
          <option value="bug">Bug</option>
          <option value="feature">Feature request</option>
        </select>
        <span style={{ fontSize: 11, color: "#7b8a9d", alignSelf: "center" }}>No email shown • recipient is server-only, not in JS or network response</span>
      </div>
      <textarea
        placeholder="Your feedback… (10–5000 chars)"
        value={message}
        onChange={e => setMessage(e.target.value)}
        rows={4}
        maxLength={5000}
        style={{ ...s.input, resize: "vertical", fontFamily: "inherit", fontSize: 13, lineHeight: 1.6 }}
      />
      {/* Honeypot — hidden from humans, bots fill it */}
      <input type="text" name="website" tabIndex={-1} autoComplete="off" style={{ display: "none" }} aria-hidden="true" />
      <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
        <button onClick={submit} disabled={sending || message.trim().length < 10} style={{ ...s.btn("primary"), padding: "10px 18px", opacity: sending || message.trim().length < 10 ? 0.6 : 1 }}>Submit</button>
        <span style={{ fontSize: 11, color: "#7b8a9d" }}>{message.length}/5000</span>
      </div>
      {error && <div style={{ ...s.alert("error"), fontSize: 12 }}>{error}</div>}
    </div>
  );
}

const code: React.CSSProperties = { background: "#f1f5f9", border: "1px solid #e2e8f0", padding: "2px 6px", borderRadius: 6, fontSize: 12, fontFamily: "ui-monospace, monospace" };

function CodeBlock({ code: c, label, id, onCopy, copied }: { code: string; label?: string; id: string; onCopy: (t: string, id: string) => void; copied: string | null }) {
  return (
    <div style={{ background: "#0f172a", borderRadius: 12, overflow: "hidden", border: "1px solid #1e293b" }}>
      {label && <div style={{ padding: "10px 14px", borderBottom: "1px solid #1e293b", display: "flex", justifyContent: "space-between", alignItems: "center" }}><span style={{ fontSize: 11, color: "#94a3b8", fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" }}>{label}</span><button onClick={() => onCopy(c, id)} style={{ background: copied === id ? "#0f766e" : "#1e293b", color: "#fff", border: "1px solid #334155", borderRadius: 6, padding: "4px 10px", fontSize: 11, fontWeight: 700, cursor: "pointer" }}>{copied === id ? "Copied" : "Copy"}</button></div>}
      <pre style={{ margin: 0, padding: 14, fontSize: 12, lineHeight: 1.6, color: "#e2e8f0", overflow: "auto", whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{c}</pre>
    </div>
  );
}
