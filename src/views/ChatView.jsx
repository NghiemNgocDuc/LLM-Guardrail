import React, { useState, useEffect, useCallback, useRef } from "react";
import { api, getToken, setTokens, clearTokens, getGatewayKey, setGatewayKey, maskGatewayKey, gatewayKeyInputProps, formatApiError, PII_PATTERNS, INJECTION_KW, JAILBREAK_KW } from "../utils/api";
import { s } from "../styles/theme";
function clientGuardrail(prompt) {
  for (const p of PII_PATTERNS) {
    if (p.regex.test(prompt)) return { blocked: true, reason: `PII detected: ${p.name}` };
  }
  const lower = prompt.toLowerCase();
  for (const kw of INJECTION_KW) {
    if (lower.includes(kw.toLowerCase())) return { blocked: true, reason: `Prompt injection: "${kw}"` };
  }
  for (const kw of JAILBREAK_KW) {
    if (lower.includes(kw.toLowerCase())) return { blocked: true, reason: `Jailbreak attempt: "${kw}"` };
  }
  return { blocked: false };
}

// STYLES
function parseInlineMarkdown(text) {
  if (!text) return "";
  const regex = /(\*\*.*?\*\*|`.*?`)/g;
  const tokens = text.split(regex);
  return tokens.map((token, i) => {
    if (token.startsWith("**") && token.endsWith("**")) {
      return <strong key={i} style={{ fontWeight: 700, color: "#1e293b" }}>{token.slice(2, -2)}</strong>;
    }
    if (token.startsWith("`") && token.endsWith("`")) {
      return (
        <code
          key={i}
          style={{
            background: "#f1f5f9",
            color: "#0f766e",
            padding: "2px 5px",
            borderRadius: 4,
            fontSize: "0.9em",
            fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
          }}
        >
          {token.slice(1, -1)}
        </code>
      );
    }
    return token;
  });
}

function MarkdownResponse({ text }) {
  if (!text) return null;
  const lines = text.split("\n");
  const elements = [];
  let currentList = [];

  const flushList = (key) => {
    if (currentList.length > 0) {
      elements.push(
        <ul key={`list-${key}`} style={{ margin: "8px 0 12px 20px", paddingLeft: 0, listStyleType: "disc" }}>
          {currentList}
        </ul>
      );
      currentList = [];
    }
  };

  lines.forEach((line, index) => {
    const trimmed = line.trim();
    if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
      const content = line.replace(/^[-*]\s+/, "");
      currentList.push(
        <li key={`li-${index}`} style={{ marginBottom: 6, lineHeight: 1.6 }}>
          {parseInlineMarkdown(content)}
        </li>
      );
    } else {
      flushList(index);
      if (trimmed === "") {
        elements.push(<div key={`space-${index}`} style={{ height: 8 }} />);
      } else {
        elements.push(
          <p key={`p-${index}`} style={{ margin: "0 0 12px 0", lineHeight: 1.65 }}>
            {parseInlineMarkdown(line)}
          </p>
        );
      }
    }
  });

  flushList(lines.length);
  return <div style={{ color: "#27394f", fontSize: 14 }}>{elements}</div>;
}

