import { useEffect, useRef, useState } from "react";
import type { ChangeEvent, FormEvent } from "react";
import { api, setTokens } from "../utils/api";
import GlobalStyles from "../styles/GlobalStyles";
import AuthFlowBackground from "../components/AuthFlowBackground";
import AuthWelcome from "../components/AuthWelcome";
import PasswordInput from "../components/PasswordInput";
import { ProjectIntroHelp } from "../components/WorkspaceHelp";
import type { components } from "../api-types";
import "../styles/auth.css";

type UserOut = components["schemas"]["UserOut"];
interface AuthTokens { access_token: string; refresh_token: string }
interface AuthMessageResponse { message: string }
interface AuthScreen { screen: "verify" | "reset" | "auth"; token: string }
interface AuthForm {
  email: string; password: string; full_name: string; org_name: string;
  new_password: string; confirm_password: string;
}
type AuthTab = "login" | "signup" | "forgot";

const DEMO_EMAIL = "demo@example.com";
const DEMO_PASSWORD = "Demo-Guardrails-2026!";

function authScreenFromLocation(): AuthScreen {
  const path = window.location.pathname.replace(/\/$/, "") || "/";
  const token = new URLSearchParams(window.location.search).get("token") || "";
  if (path.endsWith("/verify-email") && token) return { screen: "verify", token };
  if (path.endsWith("/reset-password") && token) return { screen: "reset", token };
  return { screen: "auth", token: "" };
}

function AuthIcon({ kind }: { kind: "shield" | "arrow" | "copy" | "check" }) {
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {kind === "shield" && <><path d="m12 3 8 3v5c0 5-3.5 8-8 10-4.5-2-8-5-8-10V6l8-3Z" /><path d="m8.5 12 2.5 2.5 4.5-5" /></>}
    {kind === "arrow" && <><path d="M5 12h14" /><path d="m14 7 5 5-5 5" /></>}
    {kind === "copy" && <><rect x="9" y="9" width="11" height="12" rx="2" /><path d="M15 5V3H4v12h2" /></>}
    {kind === "check" && <path d="m5 12 4 4L19 6" />}
  </svg>;
}

