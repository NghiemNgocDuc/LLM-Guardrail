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

const NAV = [
  { id: "dashboard", label: "Dashboard",      icon: "01" },
  { id: "chat",      label: "LLM Playground", icon: "02" },
  { id: "skills",    label: "Rejected access", icon: "SG" },
  { id: "billing",   label: "Billing",        icon: "$"  },
  { id: "logs",      label: "Logs",           icon: "03" },
  { id: "keys",      label: "API Keys",       icon: "04" },
  { id: "policy",    label: "Policy",         icon: "05" },
  { id: "team",      label: "Team",           icon: "06" },
  { id: "admin",     label: "Admin",          icon: "A",  adminOnly: true },
];

function ChangePasswordModal({ onClose }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  async function submit(e) {
    e.preventDefault();
    if (next !== confirm) { setError("New passwords do not match."); return; }
    setSaving(true); setError(""); setSuccess("");
    try {
      const res = await api("/auth/change-password", {
        method: "POST",
        body: { current_password: current, new_password: next },
      });
      setSuccess(res.message || "Password changed.");
      setCurrent(""); setNext(""); setConfirm("");
    } catch (e) { setError(e.message); }
    finally { setSaving(false); }
  }

  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 1000,
      background: "rgba(16,32,51,0.45)", backdropFilter: "blur(4px)",
      display: "flex", alignItems: "center", justifyContent: "center",
    }} onClick={onClose}>
      <div style={{
        background: "#fff", borderRadius: 16, padding: 28, width: 380, maxWidth: "90vw",
        boxShadow: "0 32px 80px rgba(15,118,110,0.18)",
      }} onClick={e => e.stopPropagation()}>
        <div style={{ ...s.sectionTitle, marginBottom: 20, fontSize: 16 }}>Change Password</div>
        {error && <div style={s.alert("error")}>{error}</div>}
        {success && <div style={s.alert("success")}>{success}</div>}
        <form onSubmit={submit}>
          <label style={s.label}>Current password</label>
          <input type="password" style={{ ...s.input, marginBottom: 12 }}
            value={current} onChange={e => setCurrent(e.target.value)} required />
          <label style={s.label}>New password</label>
          <input type="password" style={{ ...s.input, marginBottom: 12 }}
            value={next} onChange={e => setNext(e.target.value)} required minLength={8} />
          <label style={s.label}>Confirm new password</label>
          <input type="password" style={{ ...s.input, marginBottom: 20 }}
            value={confirm} onChange={e => setConfirm(e.target.value)} required minLength={8} />
          <div style={{ display: "flex", gap: 10 }}>
            <button style={{ ...s.btn("primary"), flex: 1 }} type="submit" disabled={saving}>
              {saving ? "Saving..." : "Update password"}
            </button>
            <button style={s.btn("secondary")} type="button" onClick={onClose}>Cancel</button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function App() {
  const [user, setUser] = useState(null);
  const [view, setView] = useState(() => {
    const q = new URLSearchParams(window.location.search);
    const v = q.get("view");
    return v && NAV.some((n) => n.id === v) ? v : "dashboard";
  });
  const [darkMode, setDarkMode] = useState(() => localStorage.getItem("guardrails_dark") === "1");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [showChangePassword, setShowChangePassword] = useState(false);

  useEffect(() => {
    if (getToken()) {
      api("/auth/me").then(setUser).catch(() => clearTokens());
    }
  }, []);

  useEffect(() => {
    localStorage.setItem("guardrails_dark", darkMode ? "1" : "0");
  }, [darkMode]);

  function logout() { clearTokens(); setUser(null); }
  function navigate(id) { setView(id); setSidebarOpen(false); }

  if (!user) return <><GlobalStyles darkMode={darkMode} /><AuthView onAuth={setUser} /></>;

  return (
    <div className="app-shell" style={s.app} data-dark={darkMode ? "1" : "0"}>
      <GlobalStyles darkMode={darkMode} />
      <AuthFlowBackground />

      {/* Mobile overlay */}
      {sidebarOpen && (
        <div style={{ position: "fixed", inset: 0, zIndex: 9, background: "rgba(16,32,51,0.4)" }}
          onClick={() => setSidebarOpen(false)} />
      )}

      {/* Sidebar */}
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
              {darkMode ? "☀" : "◑"}
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

        <div style={{ flex: 1 }} />

        <div style={{ borderTop: "1px solid #e7eef6", paddingTop: 12, marginTop: 12 }}>
          <div style={{ ...s.navItem(false), marginBottom: 4 }} onClick={() => setShowChangePassword(true)}>
            <span style={{ fontSize: 11, fontWeight: 850, color: "#9aabba" }}>pw</span>
            <span>Change password</span>
          </div>
          <div style={s.navItem(false)} onClick={logout}>
            <span style={{ fontSize: 11, fontWeight: 850, color: "#9aabba" }}>--</span>
            <span>Sign out</span>
          </div>
        </div>
      </div>

      {/* Mobile hamburger */}
      <button className="hamburger" onClick={() => setSidebarOpen(o => !o)}
        style={{
          display: "none", position: "fixed", top: 14, left: 14, zIndex: 20,
          background: "#0f766e", color: "#fff", border: "none", borderRadius: 8,
          width: 40, height: 40, fontSize: 18, cursor: "pointer",
          boxShadow: "0 4px 12px rgba(15,118,110,0.3)",
        }}
      >
        ☰
      </button>

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

      {showChangePassword && <ChangePasswordModal onClose={() => setShowChangePassword(false)} />}
    </div>
  );
}
