import type { CSSProperties } from "react";

const navItem = (active: boolean): CSSProperties => ({
    display: "flex", alignItems: "center", gap: 10,
    padding: "11px 12px",
    cursor: "pointer",
    fontSize: 14,
    fontWeight: active ? 750 : 650,
    letterSpacing: 0,
    color: active ? "#0f766e" : "#607086",
    background: active ? "rgba(45, 212, 191, 0.1)" : "transparent",
    border: active ? "1px solid rgba(15, 118, 110, 0.15)" : "1px solid transparent",
    borderRadius: 8,
    transition: "all 0.18s ease",
    userSelect: "none",
    marginBottom: 6,
  });

const badge = (status: string): CSSProperties => {
    const map: Record<string, { bg: string; color: string; border: string }> = {
      delivered:      { bg: "#e8f8ef", color: "#067647", border: "#abe7c6" },
      input_blocked:  { bg: "#fff3e8", color: "#b45309", border: "#fed7aa" },
      output_blocked: { bg: "#fff7df", color: "#99620f", border: "#fde68a" },
      rate_limited:   { bg: "#eff6ff", color: "#1d4ed8", border: "#bfdbfe" },
      error:          { bg: "#fff1f2", color: "#be123c", border: "#fecdd3" },
    };
    const c = map[status] || { bg: "#eef3f8", color: "#405166", border: "#dce7f0" };
    return {
      display: "inline-flex", alignItems: "center", padding: "4px 9px", borderRadius: 999,
      fontSize: 11, fontWeight: 800, letterSpacing: 0,
      background: c.bg, color: c.color, border: `1px solid ${c.border}`,
    };
  };

const btn = (variant = "primary"): CSSProperties => ({
    padding: "10px 16px", borderRadius: 8, border: "1px solid transparent", cursor: "pointer",
    fontSize: 13, fontWeight: 800, letterSpacing: 0,
    fontFamily: "inherit",
    ...(variant === "primary"
      ? { background: "linear-gradient(135deg, #0f766e, #047857)", color: "#fff", boxShadow: "0 10px 22px rgba(15, 118, 110, 0.18)" }
      : variant === "danger"
      ? { background: "#fff1f2", color: "#be123c", border: "1px solid #fecdd3" }
      : { background: "#ffffff", color: "#405166", border: "1px solid #ccd9e6" }),
  });

const toggle = (on: boolean): CSSProperties => ({
    width: 42, height: 24, borderRadius: 999, position: "relative",
    background: on ? "#0f766e" : "#cad6e2", border: "none", cursor: "pointer",
    transition: "background 0.2s", flexShrink: 0,
  });

const toggleDot = (on: boolean): CSSProperties => ({
    position: "absolute", top: 3, left: on ? 21 : 3,
    width: 18, height: 18, borderRadius: "50%", background: "#fff",
    transition: "left 0.2s",
    boxShadow: "0 2px 8px rgba(16,32,51,0.18)",
  });

const chip = (on: boolean): CSSProperties => ({
    padding: "7px 12px", borderRadius: 999, fontSize: 12, cursor: "pointer",
    border: on ? "1px solid #8ddfcf" : "1px solid #dce7f0",
    background: on ? "#e8f8f3" : "#ffffff",
    color: on ? "#0f766e" : "#607086",
    fontWeight: 750,
    userSelect: "none",
  });

const alert = (type: string): CSSProperties => ({
    padding: "13px 15px", borderRadius: 8, fontSize: 13, marginBottom: 16,
    background: type === "error" ? "#fff1f2" : type === "success" ? "#e8f8ef" : "#eff6ff",
    border: `1px solid ${type === "error" ? "#fecdd3" : type === "success" ? "#abe7c6" : "#bfdbfe"}`,
    color: type === "error" ? "#be123c" : type === "success" ? "#067647" : "#1d4ed8",
    lineHeight: 1.5,
  });

const inputStyle: CSSProperties = {
    width: "100%", background: "#ffffff", border: "1px solid #ccd9e6",
    borderRadius: 8, padding: "11px 12px", color: "#102033",
    fontFamily: "inherit", fontSize: 14, outline: "none",
    boxSizing: "border-box",
    boxShadow: "0 1px 0 rgba(15,118,110,0.03)",
  };

