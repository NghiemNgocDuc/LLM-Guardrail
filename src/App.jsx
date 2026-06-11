import React, { useState, useEffect, useCallback, useRef } from "react";
import { api, getToken, setTokens, clearTokens, getGatewayKey, setGatewayKey, maskGatewayKey, gatewayKeyInputProps, formatApiError } from "./utils/api";
import { s } from "./styles/theme";
import GlobalStyles from "./styles/GlobalStyles";
import AuthView from "./views/AuthView";
import DashboardView from "./views/DashboardView";
import ChatView from "./views/ChatView";
import SkillGuardView from "./views/SkillGuardView";
import BillingView from "./views/BillingView";
import LogsView from "./views/LogsView";
import ApiKeysView from "./views/ApiKeysView";
import PolicyView from "./views/PolicyView";
import AdminView from "./views/AdminView";
import TeamView from "./views/TeamView";
import AuthFlowBackground from "./components/AuthFlowBackground";
// ROOT APP
const NAV = [
  { id: "dashboard", label: "Dashboard",    icon: "01" },
  { id: "chat",      label: "LLM Playground", icon: "02" },
  { id: "skills",    label: "Rejected access",  icon: "SG" },
  { id: "billing",   label: "Billing",      icon: "$" },
  { id: "logs",      label: "Logs",         icon: "03" },
  { id: "keys",      label: "API Keys",     icon: "04" },
  { id: "policy",    label: "Policy",       icon: "05" },
  { id: "team",      label: "Team",         icon: "06" },
  { id: "admin",     label: "Admin",        icon: "A", adminOnly: true },
];

export default function App() {
  const [user, setUser] = useState(null);
  const [view, setView] = useState(() => {
    const q = new URLSearchParams(window.location.search);
    const v = q.get("view");
    return v && NAV.some((n) => n.id === v) ? v : "dashboard";
  });

  // Try to restore session
  useEffect(() => {
    if (getToken()) {
      api("/auth/me").then(setUser).catch(() => clearTokens());
    }
  }, []);

  function logout() { clearTokens(); setUser(null); }

  if (!user) return <><GlobalStyles /><AuthView onAuth={setUser} /></>;

  return (
    <div className="app-shell" style={s.app}>
      <GlobalStyles />
      <AuthFlowBackground />
      {/* Sidebar */}
      <div className="app-sidebar" style={s.sidebar}>
        <div style={s.logo}>
          <div style={{ fontSize: 10, fontWeight: 700, color: "#0f766e", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6 }}>
            Ngoc Duc Nghiem
          </div>
          <div style={s.logoText}>AI Guardrails</div>
          <div style={{ fontSize: 11, color: "#7b8a9d", marginTop: 4 }}>Models · agents · skills</div>
          <div style={s.logoSub}>{user.email}</div>
          {user.is_admin && (
            <div style={{ display: "inline-flex", marginTop: 8, ...s.badge("rate_limited") }}>Admin</div>
          )}
        </div>
        {NAV.filter(n => !n.adminOnly || user.is_admin).map(n => (
          <div key={n.id} style={s.navItem(view === n.id)} onClick={() => setView(n.id)}>
            <span style={{ fontSize: 11, fontWeight: 850, color: view === n.id ? "#0f766e" : "#9aabba" }}>{n.icon}</span>
            <span>{n.label}</span>
          </div>
        ))}
        <div style={{ flex: 1 }} />
        <div style={{ ...s.navItem(false), marginTop: "auto" }} onClick={logout}>
          <span style={{ fontSize: 11, fontWeight: 850, color: "#9aabba" }}>--</span><span>Sign out</span>
        </div>
      </div>

      {/* Main */}
      <div className="app-main" style={s.main}>
        {view === "dashboard" && <DashboardView />}
        {view === "chat"      && <ChatView />}
        {view === "skills"    && <SkillGuardView />}
        {view === "billing"   && <BillingView />}
        {view === "logs"      && <LogsView />}
        {view === "keys"      && <ApiKeysView />}
        {view === "policy"    && <PolicyView user={user} />}
        {view === "team"      && <TeamView user={user} />}
        {view === "admin"     && user.is_admin && <AdminView />}
      </div>
    </div>
  );
}


