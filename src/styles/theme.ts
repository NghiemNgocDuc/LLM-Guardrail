import type { CSSProperties } from "react";

const badge = (status: string): CSSProperties => {
  const colors: Record<string, [string, string]> = {
    delivered: ["var(--gr-accent-soft)", "var(--gr-accent)"],
    input_blocked: ["var(--gr-warning-soft)", "var(--gr-warning)"],
    output_blocked: ["var(--gr-warning-soft)", "var(--gr-warning)"],
    rate_limited: ["var(--gr-info-soft)", "var(--gr-info)"],
    error: ["var(--gr-danger-soft)", "var(--gr-danger)"],
  };
  const [background, color] = colors[status] || ["var(--gr-subtle)", "var(--gr-muted)"];
  return { display: "inline-flex", alignItems: "center", gap: 5, padding: "4px 9px", borderRadius: 6,
    fontSize: 11, fontWeight: 600, lineHeight: 1.4, background, color, border: "1px solid transparent" };
};

const btn = (variant = "primary"): CSSProperties => ({
  display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 8,
  minHeight: 40, padding: "10px 16px", borderRadius: 8, cursor: "pointer",
  fontSize: 13, fontWeight: 600, fontFamily: "inherit", lineHeight: 1.35,
  border: "1px solid var(--gr-border)",
  ...(variant === "primary" ? { background: "var(--gr-accent)", color: "var(--gr-on-accent)", borderColor: "var(--gr-accent)" }
    : variant === "danger" ? { background: "var(--gr-danger-soft)", color: "var(--gr-danger)", borderColor: "var(--gr-danger-border)" }
    : { background: "var(--gr-surface)", color: "var(--gr-ink)" }),
});

const card: CSSProperties = { background: "var(--gr-surface)", border: "1px solid var(--gr-border)", borderRadius: 12, padding: 24 };
const input: CSSProperties = { width: "100%", minHeight: 44, background: "var(--gr-surface)", border: "1px solid var(--gr-input-border)",
  borderRadius: 8, padding: "11px 13px", color: "var(--gr-ink)", fontFamily: "inherit", fontSize: 14, boxSizing: "border-box" };

export const s = {
  app: { height: "100dvh", width: "100%", overflow: "hidden", background: "var(--gr-bg)", color: "var(--gr-ink)", fontFamily: "var(--gr-font)", display: "flex" },
  sidebar: { width: 248, background: "var(--gr-sidebar)", borderRight: "1px solid var(--gr-border)", display: "flex", flexDirection: "column", flexShrink: 0 },
  logo: { padding: "22px 20px", marginBottom: 12 },
  logoText: { fontSize: 18, fontWeight: 650, letterSpacing: "-.035em", color: "var(--gr-ink)" },
  logoSub: { fontSize: 12, color: "var(--gr-muted)", marginTop: 6, overflow: "hidden", textOverflow: "ellipsis" },
  navItem: (active: boolean): CSSProperties => ({ display: "flex", alignItems: "center", gap: 10, padding: "10px 12px", minHeight: 42,
    cursor: "pointer", fontSize: 13, fontWeight: active ? 600 : 450, color: active ? "var(--gr-accent)" : "var(--gr-muted)",
    background: active ? "var(--gr-accent-soft)" : "transparent", border: "none", borderRadius: 7 }),
  main: { flex: 1, minWidth: 0, overflow: "auto", padding: 32, position: "relative" },
  pageTitle: { fontSize: 28, fontWeight: 600, marginBottom: 24, color: "var(--gr-ink)", letterSpacing: "-.04em", lineHeight: 1.2 },
  card,
  statGrid: { display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(185px,1fr))", gap: 16, marginBottom: 24 },
  statCard: { ...card, padding: 22 },
  statLabel: { fontSize: 12, color: "var(--gr-muted)", fontWeight: 500 },
  statValue: { fontSize: 34, fontWeight: 550, marginTop: 12, color: "var(--gr-ink)", letterSpacing: "-.04em", fontVariantNumeric: "tabular-nums" },
  statSub: { fontSize: 12, color: "var(--gr-muted)", marginTop: 6 },
  grid2: { display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(min(100%,340px),1fr))", gap: 20, marginBottom: 24 },
  sectionTitle: { fontSize: 14, fontWeight: 600, color: "var(--gr-ink)", marginBottom: 18 },
  table: { width: "100%", borderCollapse: "collapse", textAlign: "left" },
  th: { textAlign: "left", padding: "12px 14px", fontSize: 11, color: "var(--gr-muted)", fontWeight: 600,
    letterSpacing: ".05em", textTransform: "uppercase", borderBottom: "1px solid var(--gr-border)", whiteSpace: "nowrap" },
  td: { padding: "14px", fontSize: 13, borderBottom: "1px solid var(--gr-border)", color: "var(--gr-ink)", lineHeight: 1.5 },
  badge, input, btn,
  toggle: (on: boolean): CSSProperties => ({ width: 42, height: 24, borderRadius: 999, position: "relative",
    background: on ? "var(--gr-accent)" : "var(--gr-input-border)", border: "none", cursor: "pointer", flexShrink: 0 }),
  toggleDot: (on: boolean): CSSProperties => ({ position: "absolute", top: 3, left: on ? 21 : 3,
    width: 18, height: 18, borderRadius: "50%", background: "#fff", transition: "left .18s ease" }),
  chip: (on: boolean): CSSProperties => ({ display: "inline-flex", padding: "8px 12px", minHeight: 36, alignItems: "center", borderRadius: 7, fontSize: 12,
    cursor: "pointer", border: on ? "1px solid var(--gr-accent)" : "1px solid var(--gr-border)", background: on ? "var(--gr-accent-soft)" : "var(--gr-surface)",
    color: on ? "var(--gr-accent)" : "var(--gr-muted)", fontWeight: 500 }),
  alert: (type: string): CSSProperties => ({ padding: "14px 16px", borderRadius: 8, fontSize: 13, marginBottom: 16, lineHeight: 1.55,
    background: type === "error" ? "var(--gr-danger-soft)" : type === "success" ? "var(--gr-accent-soft)" : "var(--gr-info-soft)",
    color: type === "error" ? "var(--gr-danger)" : type === "success" ? "var(--gr-accent)" : "var(--gr-info)", border: "1px solid var(--gr-border)" }),
  muted: { color: "var(--gr-muted)", fontSize: 13 },
  label: { display: "block", fontSize: 12, color: "var(--gr-muted)", fontWeight: 550, marginBottom: 8 },
  heroPanel: { ...card, background: "var(--gr-accent-soft)", padding: 28, marginBottom: 24 },
} satisfies Record<string, CSSProperties | ((...args: any[]) => CSSProperties)>;
