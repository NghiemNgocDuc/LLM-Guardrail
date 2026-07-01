import React, { useState, useEffect, useCallback, useRef } from "react";
import { api, getToken, setTokens, clearTokens, getGatewayKey, setGatewayKey, maskGatewayKey, gatewayKeyInputProps, formatApiError } from "../utils/api";
import { s } from "../styles/theme";
import GlobalStyles from "../styles/GlobalStyles";
import AuthFlowBackground from "../components/AuthFlowBackground";
import AuthTerminalIntro from "../components/AuthTerminalIntro";
import PasswordInput from "../components/PasswordInput";
const authStyles = {
  page: {
    position: "relative",
    minHeight: "100vh",
    background: "#f0fdf4",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: "40px 24px",
    overflow: "hidden",
  },
  pageInner: {
    position: "relative",
    zIndex: 1,
    width: "min(1200px, 100%)",
    display: "grid",
    gridTemplateColumns: "1fr 420px",
    gap: 48,
    alignItems: "center",
  },
  formShell: {},
  formCard: {
    background: "rgba(255, 255, 255, 0.9)",
    border: "1px solid rgba(15, 118, 110, 0.15)",
    borderRadius: 16,
    padding: "32px 28px",
    boxShadow: "0 24px 64px rgba(15, 118, 110, 0.12), inset 0 1px 0 rgba(255,255,255,0.5)",
    backdropFilter: "blur(20px)",
  },
  codeLabel: {
    fontSize: 11,
    fontWeight: 700,
    color: "#0f766e",
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
    letterSpacing: "0.02em",
  },
  codeInput: {
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
    fontSize: 13,
  },
  passwordWrap: { position: "relative", width: "100%" },
  passwordToggle: {
    position: "absolute",
    right: 8,
    top: "50%",
    transform: "translateY(-50%)",
    border: "none",
    background: "transparent",
    color: "#64748b",
    fontSize: 11,
    fontWeight: 700,
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
    cursor: "pointer",
    padding: "6px 8px",
    borderRadius: 6,
    lineHeight: 1,
  },
};

function authScreenFromLocation() {
  const path = window.location.pathname.replace(/\/$/, "") || "/";
  const token = new URLSearchParams(window.location.search).get("token") || "";
  if (path.endsWith("/verify-email") && token) return { screen: "verify", token };
  if (path.endsWith("/reset-password") && token) return { screen: "reset", token };
  return { screen: "auth", token: "" };
}

