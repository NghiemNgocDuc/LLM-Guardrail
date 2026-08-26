import React, { useState, useEffect } from "react";
import type { ReactNode } from "react";
import { useAuth, useUser, SignIn, SignUp } from "@clerk/clerk-react";
import { api, setClerkTokenProvider } from "./utils/api";
import { identifyUser } from "./utils/analytics";
import type { components } from "./api-types";
import { s } from "./styles/theme";
import GlobalStyles from "./styles/GlobalStyles";
import AuthFlowBackground from "./components/AuthFlowBackground";
import DashboardView from "./views/DashboardView";
import ChatView from "./views/ChatView";
import MemoryView from "./views/MemoryView";
import SkillGuardView from "./views/SkillGuardView";
import BillingView from "./views/BillingView";
import LogsView from "./views/LogsView";
import ApiKeysView from "./views/ApiKeysView";
import PolicyView from "./views/PolicyView";
import AdminView from "./views/AdminView";
import TeamView from "./views/TeamView";
import AnalyticsView from "./views/AnalyticsView";
import ProfileView from "./views/ProfileView";
import HealthView from "./views/HealthView";
import SettingsView from "./views/SettingsView";

type UserOut = components["schemas"]["UserOut"];

type NavItem = { id: string; label: string; icon: string; adminOnly?: boolean };

const NAV: NavItem[] = [
  { id: "dashboard",  label: "Dashboard",      icon: "01" },
  { id: "chat",       label: "LLM Playground", icon: "02" },
  { id: "memory",     label: "Memory",         icon: "" },
  { id: "skills",     label: "Rejected access", icon: "SG" },
  { id: "analytics",  label: "Analytics",      icon: "AN" },
  { id: "billing",    label: "Billing",        icon: "$"  },
  { id: "logs",       label: "Logs",           icon: "03" },
  { id: "keys",       label: "API Keys",       icon: "04" },
  { id: "policy",     label: "Policy",         icon: "05" },
  { id: "team",       label: "Team",           icon: "06" },
  { id: "health",     label: "System Health",  icon: "H"  },
  { id: "admin",      label: "Admin",          icon: "A",  adminOnly: true },
  { id: "settings",   label: "Settings",       icon: "ST" },
];

type GateContext = {
  user: UserOut;
  setUser: React.Dispatch<React.SetStateAction<UserOut | null>>;
  signOut: () => Promise<void>;
};

function ClerkAuthGate({ children }: { children: (ctx: GateContext) => ReactNode }) {
  const { isSignedIn, getToken, signOut } = useAuth();
  const { user: clerkUser } = useUser();
  const [appUser, setAppUser] = useState<UserOut | null>(null);
  const [authMode, setAuthMode] = useState<"signin" | "signup">("signin");

  useEffect(() => {
    if (!isSignedIn || !clerkUser) return;
    setClerkTokenProvider(getToken);
    api<UserOut>("/auth/me").then(u => { identifyUser(u); setAppUser(u); }).catch(() => { identifyUser(null); setAppUser(null); });
  }, [isSignedIn, clerkUser, getToken]);

  if (!isSignedIn || !clerkUser) {
    return (
      <>
        <GlobalStyles />
        <div className="auth-page" style={{
          position: "relative", minHeight: "100vh", background: "#f0fdf4",
          display: "flex", alignItems: "center", justifyContent: "center",
          padding: "40px 24px", overflow: "hidden",
        }}>
          <AuthFlowBackground />
          <div style={{ position: "relative", zIndex: 1, width: "min(420px, 100%)" }}>
            <div style={{ textAlign: "center", marginBottom: 32 }}>
              <div style={{ fontSize: 22, fontWeight: 800, color: "#0f766e" }}>AI Guardrails</div>
              <div style={{ fontSize: 13, color: "#6b7f94", marginTop: 4 }}>
                LLM gateway, agent skills, and policy — one workspace
              </div>
            </div>
            {authMode === "signin" ? (
              <SignIn
                appearance={{ elements: { card: { boxShadow: "none" } } }}
                signUpUrl="#"
                afterSignInUrl="/"
              />
            ) : (
              <SignUp
                appearance={{ elements: { card: { boxShadow: "none" } } }}
                signInUrl="#"
                afterSignUpUrl="/"
              />
            )}
            <div style={{ textAlign: "center", marginTop: 16 }}>
              <button
                onClick={() => setAuthMode(m => m === "signin" ? "signup" : "signin")}
                style={{ background: "none", border: "none", color: "#0f766e", cursor: "pointer", fontSize: 13, fontWeight: 600 }}
              >
                {authMode === "signin" ? "Don't have an account? Sign up" : "Already have an account? Sign in"}
              </button>
            </div>
          </div>
        </div>
      </>
    );
  }

  if (!appUser) {
    return (
      <>
        <GlobalStyles />
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: "100vh", color: "#0f766e", fontSize: 14 }}>Loading workspace...</div>
      </>
    );
  }

  return children({ user: appUser, setUser: setAppUser, signOut });
}

