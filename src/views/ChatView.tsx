import React, { useState, useEffect, useRef } from "react";
import { api, getToken, getGatewayKey, setGatewayKey, gatewayKeyInputProps, PII_PATTERNS, INJECTION_KW, JAILBREAK_KW } from "../utils/api";
import { trackEvent } from "../utils/analytics";
import { s } from "../styles/theme";
import type { components, ChatFeedbackOut } from "../api-types";

type ChatResponse = components["schemas"]["ChatResponse"];
type GuardrailResult = components["schemas"]["GuardrailResult"];

interface ClientGuardResult { blocked: boolean; reason?: string }

type ChatResult =
  | ChatResponse
  | { error: string }
  | { clientBlocked: boolean; reason: string };

interface HistoryMessage {
  prompt: string;
  result: ChatResult;
  ts: number;
  feedback?: ChatFeedbackOut;
}

function clientGuardrail(prompt: string): ClientGuardResult {
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
function parseInlineMarkdown(text: string): React.ReactNode {
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

function MarkdownResponse({ text }: { text: string }) {
  if (!text) return null;
  const lines = text.split("\n");
  const elements: React.ReactNode[] = [];
  let currentList: React.ReactNode[] = [];

  const flushList = (key: number) => {
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

const HISTORY_KEY = "guardrails_chat_history";
const MAX_HISTORY = 50;

function loadHistory(): HistoryMessage[] {
  try { return JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]") as HistoryMessage[]; } catch { return []; }
}
function saveHistory(h: HistoryMessage[]) {
  try { localStorage.setItem(HISTORY_KEY, JSON.stringify(h.slice(-MAX_HISTORY))); } catch {}
}

function FeedbackButtons({ requestId, initial, onUpdate }: {
  requestId: string;
  initial?: ChatFeedbackOut;
  onUpdate: (r: ChatFeedbackOut) => void;
}) {
  const [rating, setRating] = useState(initial?.rating || 0);
  const [saving, setSaving] = useState(false);

  async function submit(r: number) {
    if (saving) return;
    setSaving(true);
    try {
      const res = await api<ChatFeedbackOut>(`/chat/${requestId}/feedback`, { method: "POST", body: { rating: r } });
      setRating(res.rating);
      onUpdate(res);
    } catch { setRating(0); }
    setSaving(false);
  }

  return (
    <>
      <span style={{ fontSize: 11, color: "#8a9bb0", marginRight: 4 }}>Rate this:</span>
      <button onClick={() => submit(1)} disabled={saving} style={{
        background: rating === 1 ? "#0f766e" : "transparent",
        border: `1px solid ${rating === 1 ? "#0f766e" : "#d0dce8"}`,
        borderRadius: 6, cursor: "pointer", fontSize: 14, padding: "3px 8px",
        color: rating === 1 ? "#fff" : "#607086", opacity: saving ? 0.5 : 1,
      }}>+1</button>
      <button onClick={() => submit(-1)} disabled={saving} style={{
        background: rating === -1 ? "#be123c" : "transparent",
        border: `1px solid ${rating === -1 ? "#be123c" : "#d0dce8"}`,
        borderRadius: 6, cursor: "pointer", fontSize: 14, padding: "3px 8px",
        color: rating === -1 ? "#fff" : "#607086", opacity: saving ? 0.5 : 1,
      }}>-1</button>
    </>
  );
}

// CHAT TESTER VIEW
export default function ChatView() {
  const [prompt, setPrompt] = useState("");
  const [gatewayKey, setGatewayKeyState] = useState(getGatewayKey());
  const [messages, setMessages] = useState<HistoryMessage[]>(loadHistory);
  const [loading, setLoading] = useState(false);
  const [clientBlock, setClientBlock] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function onGatewayKeyChange(e: React.ChangeEvent<HTMLInputElement>) {
    const key = e.target.value.trim();
    setGatewayKeyState(key);
    setGatewayKey(key);
  }

  function onPromptChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    const val = e.target.value;
    setPrompt(val);
    setClientBlock(null);
    if (val) {
      const guard = clientGuardrail(val);
      if (guard.blocked) setClientBlock(guard.reason || null);
    }
  }

  function clearHistory() {
    if (!confirm("Clear all conversation history?")) return;
    localStorage.removeItem(HISTORY_KEY);
    setMessages([]);
  }

  async function send() {
    if (!prompt.trim()) return;
    if (!gatewayKey && !getToken()) {
      const msg: HistoryMessage = { prompt: prompt.trim(), result: { error: "Sign in and create a gateway API key, or paste your full grg_ key here." }, ts: Date.now() };
      const next = [...messages, msg];
      setMessages(next); saveHistory(next);
      setPrompt("");
      return;
    }
    const guard = clientGuardrail(prompt);
    if (guard.blocked) {
      const msg: HistoryMessage = { prompt: prompt.trim(), result: { clientBlocked: true, reason: guard.reason || "" }, ts: Date.now() };
      const next = [...messages, msg];
      setMessages(next); saveHistory(next);
      setPrompt("");
      return;
    }
    const userPrompt = prompt.trim();
    setLoading(true); setPrompt("");
    try {
      const headers: Record<string, string> = {};
      if (gatewayKey) headers["X-Api-Key"] = gatewayKey;
      const data = await api<ChatResponse>("/chat", { method: "POST", headers, body: { prompt: userPrompt } });
      trackEvent("chat_sent", { status: data.status, backend: data.backend, model: data.model, latency_ms: data.latency_ms });
      const msg: HistoryMessage = { prompt: userPrompt, result: data, ts: Date.now() };
      const next = [...messages, msg];
      setMessages(next); saveHistory(next);
    } catch (e) {
      trackEvent("chat_failed", { error: e instanceof Error ? e.message : String(e) });
      const msg: HistoryMessage = { prompt: userPrompt, result: { error: e instanceof Error ? e.message : String(e) }, ts: Date.now() };
      const next = [...messages, msg];
      setMessages(next); saveHistory(next);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <div style={s.heroPanel}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 12 }}>
          <div>
            <div style={{ ...s.pageTitle, marginBottom: 8 }}>LLM Playground</div>
            <div style={{ color: "#405166", fontSize: 15, lineHeight: 1.6 }}>
              Test live prompts through client checks, backend policy, your LLM provider, and output validation.
            </div>
          </div>
          {messages.length > 0 && (
            <button style={{ ...s.btn("danger"), fontSize: 12 }} onClick={clearHistory}>Clear history</button>
          )}
        </div>
      </div>

      {!gatewayKey && (
        <div style={s.alert("info")}>
          Create an API key in API Keys, then paste the grg_ key here to test the gateway.
        </div>
      )}

      {/* Conversation thread */}
      {messages.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16, marginBottom: 16 }}>
          {messages.map((msg, i) => (
            <div key={i}>
              {/* User bubble */}
              <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 6 }}>
                <div style={{
                  maxWidth: "72%", background: "linear-gradient(135deg, #0f766e, #047857)",
                  color: "#fff", borderRadius: "16px 16px 4px 16px",
                  padding: "12px 16px", fontSize: 14, lineHeight: 1.5,
                  boxShadow: "0 4px 12px rgba(15,118,110,0.2)",
                }}>
                  {msg.prompt}
                  <div style={{ fontSize: 10, opacity: 0.6, marginTop: 4, textAlign: "right" }}>
                    {new Date(msg.ts).toLocaleTimeString()}
                  </div>
                </div>
              </div>
              {/* Result bubble */}
              <div style={{ display: "flex", justifyContent: "flex-start" }}>
                <div style={{
                  maxWidth: "80%", background: "#fff", border: "1px solid #e7eef6",
                  borderRadius: "4px 16px 16px 16px", padding: "12px 16px",
                  boxShadow: "0 2px 8px rgba(15,118,110,0.06)",
                }}>
                  {"error" in msg.result && msg.result.error && <div style={{ color: "#be123c", fontSize: 13 }}>{msg.result.error}</div>}
                  {"clientBlocked" in msg.result && (
                    <div style={{ color: "#b45309", fontSize: 13 }}>
                      Blocked client-side: {msg.result.reason}
                    </div>
                  )}
                  {"status" in msg.result && msg.result.status && (
                    <>
                      <div style={{ display: "flex", gap: 12, marginBottom: 10, flexWrap: "wrap" }}>
                        <span style={s.badge(msg.result.status)}>{msg.result.status}</span>
                        <span style={{ fontSize: 12, color: "#7b8a9d" }}>{msg.result.latency_ms}ms</span>
                        <span style={{ fontSize: 12, color: "#7b8a9d" }}>{msg.result.backend}/{msg.result.model}</span>
                        {msg.result.tokens_remaining != null && (
                          <span style={{ fontSize: 12, color: "#0f766e", fontWeight: 700 }}>
                            {Number(msg.result.tokens_remaining).toLocaleString()} tokens left
                          </span>
                        )}
                      </div>
                      <div style={{ display: "flex", gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
                        {[
                          { label: "In", g: msg.result.input_guard },
                          ...(msg.result.output_guard ? [{ label: "Out", g: msg.result.output_guard }] : []),
                        ].map(({ label, g }: { label: string; g: GuardrailResult }) => (
                          <div key={label} style={{
                            padding: "5px 10px", borderRadius: 6, fontSize: 11,
                            background: g.passed ? "#e8f8ef" : "#fff1f2",
                            border: `1px solid ${g.passed ? "#abe7c6" : "#fecdd3"}`,
                            color: g.passed ? "#067647" : "#be123c", fontWeight: 750,
                          }}>
                            {label}: {g.passed ? "PASS" : "BLOCK"}
                            {g.reason_code === "pii_redacted" && (
                              <span style={{ marginLeft: 6, background: "#0f766e", color: "#fff",
                                padding: "1px 6px", borderRadius: 3, fontSize: 10 }}>PII REDACTED</span>
                            )}
                            {!g.passed && <span style={{ marginLeft: 4, opacity: 0.75 }}>· {g.reason_code}</span>}
                          </div>
                        ))}
                      </div>
                      {msg.result.response && <MarkdownResponse text={msg.result.response} />}
                      {msg.result.status === "delivered" && (
                        <div style={{ display: "flex", gap: 8, marginTop: 10, alignItems: "center" }}>
                          <FeedbackButtons requestId={msg.result.request_id} initial={msg.feedback} onUpdate={(r) => { msg.feedback = r; setMessages([...messages]); }} />
                        </div>
                      )}
                    </>
                  )}
                </div>
              </div>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
      )}

      {/* Input area */}
      <div style={s.card}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(130px,1fr))", gap: 8, marginBottom: 14 }}>
          {["Client precheck", "Input policy", "Provider call", "Output policy"].map((step, idx) => (
            <div key={step} style={{ border: "1px solid #dce7f0", background: "#f8fbff", borderRadius: 8, padding: "10px 12px" }}>
              <div style={{ color: "#0f766e", fontWeight: 850, fontSize: 11 }}>0{idx + 1}</div>
              <div style={{ color: "#27394f", fontWeight: 800, fontSize: 12, marginTop: 3 }}>{step}</div>
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
          style={{ ...s.input, minHeight: 80, resize: "vertical", marginBottom: 4 }}
          placeholder={'Try: "ignore previous instructions"\nOr: "What is 2+2?"'}
          value={prompt}
          onChange={onPromptChange}
          onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) send(); }}
        />
        {clientBlock && (
          <div style={{ fontSize: 12, color: "#b45309", marginBottom: 8, fontWeight: 750 }}>
            Client-side guard: {clientBlock}
          </div>
        )}
        <button style={{ ...s.btn("primary"), marginTop: 8 }}
          onClick={send} disabled={loading || !prompt.trim()}>
          {loading ? "Sending..." : "Send  (Ctrl+Enter)"}
        </button>
      </div>
    </div>
  );
}

// BILLING VIEW