export default function AuthView({ onAuth }) {
  const initial = authScreenFromLocation();
  const [tab, setTab] = useState("login");
  const [screen, setScreen] = useState(initial.screen);
  const [linkToken, setLinkToken] = useState(initial.token);
  const [form, setForm] = useState({
    email: "", password: "", full_name: "", org_name: "", new_password: "", confirm_password: "",
  });
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState("");

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const handleCopy = (text, label) => {
    navigator.clipboard.writeText(text);
    setCopied(label);
    setTimeout(() => setCopied(""), 1500);
  };

  function goHome() {
    window.history.replaceState({}, "", "/");
    setScreen("auth");
    setLinkToken("");
    setError("");
    setInfo("");
  }

  useEffect(() => {
    if (screen !== "verify" || !linkToken) return;
    setLoading(true);
    setError("");
    api("/auth/verify-email", { method: "POST", body: { token: linkToken } })
      .then((data) => {
        window.history.replaceState({}, "", "/");
        setScreen("auth");
        setLinkToken("");
        setTab("login");
        setInfo(data.message);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [screen, linkToken]);

  async function submit() {
    setError(""); setInfo(""); setLoading(true);
    try {
      if (tab === "login") {
        const data = await api("/auth/login", {
          method: "POST", body: { email: form.email, password: form.password },
        });
        setTokens(data.access_token, data.refresh_token);
        const me = await api("/auth/me");
        onAuth(me);
      } else if (tab === "signup") {
        const data = await api("/auth/signup", {
          method: "POST",
          body: {
            email: form.email, password: form.password,
            full_name: form.full_name,
            org_name: form.org_name || undefined,
          },
        });
        setInfo(data.message);
        setTab("login");
      } else if (tab === "forgot") {
        const data = await api("/auth/forgot-password", {
          method: "POST", body: { email: form.email },
        });
        setInfo(data.message);
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function submitReset() {
    setError(""); setInfo("");
    if (form.new_password !== form.confirm_password) {
      setError("Passwords do not match");
      return;
    }
    setLoading(true);
    try {
      const data = await api("/auth/reset-password", {
        method: "POST",
        body: { token: linkToken, new_password: form.new_password },
      });
      window.history.replaceState({}, "", "/");
      setScreen("auth");
      setLinkToken("");
      setTab("login");
      setInfo(data.message);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function resendVerification() {
    if (!form.email) {
      setError("Enter your email first");
      return;
    }
    setError(""); setInfo(""); setLoading(true);
    try {
      const data = await api("/auth/resend-verification", {
        method: "POST", body: { email: form.email },
      });
      setInfo(data.message);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
    <GlobalStyles />
    <div className="auth-page" style={authStyles.page}>
      <div style={{ position: "absolute", top: 24, left: 32, zIndex: 10, fontSize: 13, fontWeight: 700, color: "#0f766e", letterSpacing: "0.02em" }}>
        Ngoc Duc Nghiem
      </div>
      <AuthFlowBackground />
      <div className="auth-page-inner" style={authStyles.pageInner}>
        <AuthTerminalIntro />

        <div className="auth-form-shell" style={authStyles.formShell}>
          <div className="auth-form-logo">
            <div className="auth-form-logo-title">AI Guardrails</div>
            <div className="auth-form-logo-sub">
              LLM gateway, agent skills, and policy — one workspace
            </div>
          </div>

          <div className="auth-form-card" style={authStyles.formCard}>
            <div className="auth-form-title">
              {screen === "verify" ? "Verify Email" :
               screen === "reset" ? "Reset Password" :
               tab === "forgot" ? "Reset Password" :
               tab === "signup" ? "Create an Account" : "Welcome Back"}
            </div>

            {screen === "auth" && (
              <div className="auth-form-tabs">
                {["login", "signup"].map((t) => (
                  <div
                    key={t}
                    onClick={() => { setTab(t); setError(""); setInfo(""); }}
                    className={`auth-form-tab ${tab === t ? "auth-form-tab-active" : ""}`}
                  >
                    {t === "login" ? "Sign in" : "Sign up"}
                  </div>
                ))}
              </div>
            )}

            {error && <div className="auth-form-alert-error">{error}</div>}
            {info && <div className="auth-form-alert-success">{info}</div>}

            {screen === "verify" && (
              <div style={{ color: "#94a3b8", fontSize: 14 }}>
                {loading ? "Verifying your email…" : "Verification complete. You can sign in."}
              </div>
            )}

            {screen === "reset" && (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <label className="auth-form-label">New Password</label>
                <PasswordInput
                  placeholder="Min 8 characters"
                  value={form.new_password}
                  onChange={set("new_password")}
                  autoComplete="new-password"
                />
                <label className="auth-form-label">Confirm Password</label>
                <PasswordInput
                  placeholder="Confirm new password"
                  value={form.confirm_password}
                  onChange={set("confirm_password")}
                  autoComplete="new-password"
                />
                <button className="auth-form-btn-primary" style={{ marginTop: 8 }} onClick={submitReset} disabled={loading}>
                  {loading ? "Resetting..." : "Reset Password"}
                </button>
                <button type="button" className="auth-form-btn-secondary" onClick={goHome}>Back to sign in</button>
              </div>
            )}

            {screen === "auth" && (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {tab === "login" && (
                  <div style={{
                    background: "rgba(15, 118, 110, 0.06)",
                    border: "1px solid rgba(15, 118, 110, 0.15)",
                    borderRadius: 10,
                    padding: "12px 14px",
                    fontSize: 12,
                  }}>
                    <div style={{ fontWeight: 700, color: "#0f766e", marginBottom: 8, fontSize: 11, textTransform: "uppercase", letterSpacing: "0.04em" }}>
                      Test Account
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                      <span style={{ color: "#475569", flex: 1, fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace", fontSize: 12 }}>dnghiem@umass.edu</span>
                      <button onClick={() => handleCopy("dnghiem@umass.edu", "Email copied")} title="Copy email" style={{ border: "none", background: "transparent", cursor: "pointer", color: "#0f766e", padding: 4, borderRadius: 4, display: "flex", alignItems: "center", justifyContent: "center", transition: "background 0.15s" }}
                        onMouseEnter={(e) => e.currentTarget.style.background = "rgba(15, 118, 110, 0.1)"}
                        onMouseLeave={(e) => e.currentTarget.style.background = "transparent"}>
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                        </svg>
                      </button>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ color: "#475569", flex: 1, fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace", fontSize: 12 }}>@aZ123456123</span>
                      <button onClick={() => handleCopy("@aZ123456123", "Password copied")} title="Copy password" style={{ border: "none", background: "transparent", cursor: "pointer", color: "#0f766e", padding: 4, borderRadius: 4, display: "flex", alignItems: "center", justifyContent: "center", transition: "background 0.15s" }}
                        onMouseEnter={(e) => e.currentTarget.style.background = "rgba(15, 118, 110, 0.1)"}
                        onMouseLeave={(e) => e.currentTarget.style.background = "transparent"}>
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                        </svg>
                      </button>
                    </div>
                  </div>
                )}
                {tab === "signup" && (
                  <>
                    <label className="auth-form-label">Full Name</label>
                    <input className="auth-form-input" placeholder="Jane Developer"
                      value={form.full_name} onChange={set("full_name")} />
                  </>
                )}
                {(tab === "login" || tab === "signup" || tab === "forgot") && (
                  <>
                    <label className="auth-form-label">Email Address</label>
                    <input className="auth-form-input" placeholder="dev@acme.corp"
                      type="email" value={form.email} onChange={set("email")} autoComplete="email" />
                  </>
                )}
                {tab !== "forgot" && (
                  <>
                    <label className="auth-form-label">Password</label>
                    <PasswordInput
                      placeholder="••••••••"
                      value={form.password}
                      onChange={set("password")}
                      autoComplete={tab === "login" ? "current-password" : "new-password"}
                    />
                  </>
                )}
                {tab === "signup" && (
                  <>
                    <label className="auth-form-label">Organization Name (Optional)</label>
                    <input className="auth-form-input" placeholder="Acme Corp"
                      value={form.org_name} onChange={set("org_name")} />
                  </>
                )}
                <button className="auth-form-btn-primary" style={{ marginTop: 8 }} onClick={submit} disabled={loading}>
                  {loading ? "Please wait..." :
                    tab === "login" ? "Sign In" :
                    tab === "forgot" ? "Send Reset Link" : "Create Account"}
                </button>

                {tab === "login" && (
                  <button type="button" className="auth-form-btn-secondary"
                    onClick={() => { setTab("forgot"); setError(""); setInfo(""); }}>
                    Forgot password?
                  </button>
                )}
                {tab === "forgot" && (
                  <button type="button" className="auth-form-btn-secondary"
                    onClick={() => { setTab("login"); setError(""); setInfo(""); }}>
                    Back to login
                  </button>
                )}
                {(tab === "login" || tab === "forgot") && (
                  <button type="button" className="auth-form-btn-secondary"
                    onClick={resendVerification} disabled={loading}>
                    Resend verification email
                  </button>
                )}
              </div>
            )}
          </div>
          
          <div className="auth-form-footer">
            {"// demo_mode: rate limits active"}
          </div>

          {copied && (
            <div style={{
              position: "fixed", bottom: 24, left: "50%", transform: "translateX(-50%)",
              background: "#0f766e", color: "#fff", padding: "10px 20px", borderRadius: 10,
              fontSize: 13, fontWeight: 600, zIndex: 999, boxShadow: "0 8px 24px rgba(15,118,110,0.35)",
              display: "flex", alignItems: "center", gap: 8, transition: "opacity 0.2s",
            }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="20 6 9 17 4 12"></polyline>
              </svg>
              {copied}
            </div>
          )}
        </div>
      </div>
    </div>
    </>
  );
}

// DASHBOARD VIEW