export default function App() {
  const [view, setView] = useState<string>(() => {
    const q = new URLSearchParams(window.location.search);
    const v = q.get("view");
    return v && NAV.some((n) => n.id === v) ? v : "dashboard";
  });
  const [darkMode, setDarkMode] = useState<boolean>(() => localStorage.getItem("guardrails_dark") === "1");
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    localStorage.setItem("guardrails_dark", darkMode ? "1" : "0");
  }, [darkMode]);

  function navigate(id: string) { setView(id); setSidebarOpen(false); }

  return (
    <ClerkAuthGate>
      {({ user, setUser, signOut }) => (
        <div className="app-shell" style={s.app} data-dark={darkMode ? "1" : "0"}>
          <GlobalStyles darkMode={darkMode} />
          <AuthFlowBackground />

          {sidebarOpen && (
            <div style={{ position: "fixed", inset: 0, zIndex: 9, background: "rgba(16,32,51,0.4)" }}
              onClick={() => setSidebarOpen(false)} />
          )}

          <div className={`app-sidebar${sidebarOpen ? " sidebar-open" : ""}`} style={s.sidebar}>
            <div style={s.logo}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div>
                  <div style={{ fontSize: 10, fontWeight: 700, color: "#0f766e", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6 }}>
                    Ngoc Duc Nghiem
                  </div>
                  <div style={s.logoText}>AI Guardrails</div>
                </div>
                <button
                  style={{ background: "none", border: "none", cursor: "pointer", fontSize: 18, color: "#607086", padding: 4 }}
                  onClick={() => setDarkMode(d => !d)}
                  title={darkMode ? "Switch to light mode" : "Switch to dark mode"}
                >
                  {darkMode ? "Light" : "Dark"}
                </button>
              </div>
              <div style={{ fontSize: 11, color: "#7b8a9d", marginTop: 4 }}>Models · agents · skills</div>
              <div style={s.logoSub}>{user.email}</div>
              {user.is_admin && (
                <div style={{ display: "inline-flex", marginTop: 8, ...s.badge("rate_limited") }}>Admin</div>
              )}
            </div>

            {NAV.filter(n => !n.adminOnly || user.is_admin).map(n => (
              <div key={n.id} style={s.navItem(view === n.id)} onClick={() => navigate(n.id)}>
                <span style={{ fontSize: 11, fontWeight: 850, color: view === n.id ? "#0f766e" : "#9aabba" }}>{n.icon}</span>
                <span>{n.label}</span>
              </div>
            ))}
          </div>

          <button className="hamburger" onClick={() => setSidebarOpen(o => !o)}
            style={{
              display: "none", position: "fixed", top: 14, left: 14, zIndex: 20,
              background: "#0f766e", color: "#fff", border: "none", borderRadius: 8,
              width: 40, height: 40, fontSize: 18, cursor: "pointer",
              boxShadow: "0 4px 12px rgba(15,118,110,0.3)",
            }}
          >
            Menu
          </button>

          <div className="app-main" style={s.main}>
            {view === "dashboard"  && <DashboardView />}
            {view === "chat"       && <ChatView />}
            {view === "memory"     && <MemoryView />}
            {view === "skills"     && <SkillGuardView />}
            {view === "analytics"  && <AnalyticsView />}
            {view === "billing"    && <BillingView />}
            {view === "logs"       && <LogsView />}
            {view === "keys"       && <ApiKeysView />}
            {view === "policy"     && <PolicyView user={user} />}
            {view === "team"       && <TeamView user={user} />}
            {view === "health"     && <HealthView />}
            {view === "profile"    && <ProfileView user={user} onUserUpdate={setUser} />}
            {view === "admin"      && user.is_admin && <AdminView />}
            {view === "settings"   && (
              <SettingsView
                user={user}
                onUserUpdate={setUser}
                darkMode={darkMode}
                setDarkMode={setDarkMode}
                onLogout={() => { signOut(); setUser(null); }}
              />
            )}
          </div>
        </div>
      )}
    </ClerkAuthGate>
  );
}