export default function AuthView({ onAuth }: { onAuth: (user: UserOut) => void }) {
  const initial = authScreenFromLocation();
  const [tab, setTab] = useState<AuthTab>("login");
  const [screen, setScreen] = useState<AuthScreen["screen"]>(initial.screen);
  const [linkToken, setLinkToken] = useState(initial.token);
  const [form, setForm] = useState<AuthForm>({ email: "", password: "", full_name: "", org_name: "", new_password: "", confirm_password: "" });
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState("");
  const [mobileLayout, setMobileLayout] = useState(() => window.matchMedia("(max-width: 850px)").matches);
  const feedbackRef = useRef<HTMLDivElement>(null);
  const copyTimer = useRef<number | undefined>(undefined);
  const verificationRequest = useRef<{ token: string; promise: Promise<AuthMessageResponse> } | null>(null);
  const set = (key: keyof AuthForm) => (event: ChangeEvent<HTMLInputElement>) => setForm((current) => ({ ...current, [key]: event.target.value }));

  useEffect(() => { if (error) feedbackRef.current?.focus(); }, [error]);
  useEffect(() => () => window.clearTimeout(copyTimer.current), []);
  useEffect(() => {
    const media = window.matchMedia("(max-width: 850px)");
    const update = () => setMobileLayout(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  async function copyDemoValue(value: string, label: string) {
    window.clearTimeout(copyTimer.current);
    try {
      await navigator.clipboard.writeText(value);
      setCopied(label);
    } catch {
      setCopied("Copy is unavailable. You can select and copy the value.");
    }
    copyTimer.current = window.setTimeout(() => setCopied(""), 2500);
  }

  function changeTab(next: AuthTab) {
    setTab(next);
    setError("");
    setInfo("");
    setCopied("");
  }

  function goHome() {
    window.history.replaceState({}, "", "/");
    setScreen("auth");
    setLinkToken("");
    changeTab("login");
  }

  useEffect(() => {
    if (screen !== "verify" || !linkToken) return;
    let active = true;
    setLoading(true);
    setError("");
    // React StrictMode replays effects. Reuse this request because the link is single-use.
    if (verificationRequest.current?.token !== linkToken) {
      verificationRequest.current = {
        token: linkToken,
        promise: api<AuthMessageResponse>("/auth/verify-email", { method: "POST", body: { token: linkToken } }),
      };
    }
    verificationRequest.current.promise
      .then((data) => {
        if (!active) return;
        window.history.replaceState({}, "", "/");
        setScreen("auth");
        setLinkToken("");
        setTab("login");
        setInfo(data.message);
        setLoading(false);
      })
      .catch((reason: Error) => {
        if (!active) return;
        setError(reason.message);
        setLoading(false);
      });
    return () => { active = false; };
  }, [screen, linkToken]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (loading) return;
    setError("");
    setInfo("");
    setLoading(true);
    try {
      if (tab === "login") {
        const data = await api<AuthTokens>("/auth/login", { method: "POST", body: { email: form.email, password: form.password } });
        setTokens(data.access_token, data.refresh_token);
        const me = await api<UserOut>("/auth/me");
        onAuth(me);
      } else if (tab === "signup") {
        const data = await api<AuthMessageResponse>("/auth/signup", {
          method: "POST",
          body: { email: form.email, password: form.password, full_name: form.full_name, org_name: form.org_name || undefined },
        });
        setInfo(data.message);
        setTab("login");
      } else {
        const data = await api<AuthMessageResponse>("/auth/forgot-password", { method: "POST", body: { email: form.email } });
        setInfo(data.message);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }

  async function submitReset(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (loading) return;
    setError("");
    setInfo("");
    if (form.new_password !== form.confirm_password) {
      setError("Passwords do not match. Enter the same password in both fields.");
      return;
    }
    setLoading(true);
    try {
      const data = await api<AuthMessageResponse>("/auth/reset-password", { method: "POST", body: { token: linkToken, new_password: form.new_password } });
      window.history.replaceState({}, "", "/");
      setScreen("auth");
      setLinkToken("");
      setTab("login");
      setInfo(data.message);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }

  async function resendVerification() {
    if (loading) return;
    setError("");
    setInfo("");
    if (!form.email) {
      setError("Enter your email address to receive a new verification link.");
      return;
    }
    setLoading(true);
    try {
      const data = await api<AuthMessageResponse>("/auth/resend-verification", { method: "POST", body: { email: form.email } });
      setInfo(data.message);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }

  const title = screen === "verify" ? "Verify your email." : screen === "reset" ? "A fresh start." : tab === "forgot" ? "Forgot your password?" : tab === "signup" ? "Build with confidence." : "Welcome back.";
  const description = screen === "verify" ? "We’re checking your verification link." : screen === "reset" ? "Choose a new password for your workspace." : tab === "forgot" ? "Enter your email and we’ll send you a reset link." : tab === "signup" ? "Create your account to start protecting AI workflows." : "Sign in to your guardrail workspace.";
  const feedbackId = error || info ? "gr-auth-feedback" : undefined;

  return <>
    <GlobalStyles />
    <div className="gr-auth-page">
      <AuthFlowBackground />
      <header className="gr-auth-header">
        <a href="/" className="gr-auth-wordmark" aria-label="LLM Guardrail home"><span className="gr-auth-brand-symbol"><AuthIcon kind="shield" /></span><span>LLM<span className="gr-auth-wordmark-light"> Guardrail</span></span></a>
        <div className="gr-auth-header-actions"><span className="gr-auth-header-note">Your models. Your rules.</span><ProjectIntroHelp /></div>
      </header>
      <h1 className="gr-auth-sr-only">LLM Guardrail account access</h1>

      <main className="gr-auth-layout">
        {!mobileLayout && <AuthWelcome />}
        <section className="gr-auth-form-shell" aria-labelledby="gr-auth-form-title">
          <div className="gr-auth-form-card">
            <div className="gr-auth-form-heading" key={screen + tab}><p className="gr-auth-form-eyebrow">YOUR WORKSPACE</p><h2 id="gr-auth-form-title">{title}</h2><p>{description}</p></div>
            {screen === "auth" && tab !== "forgot" && <div className="gr-auth-form-tabs" aria-label="Account access">
              <button type="button" aria-pressed={tab === "login"} onClick={() => changeTab("login")} disabled={loading}>Sign in</button>
              <button type="button" aria-pressed={tab === "signup"} onClick={() => changeTab("signup")} disabled={loading}>Create account</button>
            </div>}
            {error && <div id="gr-auth-feedback" className="gr-auth-feedback gr-auth-feedback-error" role="alert" tabIndex={-1} ref={feedbackRef}>{error}</div>}
            {info && <div id="gr-auth-feedback" className="gr-auth-feedback gr-auth-feedback-success" role="status"><AuthIcon kind="check" /><span>{info}</span></div>}

            {screen === "verify" && <div className="gr-auth-verify">
              {!error && <p role="status"><span className="gr-auth-spinner" /> Verifying your email…</p>}
              {error && <p>Return to sign in to request a new verification email.</p>}
              <button type="button" className="gr-auth-secondary" onClick={goHome} disabled={loading}>Back to sign in</button>
            </div>}

            {screen === "reset" && <form className="gr-auth-form" onSubmit={submitReset} aria-busy={loading}>
              <fieldset disabled={loading}>
                <div className="gr-auth-field"><label htmlFor="gr-new-password">New password</label><PasswordInput id="gr-new-password" name="new_password" placeholder="At least 8 characters" value={form.new_password} onChange={set("new_password")} autoComplete="new-password" required minLength={8} aria-describedby={feedbackId} /></div>
                <div className="gr-auth-field"><label htmlFor="gr-confirm-password">Confirm password</label><PasswordInput id="gr-confirm-password" name="confirm_password" placeholder="Repeat your new password" value={form.confirm_password} onChange={set("confirm_password")} autoComplete="new-password" required minLength={8} aria-describedby={feedbackId} aria-invalid={error.startsWith("Passwords do not match") || undefined} /></div>
                <button className="gr-auth-primary" type="submit">{loading ? <><span className="gr-auth-spinner" /> Updating password…</> : <>Update password<AuthIcon kind="arrow" /></>}</button>
              </fieldset>
              <button type="button" className="gr-auth-secondary" onClick={goHome} disabled={loading}>Back to sign in</button>
            </form>}

            {screen === "auth" && <form className="gr-auth-form" onSubmit={submit} aria-busy={loading}>
              <fieldset disabled={loading}>
                {tab === "signup" && <div className="gr-auth-field"><label htmlFor="gr-full-name">Full name</label><input id="gr-full-name" name="full_name" type="text" placeholder="Alex Morgan" value={form.full_name} onChange={set("full_name")} autoComplete="name" required /></div>}
                <div className="gr-auth-field"><label htmlFor="gr-email">Email address</label><input id="gr-email" name="email" type="email" placeholder="you@company.com" value={form.email} onChange={set("email")} autoComplete="email" autoCapitalize="none" spellCheck={false} required aria-describedby={feedbackId} /></div>
                {tab !== "forgot" && <div className="gr-auth-field"><div className="gr-auth-field-header"><label htmlFor="gr-password">Password</label>{tab === "login" && <button type="button" className="gr-auth-inline-link" onClick={() => changeTab("forgot")}>Forgot password?</button>}</div><PasswordInput id="gr-password" name="password" placeholder={tab === "signup" ? "At least 8 characters" : "Enter your password"} value={form.password} onChange={set("password")} autoComplete={tab === "login" ? "current-password" : "new-password"} required minLength={tab === "signup" ? 8 : undefined} aria-describedby={feedbackId} /></div>}
                {tab === "signup" && <div className="gr-auth-field"><label htmlFor="gr-org-name">Organization <span className="gr-auth-optional">(optional)</span></label><input id="gr-org-name" name="org_name" type="text" placeholder="Your team or company" value={form.org_name} onChange={set("org_name")} autoComplete="organization" /></div>}
                <button className="gr-auth-primary" type="submit">{loading ? <><span className="gr-auth-spinner" /> Please wait…</> : <>{tab === "login" ? "Sign in to workspace" : tab === "forgot" ? "Send reset link" : "Create account"}<AuthIcon kind="arrow" /></>}</button>
              </fieldset>
              {tab === "forgot" && <button type="button" className="gr-auth-secondary" onClick={() => changeTab("login")} disabled={loading}>Back to sign in</button>}
            </form>}

            {screen === "auth" && tab === "login" && <div className="gr-auth-demo">
              <div className="gr-auth-demo-heading"><span>Just exploring?</span><button type="button" onClick={() => { setForm((current) => ({ ...current, email: DEMO_EMAIL, password: DEMO_PASSWORD })); setError(""); setInfo(""); setCopied("Demo credentials filled. Select Sign in to workspace to continue."); }} disabled={loading}>Use demo account <AuthIcon kind="arrow" /></button></div>
              <p>Public demo with sample data. Avoid sharing private information.</p>
              <details><summary>View demo credentials</summary><div className="gr-auth-demo-values">{[{ label: "Email", value: DEMO_EMAIL }, { label: "Password", value: DEMO_PASSWORD }].map((item) => <div key={item.label}><span>{item.label}</span><code>{item.value}</code><button type="button" onClick={() => copyDemoValue(item.value, `${item.label} copied`)} aria-label={`Copy demo ${item.label.toLowerCase()}`}><AuthIcon kind="copy" /></button></div>)}</div></details>
              <div className="gr-auth-demo-status" role="status">{copied}</div>
            </div>}
            {screen === "auth" && (tab === "login" || tab === "forgot") && <p className="gr-auth-resend">Need to verify your email? <button type="button" onClick={resendVerification} disabled={loading}>Resend link</button></p>}
          </div>
          <p className="gr-auth-form-note"><AuthIcon kind="shield" /> Your AI, with rules you can understand.</p>
        </section>
        {mobileLayout && <AuthWelcome />}
      </main>
      <footer className="gr-auth-footer"><span>LLM Guardrail</span><span>Built by Ngoc Duc Nghiem</span></footer>
    </div>
  </>;
}
