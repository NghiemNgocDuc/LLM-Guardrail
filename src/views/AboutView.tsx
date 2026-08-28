import React, { useState } from "react";
import { s } from "../styles/theme";

export default function AboutView() {
  const [activeTab, setActiveTab] = useState<"quickstart" | "api" | "skills">("quickstart");
  const [copied, setCopied] = useState<string | null>(null);
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
            <div><span style={{ color: "#fde68a" }}>FastAPI</span>  auth + rate limit + demo limit</div>
            <div style={{ color: "#475569" }}>                 |</div>
            <div><span style={{ color: "#fca5a5" }}>Input guardrails</span>  secrets <span style={{ color: "#64748b" }}>|</span> PII <span style={{ color: "#64748b" }}>|</span> injection <span style={{ color: "#64748b" }}>|</span> jailbreak <span style={{ color: "#64748b" }}>|</span> OPA/Rego</div>
            <div style={{ color: "#475569" }}>                 | pass</div>
            <div><span style={{ color: "#93c5fd" }}>Provider</span>  Groq / OpenAI / Anthropic / Ollama</div>
            <div style={{ color: "#475569" }}>                 |</div>
            <div><span style={{ color: "#fca5a5" }}>Output guardrails</span>  leakage <span style={{ color: "#64748b" }}>|</span> toxic <span style={{ color: "#64748b" }}>|</span> topic <span style={{ color: "#64748b" }}>|</span> schema</div>
            <div style={{ color: "#475569" }}>                 |</div>
            <div><span style={{ color: "#5eead4" }}>Audit</span>  Postgres + Redis • <span style={{ color: "#94a3b8" }}>X-Request-ID</span></div>
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
            { t: "Input guardrails", d: "Block secrets (gsk_/sk-), PII (email/SSN/CC), prompt injection, jailbreak, semantic near-duplicates. Rust regex, linear time.", bg: "#fffbeb" },
            { t: "Output guardrails", d: "Catch credential leakage, toxicity, blocked topics, and JSON schema violations before the user sees them.", bg: "#fff1f2" },
            { t: "Skill scanner", d: "POST /skills/scan for SKILL.md, system prompts, MCP rules. Flags env assignments, private IPs, destructive shell/SQL.", bg: "#f5f3ff" },
            { t: "Per-org policy", d: "Each org tunes its own JSON policy + optional Rego (OPA) as final gate. Diff, replay, and export for audit.", bg: "#eff6ff" },
            { t: "Audit + analytics", d: "Immutable request_logs, top blocked reasons, false-positive candidates, per-user token breakdown, GraphQL mirror.", bg: "#f0fdfa" },
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
            <div><strong style={{ color: "#102033" }}>UI</strong><br /><span style={{ color: "#405166" }}>React • Vite • Clerk • Recharts • Strawberry GraphQL</span></div>
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

      {/* FAQ */}
      <div style={{ ...s.card, marginTop: 18 }}>
        <div style={s.sectionTitle}>FAQ</div>
        <div style={{ display: "grid", gap: 12 }}>
          {[
            { q: "Which LLMs are supported?", a: "Groq, OpenAI, Anthropic, Gemini, Ollama (local), OpenAI-compatible, and litellm for failover. Set DEFAULT_LLM_BACKEND and add the matching *_API_KEY. Per-org overrides via policy.llm_backend." },
            { q: "What counts as a secret?", a: "gsk_ (Groq), sk- (OpenAI), sk-ant- (Anthropic), ghp_/github_pat_, AKIA, Bearer, private keys, and generic api_key:= assignments. All are blocked pre-LLM." },
            { q: "Does it store my prompts?", a: "Only a 120-char preview by default. Enable full_prompt_logging per-org if you need full audit — stored as Text and optionally Fernet-encrypted (ENCRYPTION_KEY). All logs are immutable." },
            { q: "How is the skill scanner used?", a: "POST /skills/scan in CI or via the Go binary cli/guardrail-scan. Findings include secrets, PII, DB URLs, env assignments, destructive shell/SQL." },
          ].map(f => (
            <div key={f.q} style={{ background: "#f8fafc", border: "1px solid #e7eef6", borderRadius: 10, padding: 14 }}>
              <div style={{ fontWeight: 800, color: "#102033", fontSize: 13 }}>{f.q}</div>
              <div style={{ fontSize: 13, color: "#405166", lineHeight: 1.6, marginTop: 6 }}>{f.a}</div>
            </div>
          ))}
        </div>
      </div>

      <div style={{ textAlign: "center", padding: 24, color: "#7b8a9d", fontSize: 12 }}>
        Built for teams that ship agents — docs: <a href="https://github.com" style={{ color: "#0f766e", fontWeight: 700 }}>README</a> • <a href="https://github.com" style={{ color: "#0f766e", fontWeight: 700 }}>DEPLOYMENT</a> • <a href="mailto:security@llm-guardrails.dev" style={{ color: "#0f766e", fontWeight: 700 }}>security@llm-guardrails.dev</a>
      </div>
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
