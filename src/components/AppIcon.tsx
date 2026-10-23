import type { ReactNode, SVGProps } from "react";

export type IconName = "grid" | "sparkles" | "shield" | "chart" | "key" | "logs" | "settings" | "user" | "arrow" | "plus" | "refresh" | "copy" | "check" | "close" | "menu" | "search" | "sun" | "moon" | "chevron" | "external" | "code" | "layers" | "team" | "card" | "activity" | "eye" | "eye-off" | "logout" | "help";

const paths: Record<IconName, ReactNode> = {
  help: <><circle cx="12" cy="12" r="9" /><path d="M9.5 9a2.5 2.5 0 0 1 5 .3c0 1.8-2.5 2-2.5 3.7" /><path d="M12 16.5h.01" /></>,
  grid: <><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>,
  sparkles: <><path d="m12 3 2.4 6.6L21 12l-6.6 2.4L12 21l-2.4-6.6L3 12l6.6-2.4Z" /><path d="m20 3 .5 1.5L22 5l-1.5.5L20 7l-.5-1.5L18 5l1.5-.5Z" /></>,
  shield: <><path d="m12 3 8 3v5c0 5-4 8.5-8 10-4-1.5-8-5-8-10V6Z" /><path d="m8.5 12 2.3 2.3 4.7-4.7" /></>,
  chart: <><path d="M4 3v17h17" /><path d="m7 14 4-4 4 2 5-7" /></>,
  key: <><circle cx="8" cy="8" r="5" /><path d="m11.5 11.5 9 9M16 16l3-3M18 18l3-3" /></>,
  logs: <><rect x="5" y="3" width="14" height="18" rx="2" /><path d="M9 8h6M9 12h6M9 16h4" /></>,
  settings: <><path d="M4 7h16M4 17h16" /><circle cx="9" cy="7" r="3" fill="var(--gr-surface, white)" /><circle cx="15" cy="17" r="3" fill="var(--gr-surface, white)" /></>,
  user: <><circle cx="12" cy="8" r="4" /><path d="M4 21v-2a8 8 0 0 1 16 0v2" /></>,
  arrow: <path d="M4 12h16m-6-6 6 6-6 6" />,
  plus: <path d="M12 5v14M5 12h14" />,
  refresh: <><path d="M20 7v5h-5M4 17v-5h5" /><path d="M5 8a8 8 0 0 1 13-3l2 2M19 16a8 8 0 0 1-13 3l-2-2" /></>,
  copy: <><rect x="8" y="8" width="13" height="13" rx="2" /><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3" /></>,
  check: <path d="m5 12 4 4L19 6" />,
  close: <path d="m6 6 12 12M6 18 18 6" />,
  menu: <path d="M4 6h16M4 12h16M4 18h16" />,
  search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></>,
  sun: <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M2 12h2M20 12h2m-3-9-1.5 1.5M5.5 18.5 4 20m0-16 1.5 1.5M18.5 18.5 20 20" /></>,
  moon: <path d="M20.5 13a8.5 8.5 0 0 1-9.5-9.5A8.5 8.5 0 1 0 20.5 13Z" />,
  chevron: <path d="m9 5 7 7-7 7" />,
  external: <><path d="M14 3h7v7m0-7L11 13" /><path d="M10 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-5" /></>,
  code: <><path d="m7 6-6 6 6 6m10-12 6 6-6 6M14 3l-4 18" /></>,
  layers: <><path d="m12 3 10 5-10 5L2 8Zm-10 9 10 5 10-5M2 16l10 5 10-5" /></>,
  team: <><circle cx="9" cy="8" r="3" /><path d="M2 21v-2a7 7 0 0 1 14 0v2M16 5a3 3 0 0 1 0 6m2 4a6 6 0 0 1 4 6" /></>,
  card: <><rect x="3" y="5" width="18" height="14" rx="2" /><path d="M3 10h18M7 15h3" /></>,
  activity: <path d="M2 12h4l3-8 6 16 3-8h4" />,
  eye: <><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" /><circle cx="12" cy="12" r="3" /></>,
  "eye-off": <><path d="m3 3 18 18M9.5 5.3A12 12 0 0 1 12 5c6.5 0 10 7 10 7a18 18 0 0 1-3 4M6 6a18 18 0 0 0-4 6s3.5 7 10 7a12 12 0 0 0 6-1.8M10 10a3 3 0 0 0 4 4" /></>,
  logout: <><path d="M9 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h4M9 12h12m-5-5 5 5-5 5" /></>,
};

export default function AppIcon({ name, size = 18, ...props }: SVGProps<SVGSVGElement> & { name: IconName; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false" {...props}>{paths[name]}</svg>;
}
