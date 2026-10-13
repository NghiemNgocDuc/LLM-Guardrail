import { Component, lazy, Suspense, useEffect, useRef, useState } from "react";
import type { Dispatch, MouseEvent, ReactNode, SetStateAction } from "react";
import { api, clearTokens, getToken } from "./utils/api";
import { identifyUser } from "./utils/analytics";
import type { components } from "./api-types";
import GlobalStyles from "./styles/GlobalStyles";
import AppIcon from "./components/AppIcon";
import type { IconName } from "./components/AppIcon";
import AuthView from "./views/AuthView";

const DashboardView = lazy(() => import("./views/DashboardView"));
const ChatView = lazy(() => import("./views/ChatView"));
const MemoryView = lazy(() => import("./views/MemoryView"));
const SkillGuardView = lazy(() => import("./views/SkillGuardView"));
const BillingView = lazy(() => import("./views/BillingView"));
const LogsView = lazy(() => import("./views/LogsView"));
const ApiKeysView = lazy(() => import("./views/ApiKeysView"));
const PolicyView = lazy(() => import("./views/PolicyView"));
const AdminView = lazy(() => import("./views/AdminView"));
const TeamView = lazy(() => import("./views/TeamView"));
const TeamsHubView = lazy(() => import("./views/TeamsHubView"));
const AnalyticsView = lazy(() => import("./views/AnalyticsView"));
const ProfileView = lazy(() => import("./views/ProfileView"));
const HealthView = lazy(() => import("./views/HealthView"));
const MandateFlowView = lazy(() => import("./views/MandateFlowView"));
const SettingsView = lazy(() => import("./views/SettingsView"));
const AboutView = lazy(() => import("./views/AboutView"));
type UserOut = components["schemas"]["UserOut"];
type NavItem = { id: string; label: string; icon: IconName; group: string; adminOnly?: boolean };
const NAV: NavItem[] = [
  { id: "dashboard", label: "Overview", icon: "grid", group: "Workspace" },
  { id: "chat", label: "LLM Playground", icon: "sparkles", group: "Workspace" },
  { id: "skills", label: "Skill Guard", icon: "shield", group: "Workspace" },
  { id: "memory", label: "Memory", icon: "layers", group: "Workspace" },
  { id: "mandate", label: "MandateFlow", icon: "code", group: "Workspace" },
  { id: "analytics", label: "Analytics", icon: "chart", group: "Observe" },
  { id: "logs", label: "Request logs", icon: "logs", group: "Observe" },
  { id: "health", label: "System health", icon: "activity", group: "Observe" },
  { id: "keys", label: "API keys", icon: "key", group: "Manage" },
  { id: "policy", label: "Policies", icon: "settings", group: "Manage" },
  { id: "teams", label: "Teams", icon: "team", group: "Manage" },
  { id: "billing", label: "Usage & billing", icon: "card", group: "Manage" },
  { id: "admin", label: "Administration", icon: "shield", group: "Manage", adminOnly: true },
  { id: "settings", label: "Settings", icon: "settings", group: "Resources" },
  { id: "about", label: "About the project", icon: "code", group: "Resources" },
];
const validViews = new Set([...NAV.map(item => item.id), "profile", "team"]);
function readView() {
  const view = new URLSearchParams(window.location.search).get("view");
  return view && validViews.has(view) ? view : "dashboard";
}
function LoadingWorkspace({ page = false }: { page?: boolean }) {
  return <div className={page ? "workspace-loading" : "workspace-view-loading"} role="status">
    <div className="workspace-loading-inner"><span className="workspace-spinner" aria-hidden="true" />Loading {page ? "your workspace" : "view"}…</div>
  </div>;
}
type GateContext = { user: UserOut; setUser: Dispatch<SetStateAction<UserOut | null>>; signOut: () => void };
class ViewBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (!this.state.failed) return this.props.children;
    return <section className="workspace-view-error" role="alert"><AppIcon name="activity" size={28} /><h1>This view couldn't load.</h1><p>Reload the page to try again, or open another view from the sidebar.</p><button type="button" onClick={() => window.location.reload()}>Reload page<AppIcon name="refresh" size={16} /></button></section>;
  }
}
function LocalAuthGate({ children }: { children: (ctx: GateContext) => ReactNode }) {
  const authLink = Boolean(new URLSearchParams(window.location.search).get("token")) && /\/(verify-email|reset-password)\/?$/.test(window.location.pathname);
  const [user, setUser] = useState<UserOut | null>(null);
  const [checking, setChecking] = useState(Boolean(getToken()) && !authLink);
  useEffect(() => {
    if (!getToken() || authLink) return;
    let active = true;
    api<UserOut>("/auth/me").then(value => { if (active) { identifyUser(value); setUser(value); } })
      .catch(() => { if (active) { clearTokens(); identifyUser(null); } }).finally(() => { if (active) setChecking(false); });
    return () => { active = false; };
  }, [authLink]);
  if (checking) return <LoadingWorkspace page />;
  if (authLink || !user) return <AuthView onAuth={value => { setUser(value); identifyUser(value); }} />;
  return children({ user, setUser, signOut: () => { clearTokens(); identifyUser(null); setUser(null); } });
}
function WorkspaceShell({ user, setUser, signOut }: GateContext) {
  const [view, setView] = useState(() => readView() === "admin" && !user.is_admin ? "dashboard" : readView());
  const [darkMode, setDarkMode] = useState(() => localStorage.getItem("guardrails_dark") === "1");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [mobile, setMobile] = useState(() => window.matchMedia("(max-width: 850px)").matches);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(0);
  const commandRef = useRef<HTMLDialogElement>(null);
  const commandInput = useRef<HTMLInputElement>(null);
  const sidebarRef = useRef<HTMLElement>(null);
  const contentRef = useRef<HTMLElement>(null);
  const items = NAV.filter(item => !item.adminOnly || user.is_admin);
  const results = items.filter(item => (item.label + " " + item.group).toLowerCase().includes(query.toLowerCase()));
  const current = NAV.find(item => item.id === view);
  const pageLabel = current?.label || (view === "profile" ? "Your profile" : "Team details");
  useEffect(() => { localStorage.setItem("guardrails_dark", darkMode ? "1" : "0"); }, [darkMode]);
  useEffect(() => {
    const sync = () => { setView(readView() === "admin" && !user.is_admin ? "dashboard" : readView()); setSidebarOpen(false); commandRef.current?.close(); };
    window.addEventListener("popstate", sync); return () => window.removeEventListener("popstate", sync);
  }, [user.is_admin]);
  useEffect(() => {
    const media = window.matchMedia("(max-width: 850px)");
    const update = () => { setMobile(media.matches); if (!media.matches) setSidebarOpen(false); };
    media.addEventListener("change", update); return () => media.removeEventListener("change", update);
  }, []);
  useEffect(() => {
    document.title = pageLabel + " · LLM Guardrail";
    contentRef.current?.scrollTo({ top: 0 });
    const frame = window.requestAnimationFrame(() => contentRef.current?.focus({ preventScroll: true }));
    return () => window.cancelAnimationFrame(frame);
  }, [view, pageLabel]);
  useEffect(() => {
    if (commandRef.current?.open && results[selected]) document.getElementById("workspace-page-" + results[selected].id)?.scrollIntoView({ block: "nearest" });
  }, [selected, query]);
  useEffect(() => {
    const listener = (event: KeyboardEvent) => { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); setSidebarOpen(false); openCommand(); } };
    window.addEventListener("keydown", listener); return () => window.removeEventListener("keydown", listener);
  }, []);
  useEffect(() => {
    if (!sidebarOpen || !mobile) return;
    const previous = document.activeElement as HTMLElement | null;
    sidebarRef.current?.querySelector<HTMLButtonElement>(".workspace-mobile-close")?.focus();
    const trap = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); setSidebarOpen(false); return; }
      if (event.key !== "Tab") return;
      const nodes = sidebarRef.current?.querySelectorAll<HTMLElement>("a[href], button:not([disabled])");
      if (!nodes?.length) return;
      const first = nodes[0], last = nodes[nodes.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    window.addEventListener("keydown", trap); return () => { window.removeEventListener("keydown", trap); previous?.focus(); };
  }, [sidebarOpen, mobile]);
  function navigate(id: string) {
    if (!validViews.has(id) || id === "admin" && !user.is_admin) return;
    setView(id); setSidebarOpen(false); commandRef.current?.close();
    const url = new URL(window.location.href); url.searchParams.set("view", id);
    if (url.href !== window.location.href) window.history.pushState({}, "", url);
  }
  function navClick(event: MouseEvent<HTMLAnchorElement>, id: string) {
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault(); navigate(id);
  }
  function contentClick(event: MouseEvent<HTMLElement>) {
    if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || !(event.target instanceof Element)) return;
    const anchor = event.target.closest<HTMLAnchorElement>("a[href]");
    if (!anchor || anchor.target || anchor.hasAttribute("download")) return;
    const url = new URL(anchor.href), id = url.searchParams.get("view");
    if (url.origin === window.location.origin && url.pathname === window.location.pathname && id && validViews.has(id)) { event.preventDefault(); navigate(id); }
  }
  function openCommand() { setQuery(""); setSelected(0); if (!commandRef.current?.open) commandRef.current?.showModal(); commandInput.current?.focus(); }
  const displayName = user.full_name || user.email.split("@")[0];
  const initials = displayName.split(/\s+/).slice(0, 2).map(word => word[0]).join("").toUpperCase();
  function renderView() {
    switch (view) {
      case "chat": return <ChatView />;
      case "memory": return <MemoryView />;
      case "mandate": return <MandateFlowView />;
      case "skills": return <SkillGuardView />;
      case "analytics": return <AnalyticsView />;
      case "billing": return <BillingView />;
      case "logs": return <LogsView />;
      case "keys": return <ApiKeysView />;
      case "policy": return <PolicyView user={user} />;
      case "teams": return <TeamsHubView user={user} onSwitch={async () => { try { setUser(await api<UserOut>("/auth/me")); } catch {} navigate("team"); }} onBack={() => navigate("team")} />;
      case "team": return <div><button onClick={() => navigate("teams")} className="workspace-back-button"><AppIcon name="chevron" size={14} style={{ transform: "rotate(180deg)" }} />All teams</button><TeamView user={user} /></div>;
      case "health": return <HealthView />;
      case "about": return <AboutView />;
      case "profile": return <ProfileView user={user} onUserUpdate={setUser} />;
      case "admin": return user.is_admin ? <AdminView /> : <DashboardView />;
      case "settings": return <SettingsView user={user} onUserUpdate={setUser} darkMode={darkMode} setDarkMode={setDarkMode} onLogout={signOut} />;
      default: return <DashboardView />;
    }
  }
  return <div className="app-shell" data-dark={darkMode ? "1" : "0"}>
    <a className="skip-link" href="#workspace-main">Skip to content</a>
    {sidebarOpen && mobile && <button type="button" className="workspace-scrim" aria-label="Close navigation" onClick={() => setSidebarOpen(false)} />}
    <aside ref={sidebarRef} className={"app-sidebar" + (sidebarOpen ? " sidebar-open" : "")} inert={mobile && !sidebarOpen ? true : undefined} role={mobile && sidebarOpen ? "dialog" : undefined} aria-modal={mobile && sidebarOpen ? true : undefined} aria-label="Workspace navigation" id="workspace-navigation">
      <div className="workspace-brand-row"><a className="workspace-brand" href="?view=dashboard" onClick={event => navClick(event, "dashboard")}><span className="workspace-brand-mark"><AppIcon name="shield" size={21} /></span>LLM Guardrail</a>
        <button type="button" className="workspace-icon-button workspace-mobile-close" onClick={() => setSidebarOpen(false)} aria-label="Close navigation"><AppIcon name="close" /></button></div>
      <button type="button" className="workspace-switch" onClick={() => navigate("teams")}><span className="workspace-avatar"><AppIcon name="layers" size={15} /></span><span className="workspace-switch-copy"><strong>Your workspace</strong><span>{user.is_admin ? "Administrator" : "Member"}</span></span><AppIcon name="chevron" size={13} /></button>
      <nav className="workspace-nav" aria-label="Main navigation">{["Workspace", "Observe", "Manage", "Resources"].map(group => <div className="workspace-nav-group" key={group}>
        <p className="workspace-nav-heading">{group}</p>{items.filter(item => item.group === group).map(item => <a key={item.id} className="workspace-nav-link" href={"?view=" + item.id} onClick={event => navClick(event, item.id)} aria-current={view === item.id || item.id === "teams" && view === "team" ? "page" : undefined}><AppIcon name={item.icon} size={17} /><span>{item.label}</span></a>)}</div>)}</nav>
      <div className="workspace-sidebar-footer"><button type="button" className="workspace-account" onClick={() => navigate("profile")} aria-label="Open your profile"><span className="workspace-avatar">{initials}</span><span className="workspace-account-copy"><strong>{displayName}</strong><span title={user.email}>{user.email}</span></span><AppIcon name="chevron" size={14} /></button></div>
    </aside>
    <div className="workspace-area" inert={mobile && sidebarOpen ? true : undefined}><header className="workspace-topbar">
      <div className="workspace-breadcrumb"><button type="button" className="workspace-icon-button workspace-menu-button" onClick={() => setSidebarOpen(true)} aria-label="Open navigation" aria-expanded={sidebarOpen} aria-controls="workspace-navigation"><AppIcon name="menu" size={20} /></button><span>{current?.group || "Workspace"}</span><AppIcon name="chevron" size={12} /><strong>{pageLabel}</strong></div>
      <div className="workspace-header-actions"><button type="button" className="workspace-search-trigger" onClick={openCommand} aria-label="Jump to a page"><AppIcon name="search" size={15} /><span>Jump to…</span><kbd>Ctrl K</kbd></button><button type="button" className="workspace-icon-button" aria-label={darkMode ? "Switch to light theme" : "Switch to dark theme"} onClick={() => setDarkMode(value => !value)}><AppIcon name={darkMode ? "sun" : "moon"} size={17} /></button><button type="button" className="workspace-icon-button" aria-label="Sign out" onClick={signOut}><AppIcon name="logout" size={17} /></button></div>
    </header><main className="workspace-content" id="workspace-main" ref={contentRef} tabIndex={-1} aria-label={pageLabel} onClick={contentClick}><ViewBoundary key={view}><Suspense fallback={<LoadingWorkspace />}>{renderView()}</Suspense></ViewBoundary></main></div>
    <dialog className="workspace-command" ref={commandRef} aria-label="Jump to a page" onClick={event => { if (event.target === event.currentTarget) commandRef.current?.close(); }}>
      <div className="workspace-command-header"><AppIcon name="search" /><input ref={commandInput} value={query} onChange={event => { setQuery(event.target.value); setSelected(0); }} placeholder="Find a page…" aria-label="Search pages" role="combobox" aria-autocomplete="list" aria-expanded="true" aria-controls="workspace-page-results" aria-activedescendant={results[selected] ? "workspace-page-" + results[selected].id : undefined} onKeyDown={event => {
        if (event.key === "ArrowDown") { event.preventDefault(); setSelected(value => Math.min(value + 1, Math.max(0, results.length - 1))); }
        else if (event.key === "ArrowUp") { event.preventDefault(); setSelected(value => Math.max(value - 1, 0)); }
        else if (event.key === "Enter" && results[selected]) { event.preventDefault(); navigate(results[selected].id); }
      }} /><button type="button" className="workspace-icon-button" aria-label="Close quick navigation" onClick={() => commandRef.current?.close()}><AppIcon name="close" /></button></div>
      <div className="workspace-command-results" id="workspace-page-results" role="listbox" aria-label="Pages">{results.length ? results.map((item, index) => <button type="button" key={item.id} id={"workspace-page-" + item.id} role="option" aria-selected={selected === index} tabIndex={-1} data-selected={selected === index} onClick={() => navigate(item.id)}><AppIcon name={item.icon} /><span>{item.label}</span><AppIcon name="arrow" size={14} /></button>) : <p role="status">No matching pages. Try “logs” or “policy”.</p>}</div>
      <div className="workspace-command-footer">↑ ↓ to move · Enter to open · Esc to close</div>
    </dialog>
  </div>;
}
export default function App() { return <><GlobalStyles /><LocalAuthGate>{context => <WorkspaceShell {...context} />}</LocalAuthGate></>; }