const tableStyle: CSSProperties = { width: "100%", borderCollapse: "collapse" };
const thStyle: CSSProperties = { textAlign: "left", padding: "10px 12px", fontSize: 11, color: "#7b8a9d",
    letterSpacing: "0.04em", textTransform: "uppercase", borderBottom: "1px solid #e7eef6", whiteSpace: "nowrap" };
const tdStyle: CSSProperties = { padding: "12px", fontSize: 13, borderBottom: "1px solid #eef3f8", color: "#405166" };

const appStyle: CSSProperties = {
  height: "100vh",
  width: "100vw",
  position: "relative",
  overflow: "hidden",
  background: "transparent",
  color: "#102033",
  fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
  display: "flex",
};
const sidebarStyle: CSSProperties = {
  width: 260,
  position: "relative",
  zIndex: 1,
  background: "rgba(255, 255, 255, 0.9)",
  borderRight: "1px solid rgba(15, 118, 110, 0.15)",
  padding: "22px 14px",
  display: "flex",
  flexDirection: "column",
  flexShrink: 0,
  overflowY: "auto",
  boxShadow: "12px 0 64px rgba(15, 118, 110, 0.12), inset 0 1px 0 rgba(255,255,255,0.5)",
  backdropFilter: "blur(20px)",
};
const mainStyle: CSSProperties = { flex: 1, minWidth: 0, overflow: "auto", padding: 32, maxWidth: 1520, margin: "0 auto", position: "relative", zIndex: 1 };

export const s = {
  app: appStyle,
  sidebar: sidebarStyle,
  logo: {
    padding: "0 10px 20px",
    borderBottom: "1px solid #e7eef6",
    marginBottom: 18,
  },
  logoText: {
    fontSize: 18,
    fontWeight: 800,
    letterSpacing: 0,
    color: "#102033",
  },
  logoSub: { fontSize: 12, color: "#607086", marginTop: 6, overflow: "hidden", textOverflow: "ellipsis" },
  navItem,
  main: mainStyle,
  pageTitle: {
    fontSize: 28, fontWeight: 850, marginBottom: 22,
    color: "#102033", letterSpacing: 0,
  },
  card: {
    background: "rgba(255, 255, 255, 0.9)",
    border: "1px solid rgba(15, 118, 110, 0.15)",
    borderRadius: 16,
    padding: 22,
    boxShadow: "0 24px 64px rgba(15, 118, 110, 0.08), inset 0 1px 0 rgba(255,255,255,0.5)",
    backdropFilter: "blur(20px)",
  },
  statGrid: { display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(185px,1fr))", gap: 16, marginBottom: 24 },
  statCard: {
    background: "rgba(255, 255, 255, 0.9)",
    border: "1px solid rgba(15, 118, 110, 0.15)",
    borderRadius: 16,
    padding: 20,
    boxShadow: "0 16px 42px rgba(15, 118, 110, 0.06), inset 0 1px 0 rgba(255,255,255,0.5)",
    backdropFilter: "blur(20px)",
  },
  statLabel: { fontSize: 12, color: "#607086", letterSpacing: 0, fontWeight: 750 },
  statValue: { fontSize: 32, fontWeight: 850, marginTop: 6, color: "#102033" },
  statSub:   { fontSize: 12, color: "#7b8a9d", marginTop: 4 },
  grid2: { display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(340px,1fr))", gap: 18, marginBottom: 24 },
  sectionTitle: { fontSize: 13, fontWeight: 800, letterSpacing: 0, color: "#27394f",
    marginBottom: 16 },
  table: tableStyle,
  th: thStyle,
  td: tdStyle,
  badge,
  input: inputStyle,
  btn,
  toggle,
  toggleDot,
  chip,
  alert,
  muted: { color: "#7b8a9d", fontSize: 13 },
  label: { fontSize: 12, color: "#607086", fontWeight: 750, marginBottom: 6 },
  heroPanel: {
    background: "linear-gradient(135deg, #ffffff 0%, #ecfdf7 52%, #f0fdf4 100%)",
    border: "1px solid #d3eadf",
    borderRadius: 8,
    padding: 24,
    marginBottom: 24,
    boxShadow: "0 18px 50px rgba(15, 118, 110, 0.08)",
  },
} satisfies Record<string, unknown>;