// CHAT TESTER VIEW
export default function ChatView() {
  const [prompt, setPrompt] = useState("");
  const [gatewayKey, setGatewayKeyState] = useState(getGatewayKey());
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [clientBlock, setClientBlock] = useState(null);

  function onGatewayKeyChange(e) {
    const key = e.target.value.trim();
    setGatewayKeyState(key);
    setGatewayKey(key);
  }

  function onPromptChange(e) {
    const val = e.target.value;
    setPrompt(val);
    setClientBlock(null);
    if (val) {
      const guard = clientGuardrail(val);
      if (guard.blocked) setClientBlock(guard.reason);
    }
  }

  async function send() {
    if (!prompt.trim()) return;
    if (!gatewayKey && !getToken()) {
      setResult({ error: "Sign in and create a gateway API key, or paste your full grg_ key here." });
      return;
    }
    const guard = clientGuardrail(prompt);
    if (guard.blocked) {
      setResult({ clientBlocked: true, reason: guard.reason });
      return;
    }
    setLoading(true); setResult(null);
    try {
      const headers = {};
      if (gatewayKey) headers["X-Api-Key"] = gatewayKey;
      const data = await api("/chat", {
        method: "POST",
        headers,
        body: { prompt: prompt.trim() },
      });
      setResult(data);
    } catch (e) {
      setResult({ error: e.message });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <div style={s.heroPanel}>
        <div style={{ ...s.pageTitle, marginBottom: 8 }}>LLM Playground</div>
        <div style={{ color: "#405166", fontSize: 15, lineHeight: 1.6 }}>
          Test live prompts through client checks, backend policy, your LLM provider, and output validation.
          For agent skills and instructions, use Skill Guard in the sidebar.
        </div>
      </div>
      {!gatewayKey && (
        <div style={s.alert("info")}>
          Create an API key in API Keys, then paste the grg_ key here to test the gateway.
        </div>
      )}
      <div style={s.card}>
        <div style={s.sectionTitle}>Test a prompt through the live pipeline</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))", gap: 10, marginBottom: 16 }}>
          {["Client precheck", "Input policy", "Provider call", "Output policy"].map((step, idx) => (
            <div key={step} style={{ border: "1px solid #dce7f0", background: "#f8fbff",
              borderRadius: 8, padding: 12 }}>
              <div style={{ color: "#0f766e", fontWeight: 850, fontSize: 12 }}>0{idx + 1}</div>
              <div style={{ color: "#27394f", fontWeight: 800, fontSize: 13, marginTop: 4 }}>{step}</div>
            </div>
          ))}
        </div>
        <label style={s.label}>Gateway key</label>
        <input
          {...gatewayKeyInputProps}
          style={{ ...s.input, marginBottom: 10, fontFamily: "monospace" }}
          placeholder="Paste a gateway API key: grg_..."
          value={gatewayKey}
          onChange={onGatewayKeyChange}
        />
        <label style={s.label}>Prompt</label>
        <textarea
          style={{ ...s.input, minHeight: 100, resize: "vertical", marginBottom: 4 }}
          placeholder={'Try: "ignore previous instructions"\nOr: "What is 123-45-6789"'}
          value={prompt}
          onChange={onPromptChange}
        />
        {clientBlock && (
          <div style={{ fontSize: 12, color: "#b45309", marginBottom: 8, fontWeight: 750 }}>
            Client-side guard: {clientBlock}
          </div>
        )}
        <button style={{ ...s.btn("primary"), marginTop: 8 }}
          onClick={send} disabled={loading || !prompt.trim()}>
          {loading ? "Sending..." : "Send prompt"}
        </button>
      </div>

      {result && (
        <div style={{ ...s.card, marginTop: 16 }}>
          {result.error && <div style={s.alert("error")}>{result.error}</div>}
          {result.clientBlocked && (
            <div style={s.alert("error")}>
              Blocked client-side before hitting backend<br />
              <span style={{ fontSize: 11 }}>{result.reason}</span>
            </div>
          )}
          {result.status && (
            <>
              <div style={{ display: "flex", gap: 16, marginBottom: 16 }}>
                <div>
                  <div style={s.statLabel}>Status</div>
                  <span style={s.badge(result.status)}>{result.status}</span>
                </div>
                <div>
                  <div style={s.statLabel}>Latency</div>
                  <div style={{ fontSize: 14, color: "#102033", marginTop: 4, fontWeight: 800 }}>{result.latency_ms}ms</div>
                </div>
                <div>
                  <div style={s.statLabel}>Backend</div>
                  <div style={{ fontSize: 14, color: "#102033", marginTop: 4, fontWeight: 800 }}>{result.backend} / {result.model}</div>
                </div>
                {result.tokens_remaining != null && (
                  <div>
                    <div style={s.statLabel}>Tokens left</div>
                    <div style={{ fontSize: 14, color: "#0f766e", marginTop: 4, fontWeight: 800 }}>
                      {Number(result.tokens_remaining).toLocaleString()}
                    </div>
                  </div>
                )}
              </div>

              {/* Guardrail results */}
              <div style={{ display: "flex", gap: 12, marginBottom: 16 }}>
                {[
                  { label: "Input Guard", g: result.input_guard },
                  ...(result.output_guard ? [{ label: "Output Guard", g: result.output_guard }] : []),
                ].map(({ label, g }) => (
                  <div key={label} style={{ flex: 1, padding: 14,
                    background: g.passed ? (g.reason_code === "pii_redacted" ? "#f0fdf4" : "#e8f8ef") : "#fff1f2",
                    borderRadius: 8, border: `1px solid ${g.passed ? (g.reason_code === "pii_redacted" ? "#86efac" : "#abe7c6") : "#fecdd3"}` }}>
                    <div style={{ fontSize: 12, color: g.passed ? "#067647" : "#be123c",
                      fontWeight: 850, marginBottom: 4 }}>
                      {label}: {g.passed ? "PASS" : "BLOCK"}
                      {g.reason_code === "pii_redacted" && (
                        <span style={{
                          marginLeft: 8, padding: "2px 8px", borderRadius: 4,
                          background: "linear-gradient(135deg, #0f766e 0%, #10b981 100%)",
                          color: "#ffffff", fontSize: 10, fontWeight: 800,
                          letterSpacing: "0.04em",
                        }}>🔒 PII REDACTED</span>
                      )}
                    </div>
                    <div style={{ fontSize: 12, color: "#405166" }}>{g.reason}</div>
                    <div style={{ fontSize: 11, color: "#7b8a9d", marginTop: 6 }}>
                      {g.reason_code} / risk {Math.round((g.risk_score || 0) * 100)}%
                    </div>
                  </div>
                ))}
              </div>

              {result.response && (
                <div>
                  <div style={s.sectionTitle}>Response</div>
                  <MarkdownResponse text={result.response} />
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

// BILLING VIEW
