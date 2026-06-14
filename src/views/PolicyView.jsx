import React, { useState, useEffect, useCallback, useRef } from "react";
import { api, getToken, setTokens, clearTokens, getGatewayKey, setGatewayKey, maskGatewayKey, gatewayKeyInputProps, formatApiError } from "../utils/api";
import { s } from "../styles/theme";
export default function PolicyView({ user }) {
  const [policy, setPolicy] = useState(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [saving, setSaving] = useState(false);
  const [newTopic, setNewTopic] = useState("");

  useEffect(() => {
    api("/policy").then(setPolicy).catch((e) => setError(e.message));
  }, []);

  async function save() {
    if (!user.is_admin) return;
    setSaving(true); setError(""); setSuccess("");
    try {
      const updated = await api("/policy", { method: "PATCH", body: policy });
      setPolicy(updated);
      setSuccess("Policy saved.");
    } catch (e) { setError(e.message); }
    finally { setSaving(false); }
  }

  async function reset() {
    if (!confirm("Reset to defaults?")) return;
    try {
      const updated = await api("/policy/reset", { method: "POST" });
      setPolicy(updated);
      setSuccess("Policy reset to defaults.");
    } catch (e) { setError(e.message); }
  }

  if (error && !policy) return <div style={s.alert("error")}>{error}</div>;
  if (!policy) return <div style={s.muted}>Loading policy...</div>;

  const toggleRule = (section, key) => {
    setPolicy(p => ({
      ...p,
      [section]: { ...p[section], [key]: !p[section][key] },
    }));
  };

  const toggleTopic = (topic) => {
    const blocked = policy.topic_policy?.blocked_topics || [];
    const next = blocked.includes(topic)
      ? blocked.filter(t => t !== topic)
      : [...blocked, topic];
    setPolicy(p => ({ ...p, topic_policy: { ...p.topic_policy, blocked_topics: next } }));
  };

  const addTopic = () => {
    if (!newTopic.trim()) return;
    toggleTopic(newTopic.trim());
    setNewTopic("");
  };

  const blockedTopics = policy.topic_policy?.blocked_topics || [];
  const allTopics = [
    "competitor products", "medical advice", "legal advice",
    "financial advice", "politics", "adult content", "violence",
    ...blockedTopics.filter(t => !["competitor products","medical advice","legal advice",
      "financial advice","politics","adult content","violence"].includes(t)),
  ];

  const Rule = ({ label, section, k }) => (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
      padding: "12px 0", borderBottom: "1px solid #e7eef6" }}>
      <span style={{ fontSize: 13, color: "#405166", fontWeight: 700 }}>{label}</span>
      <button style={s.toggle(policy[section]?.[k])}
        onClick={() => user.is_admin && toggleRule(section, k)}>
        <div style={s.toggleDot(policy[section]?.[k])} />
      </button>
    </div>
  );

  return (
    <div>
      <div style={s.heroPanel}>
        <div style={{ ...s.pageTitle, marginBottom: 8 }}>Policy Editor</div>
        <div style={{ color: "#405166", fontSize: 15, lineHeight: 1.6 }}>
          Tune the organization rules that run before and after provider responses.
        </div>
      </div>
      {!user.is_admin && <div style={s.alert("info")}>View only. Admin access is required to edit.</div>}
      {error && <div style={s.alert("error")}>{error}</div>}
      {success && <div style={s.alert("success")}>{success}</div>}

      <div style={s.grid2}>
        <div style={s.card}>
          <div style={s.sectionTitle}>Input Guardrails</div>
          <Rule label="Block prompt injection" section="input_rules" k="block_prompt_injection" />
          <Rule label="Block jailbreak attempts" section="input_rules" k="block_jailbreak" />

          <div style={{ ...s.sectionTitle, marginTop: 18, fontSize: 12 }}>PII Protection Mode</div>
          <div style={{ fontSize: 12, color: "#7b8a9d", marginBottom: 10, lineHeight: 1.5 }}>
            Choose how PII (emails, SSNs, credit cards, phone numbers) is handled before reaching the LLM.
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
            {[
              { value: "block", label: "Block", desc: "Reject requests containing PII" },
              { value: "redact", label: "Redact", desc: "Replace PII with placeholders" },
              { value: "off", label: "Off", desc: "No PII scanning" },
            ].map(opt => {
              const active = (policy.input_rules?.pii_redaction_mode || "block") === opt.value;
              return (
                <div key={opt.value}
                  onClick={() => {
                    if (!user.is_admin) return;
                    setPolicy(p => ({
                      ...p,
                      input_rules: {
                        ...p.input_rules,
                        pii_redaction_mode: opt.value,
                        block_pii: opt.value === "block",
                      },
                    }));
                  }}
                  style={{
                    flex: 1,
                    minWidth: 100,
                    padding: "12px 14px",
                    borderRadius: 10,
                    border: active ? "2px solid #0f766e" : "2px solid #e7eef6",
                    background: active ? "#ecfdf5" : "#ffffff",
                    cursor: user.is_admin ? "pointer" : "default",
                    transition: "all 0.2s",
                  }}
                >
                  <div style={{ fontSize: 13, fontWeight: 800, color: active ? "#0f766e" : "#405166" }}>{opt.label}</div>
                  <div style={{ fontSize: 11, color: "#7b8a9d", marginTop: 4 }}>{opt.desc}</div>
                </div>
              );
            })}
          </div>

          {(policy.input_rules?.pii_redaction_mode === "redact") && (
            <div style={{
              padding: "12px 14px", borderRadius: 8,
              background: "linear-gradient(135deg, #f0fdf4 0%, #ecfdf5 100%)",
              border: "1px solid #99f6e4", fontSize: 12, lineHeight: 1.6, color: "#065f46",
            }}>
              <strong>Redaction active.</strong> Emails, SSNs, credit cards, phone numbers, and IP addresses 
              will be replaced with placeholders like <code>[EMAIL_REDACTED_1]</code> before the prompt reaches the LLM.
            </div>
          )}
        </div>
        <div style={s.card}>
          <div style={s.sectionTitle}>Output Guardrails</div>
          <Rule label="Block toxic content" section="output_rules" k="block_toxic_content" />
          <Rule label="Enforce schema validation" section="output_rules" k="enforce_schema" />
          <div style={{ ...s.sectionTitle, marginTop: 16 }}>Compliance</div>
          <Rule label="Block medical advice" section="compliance_rules" k="block_medical_advice" />
          <Rule label="Never discuss competitors" section="compliance_rules" k="never_discuss_competitors" />
          <div style={{ marginTop: 16, paddingTop: 16, borderTop: "1px solid #e7eef6" }}>
            <Rule label="Enable Full Prompt Logging" section="compliance_rules" k="full_prompt_logging" />
            {(policy.compliance_rules?.full_prompt_logging) && (
              <div style={{ marginTop: 8, padding: "8px 12px", borderRadius: 6, background: "#fffbeb", border: "1px solid #fde68a", fontSize: 11, color: "#92400e", lineHeight: 1.5 }}>
                <strong>Warning:</strong> Full prompts will be stored in the database. This bypasses the default 120-character preview truncation and may store sensitive user data depending on your PII redaction settings.
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Blocked topics */}
      <div style={{ ...s.card, marginBottom: 16 }}>
        <div style={s.sectionTitle}>Blocked Topics</div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 16 }}>
          {allTopics.map(t => (
            <div key={t} style={s.chip(blockedTopics.includes(t))}
              onClick={() => user.is_admin && toggleTopic(t)}>
              {t}
            </div>
          ))}
        </div>
        {user.is_admin && (
          <div style={{ display: "flex", gap: 8 }}>
            <input style={{ ...s.input, flex: 1 }} placeholder="Add custom topic..."
              value={newTopic} onChange={(e) => setNewTopic(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addTopic()} />
            <button style={s.btn("secondary")} onClick={addTopic}>ADD</button>
          </div>
        )}
      </div>

      {/* LLM backend */}
      <div style={{ ...s.card, marginBottom: 24 }}>
        <div style={s.sectionTitle}>LLM Backend Override</div>
        <div style={{ display: "flex", gap: 12 }}>
          <div style={{ flex: 1 }}>
            <div style={s.label}>Backend</div>
            <select style={{ ...s.input }} value={policy.llm_backend || ""}
              disabled={!user.is_admin}
              onChange={(e) => setPolicy(p => ({ ...p, llm_backend: e.target.value || null }))}>
              <option value="">Default</option>
              <option value="anthropic">Anthropic</option>
              <option value="openai">OpenAI</option>
              <option value="gemini">Gemini</option>
              <option value="groq">Groq</option>
              <option value="ollama">Ollama</option>
              <option value="openai_compatible">OpenAI-compatible</option>
              <option value="mock">Mock local</option>
            </select>
          </div>
          <div style={{ flex: 2 }}>
            <div style={s.label}>Model</div>
            <input style={s.input} placeholder="e.g. claude-sonnet-4-20250514"
              disabled={!user.is_admin}
              value={policy.llm_model || ""}
              onChange={(e) => setPolicy(p => ({ ...p, llm_model: e.target.value || null }))} />
          </div>
        </div>
      </div>

      {user.is_admin && (
        <div style={{ display: "flex", gap: 12 }}>
          <button style={s.btn("primary")} onClick={save} disabled={saving}>
            {saving ? "Saving..." : "Save policy"}
          </button>
          <button style={s.btn("secondary")} onClick={reset}>Reset defaults</button>
        </div>
      )}
    </div>
  );
}

// MARKDOWN RENDERER HELPERS
