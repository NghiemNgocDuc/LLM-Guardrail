import React, { useState, useEffect } from "react";
import { api, setTokens } from "../utils/api";
import { s } from "../styles/theme";
import GlobalStyles from "../styles/GlobalStyles";
import AuthFlowBackground from "../components/AuthFlowBackground";
import AuthTerminalIntro from "../components/AuthTerminalIntro";
import PasswordInput from "../components/PasswordInput";
import type { components } from "../api-types";
import type { CSSProperties } from "react";

type UserOut = components["schemas"]["UserOut"];

interface AuthTokens { access_token: string; refresh_token: string }
interface AuthMessageResponse { message: string }

const authStyles: Record<string, CSSProperties> = {
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

interface AuthScreen { screen: "verify" | "reset" | "auth"; token: string }

function authScreenFromLocation(): AuthScreen {
  const path = window.location.pathname.replace(/\/$/, "") || "/";
  const token = new URLSearchParams(window.location.search).get("token") || "";
  if (path.endsWith("/verify-email") && token) return { screen: "verify", token };
  if (path.endsWith("/reset-password") && token) return { screen: "reset", token };
  return { screen: "auth", token: "" };
}

interface AuthForm {
  email: string; password: string; full_name: string; org_name: string;
  new_password: string; confirm_password: string;
}

export default function AuthView({ onAuth }: { onAuth: (user: UserOut) => void }) {
  const initial = authScreenFromLocation();
  const [tab, setTab] = useState<"login" | "signup" | "forgot">("login");
  const [screen, setScreen] = useState<AuthScreen["screen"]>(initial.screen);
  const [linkToken, setLinkToken] = useState(initial.token);
  const [form, setForm] = useState<AuthForm>({
    email: "", password: "", full_name: "", org_name: "", new_password: "", confirm_password: "",
  });
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [loading, setLoading] = useState(false);

  const set = (k: keyof AuthForm) => (e: React.ChangeEvent<HTMLInputElement>) => setForm((f) => ({ ...f, [k]: e.target.value }));

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
    api<AuthMessageResponse>("/auth/verify-email", { method: "POST", body: { token: linkToken } })
      .then((data) => {
        window.history.replaceState({}, "", "/");
        setScreen("auth");
        setLinkToken("");
        setTab("login");
        setInfo(data.message);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [screen, linkToken]);

  async function submit() {
    setError(""); setInfo(""); setLoading(true);
    try {
      if (tab === "login") {
        const data = await api<AuthTokens>("/auth/login", {
          method: "POST", body: { email: form.email, password: form.password },
        });
        setTokens(data.access_token, data.refresh_token);
        const me = await api<UserOut>("/auth/me");
        onAuth(me);
      } else if (tab === "signup") {
        const data = await api<AuthMessageResponse>("/auth/signup", {
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
        const data = await api<AuthMessageResponse>("/auth/forgot-password", {
          method: "POST", body: { email: form.email },
        });
        setInfo(data.message);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
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
      const data = await api<AuthMessageResponse>("/auth/reset-password", {
        method: "POST",
        body: { token: linkToken, new_password: form.new_password },
      });
      window.history.replaceState({}, "", "/");
      setScreen("auth");
      setLinkToken("");
      setTab("login");
      setInfo(data.message);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
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
      const data = await api<AuthMessageResponse>("/auth/resend-verification", {
        method: "POST", body: { email: form.email },
      });
      setInfo(data.message);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
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
                {(["login", "signup"] as const).map((t) => (
                  <div key={t} onClick={() => { setTab(t); setError(""); setInfo(""); }} className={`auth-form-tab ${tab === t ? "auth-form-tab-active" : ""}`}>
                    {t === "login" ? "Sign in" : "Sign up"}
                  </div>
                ))}
              </div>
            )}
            {error && <div className="auth-form-alert-error">{error}</div>}
            {info && <div className="auth-form-alert-success">{info}</div>}
            {screen === "verify" && <div style={{ color: "#94a3b8", fontSize: 14 }}>{loading ? "Verifying your email..." : "Verification complete. You can sign in."}</div>}
            {screen === "reset" && (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <label className="auth-form-label">New Password</label>
                <PasswordInput placeholder="Min 8 characters" value={form.new_password} onChange={set("new_password")} autoComplete="new-password" />
                <label className="auth-form-label">Confirm Password</label>
                <PasswordInput placeholder="Confirm new password" value={form.confirm_password} onChange={set("confirm_password")} autoComplete="new-password" />
                <button className="auth-form-btn-primary" style={{ marginTop: 8 }} onClick={submitReset} disabled={loading}>{loading ? "Resetting..." : "Reset Password"}</button>
                <button type="button" className="auth-form-btn-secondary" onClick={goHome}>Back to sign in</button>
              </div>
            )}
            {screen === "auth" && (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {tab === "signup" && <><label className="auth-form-label">Full Name</label><input className="auth-form-input" placeholder="Jane Developer" value={form.full_name} onChange={set("full_name")} /></>}
                <label className="auth-form-label">Email Address</label>
                <input className="auth-form-input" placeholder="dev@acme.corp" type="email" value={form.email} onChange={set("email")} autoComplete="email" />
                {tab !== "forgot" && <><label className="auth-form-label">Password</label><PasswordInput placeholder="••••••••" value={form.password} onChange={set("password")} autoComplete={tab === "login" ? "current-password" : "new-password"} /></>}
                {tab === "signup" && <><label className="auth-form-label">Organization Name (Optional)</label><input className="auth-form-input" placeholder="Acme Corp" value={form.org_name} onChange={set("org_name")} /></>}
                <button className="auth-form-btn-primary" style={{ marginTop: 8 }} onClick={submit} disabled={loading}>{loading ? "Please wait..." : tab === "login" ? "Sign In" : tab === "forgot" ? "Send Reset Link" : "Create Account"}</button>
                {tab === "login" && <button type="button" className="auth-form-btn-secondary" onClick={() => { setTab("forgot"); setError(""); setInfo(""); }}>Forgot password?</button>}
                {tab === "forgot" && <button type="button" className="auth-form-btn-secondary" onClick={() => { setTab("login"); setError(""); setInfo(""); }}>Back to login</button>}
                {(tab === "login" || tab === "forgot") && <button type="button" className="auth-form-btn-secondary" onClick={resendVerification} disabled={loading}>Resend verification email</button>}
              </div>
            )}
          </div>
          
          <div className="auth-form-footer">
            {"// demo_mode: rate limits active"}
          </div>

        </div>
      </div>
    </div>
    </>
  );
}

// DASHBOARD VIEW
