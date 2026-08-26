import React from 'react';
export default function GlobalStyles({ darkMode }: { darkMode?: boolean }) {
  return (
    <style>{`
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

      * { box-sizing: border-box; }
      body { margin: 0; background: #f8fbff; font-family: Inter, ui-sans-serif, system-ui, -apple-system, sans-serif; }
      button, input, textarea, select { transition: box-shadow .18s ease, border-color .18s ease, transform .18s ease; }
      button:hover:not(:disabled) { transform: translateY(-1px); }
      button:disabled { opacity: .58; cursor: not-allowed; }
      input:focus, textarea:focus, select:focus { border-color: #0f766e !important; box-shadow: 0 0 0 3px rgba(15,118,110,.12) !important; }
      .auth-password-toggle:hover { color: #2dd4bf; background: rgba(45, 212, 191, 0.1); }
      .auth-password-toggle:focus-visible { outline: 2px solid #2dd4bf; outline-offset: 2px; }
      tr:last-child td { border-bottom: none !important; }

      /* ----- Sidebar scroll ----- */
      .app-sidebar { scrollbar-width: thin; scrollbar-color: rgba(15,118,110,0.18) transparent; }
      .app-sidebar::-webkit-scrollbar { width: 4px; }
      .app-sidebar::-webkit-scrollbar-thumb { background: rgba(15,118,110,0.18); border-radius: 4px; }
      .app-sidebar::-webkit-scrollbar-track { background: transparent; }

      /* ----- Mobile layout ----- */
      @media (max-width: 760px) {
        .app-shell { flex-direction: row; }
        .app-sidebar {
          position: fixed !important; top: 0; left: 0; bottom: 0;
          z-index: 10; width: 260px !important;
          transform: translateX(-100%);
          transition: transform 0.25s ease;
        }
        .app-sidebar.sidebar-open { transform: translateX(0); }
        .app-main { padding: 18px 16px 18px 16px !important; margin-top: 0 !important; }
        .hamburger { display: flex !important; align-items: center; justify-content: center; }
      }
      @media (min-width: 761px) {
        .hamburger { display: none !important; }
      }

      /* ----- Dark mode ----- */
      ${darkMode ? `
        body { background: #0c1824; }
        .app-shell { background: #0c1824; }
        .app-sidebar {
          background: rgba(16,28,42,0.97) !important;
          border-right-color: rgba(45,212,191,0.12) !important;
        }
        .app-main { background: transparent; color: #cbd5e1; }
        /* cards, stat cards */
        [style*="rgba(255, 255, 255, 0.9)"] {
          background: rgba(20,34,50,0.95) !important;
          border-color: rgba(45,212,191,0.12) !important;
          color: #cbd5e1;
        }
        input, textarea, select {
          background: #142232 !important;
          border-color: #2a3f56 !important;
          color: #cbd5e1 !important;
        }
        table td { border-bottom-color: #1e3347 !important; color: #94a3b8 !important; }
        table th { color: #607086 !important; border-bottom-color: #1e3347 !important; }
      ` : ""}


      /* ----- Auth page cursor ----- */
      .auth-cursor {
        display: inline-block;
        margin-left: 2px;
        color: #818cf8;
        animation: authBlink 1s step-end infinite;
      }
      @keyframes authBlink { 50% { opacity: 0; } }
      @keyframes authFadeIn {
        from { opacity: 0; transform: translateY(12px); }
        to { opacity: 1; transform: translateY(0); }
      }
      @keyframes authFadeInScale {
        from { opacity: 0; transform: translateY(8px) scale(0.97); }
        to { opacity: 1; transform: translateY(0) scale(1); }
      }
      @keyframes authSlideUp {
        from { opacity: 0; transform: translateY(20px); }
        to { opacity: 1; transform: translateY(0); }
      }

      /* ----- Auth Hero Background ----- */
      .auth-hero-bg {
        position: absolute;
        inset: 0;
        z-index: 0;
        pointer-events: none;
        overflow: hidden;
        background: radial-gradient(ellipse 120% 80% at 20% 30%, #ecfdf5 0%, #f8fafc 100%);
      }
      .auth-hero-noise {
        position: absolute;
        inset: 0;
        opacity: 0.05;
        background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
        background-size: 128px 128px;
      }
      .auth-hero-orb {
        position: absolute;
        border-radius: 50%;
        filter: blur(100px);
        will-change: transform;
      }
      .auth-hero-orb-1 {
        width: 500px; height: 500px;
        background: radial-gradient(circle, rgba(45, 212, 191, 0.45) 0%, transparent 70%);
        top: -15%; left: -10%;
        animation: authOrbDrift1 24s ease-in-out infinite;
      }
      .auth-hero-orb-2 {
        width: 600px; height: 600px;
        background: radial-gradient(circle, rgba(16, 185, 129, 0.3) 0%, transparent 70%);
        bottom: -20%; right: -12%;
        animation: authOrbDrift2 28s ease-in-out infinite;
      }
      .auth-hero-orb-3 {
        width: 400px; height: 400px;
        background: radial-gradient(circle, rgba(20, 184, 166, 0.35) 0%, transparent 70%);
        top: 50%; left: 50%;
        animation: authOrbDrift3 22s ease-in-out infinite;
      }
      .auth-hero-orb-4 {
        width: 300px; height: 300px;
        background: radial-gradient(circle, rgba(52, 211, 153, 0.3) 0%, transparent 70%);
        top: 10%; right: 20%;
        animation: authOrbDrift1 20s ease-in-out infinite reverse;
      }
      @keyframes authOrbDrift1 {
        0%, 100% { transform: translate(0, 0) scale(1); }
        50% { transform: translate(60px, 40px) scale(1.06); }
      }
      @keyframes authOrbDrift2 {
        0%, 100% { transform: translate(0, 0) scale(1); }
        50% { transform: translate(-50px, -40px) scale(1.08); }
      }
      @keyframes authOrbDrift3 {
        0%, 100% { transform: translate(-50%, -50%) scale(1); }
        50% { transform: translate(calc(-50% + 30px), calc(-50% - 20px)) scale(0.94); }
      }
      .auth-hero-svg {
        position: absolute;
        inset: -10%;
        width: 120%; height: 120%;
        opacity: 0.4;
      }
      .auth-hero-path {
        fill: none;
        stroke-width: 1.5;
        stroke-linecap: round;
        stroke-dasharray: 8 16;
        animation: authPathFlow 24s linear infinite;
      }
      .auth-hero-path-1 { stroke: rgba(15, 118, 110, 0.3); animation-duration: 30s; }
      .auth-hero-path-2 { stroke: rgba(4, 120, 87, 0.2); animation-duration: 24s; animation-direction: reverse; }
      .auth-hero-path-3 { stroke: rgba(20, 184, 166, 0.25); animation-duration: 36s; }
      @keyframes authPathFlow {
        from { stroke-dashoffset: 0; }
        to { stroke-dashoffset: -600; }
      }
      .auth-hero-grid {
        position: absolute;
        inset: 0;
        background-image:
          linear-gradient(rgba(15, 118, 110, 0.05) 1px, transparent 1px),
          linear-gradient(90deg, rgba(15, 118, 110, 0.05) 1px, transparent 1px);
        background-size: 56px 56px;
        -webkit-mask: radial-gradient(ellipse 70% 60% at 40% 45%, black 10%, transparent 70%);
        mask: radial-gradient(ellipse 70% 60% at 40% 45%, black 10%, transparent 70%);
      }
      .auth-hero-glow {
        position: absolute;
        top: 30%; left: 25%;
        width: 50%; height: 40%;
        background: radial-gradient(ellipse, rgba(45, 212, 191, 0.15) 0%, transparent 70%);
        filter: blur(60px);
      }

      /* ----- Auth Intro Panel ----- */
      .auth-intro-panel {
        color: #0f172a;
      }
      .auth-hero-badge {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 6px 14px;
        border-radius: 999px;
        background: rgba(15, 118, 110, 0.08);
        border: 1px solid rgba(15, 118, 110, 0.2);
        color: #0f766e;
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 0.02em;
        margin-bottom: 20px;
        animation: authFadeIn 0.5s ease forwards;
      }
      .auth-hero-badge-dot {
        width: 6px; height: 6px;
        border-radius: 50%;
        background: #10b981;
        box-shadow: 0 0 8px rgba(16, 185, 129, 0.6);
        animation: authBadgePulse 2s ease-in-out infinite;
      }
      @keyframes authBadgePulse {
        0%, 100% { opacity: 1; box-shadow: 0 0 8px rgba(16, 185, 129, 0.6); }
        50% { opacity: 0.6; box-shadow: 0 0 16px rgba(16, 185, 129, 0.8); }
      }
      .auth-hero-headline {
        margin: 0 0 16px;
        font-size: clamp(32px, 4.5vw, 52px);
        line-height: 1.1;
        font-weight: 800;
        color: #0f172a;
        letter-spacing: -0.03em;
        animation: authSlideUp 0.6s ease forwards;
      }
      .auth-hero-headline-gradient {
        background: linear-gradient(135deg, #0f766e 0%, #047857 50%, #0369a1 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
      }
      .auth-hero-subhead {
        margin: 0 0 28px;
        font-size: 16px;
        line-height: 1.7;
        color: #475569;
        max-width: 520px;
        animation: authSlideUp 0.7s ease forwards;
      }

      /* ----- Auth Metrics ----- */
      .auth-metrics-row {
        display: flex;
        gap: 24px;
        margin-bottom: 28px;
        animation: authFadeIn 0.5s ease forwards;
      }
      .auth-metric-item {
        padding: 12px 0;
      }
      .auth-metric-value {
        font-size: 28px;
        font-weight: 800;
        color: #0f172a;
        letter-spacing: -0.02em;
        font-variant-numeric: tabular-nums;
      }
      .auth-metric-label {
        font-size: 11px;
        font-weight: 700;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin-top: 2px;
      }

      /* ----- Auth Terminal ----- */
      .auth-terminal {
        background: rgba(255, 255, 255, 0.8);
        border: 1px solid rgba(15, 118, 110, 0.15);
        backdrop-filter: blur(24px);
        border-radius: 14px;
        overflow: hidden;
        box-shadow: 0 24px 80px rgba(15, 118, 110, 0.1);
        margin-bottom: 24px;
        animation: authFadeInScale 0.8s ease forwards;
      }
      .auth-terminal-bar {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 12px 16px;
        background: rgba(248, 250, 252, 0.9);
        border-bottom: 1px solid rgba(15, 118, 110, 0.1);
      }
      .auth-terminal-dot {
        width: 10px; height: 10px;
        border-radius: 50%;
        display: inline-block;
      }
      .auth-terminal-title {
        margin-left: 8px;
        font-size: 11px;
        color: #64748b;
        font-weight: 700;
      }
      .auth-terminal-body {
        padding: 20px 22px 24px;
        min-height: 140px;
      }

      /* ----- Auth Chat Bubbles ----- */
      .auth-chat-bubble {
        display: flex;
        gap: 12px;
        margin-bottom: 16px;
      }
      .auth-chat-bubble:last-child { margin-bottom: 0; }
      .auth-chat-avatar {
        flex-shrink: 0;
        width: 30px; height: 30px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 11px;
        font-weight: 800;
      }
      .auth-chat-avatar-user {
        background: #f1f5f9;
        color: #64748b;
        border: 1px solid #e2e8f0;
      }
      .auth-chat-avatar-ai {
        background: linear-gradient(135deg, #0f766e, #10b981);
        color: #fff;
        font-size: 10px;
        box-shadow: 0 4px 12px rgba(15, 118, 110, 0.3);
      }
      .auth-chat-content {
        flex: 1;
        font-size: 13px;
        line-height: 1.6;
      }
      .auth-chat-content-user {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        padding: 10px 14px;
        border-radius: 12px;
        border-top-left-radius: 2px;
        color: #334155;
      }
      .auth-chat-content-ai {
        color: #475569;
        padding-top: 4px;
      }
      .auth-thinking {
        color: #94a3b8;
        font-style: italic;
        animation: authBlink 1.5s infinite;
      }

      /* ----- Auth Feature Cards ----- */
      .auth-features-grid {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 12px;
        margin-bottom: 24px;
      }
      .auth-feature-card {
        background: rgba(255, 255, 255, 0.7);
        border: 1px solid rgba(15, 118, 110, 0.1);
        backdrop-filter: blur(12px);
        border-radius: 12px;
        padding: 16px;
        transition: all 0.25s ease;
        animation: authFadeInScale 0.4s ease both;
        cursor: default;
      }
      .auth-feature-card:hover {
        border-color: rgba(15, 118, 110, 0.3);
        background: rgba(255, 255, 255, 0.95);
        transform: translateY(-2px);
        box-shadow: 0 12px 32px rgba(15, 118, 110, 0.12);
      }
      .auth-feature-icon {
        width: 36px; height: 36px;
        border-radius: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: rgba(15, 118, 110, 0.05);
        border: 1px solid rgba(15, 118, 110, 0.1);
        margin-bottom: 10px;
      }
      .auth-feature-title {
        font-weight: 800;
        color: #0f766e;
        font-size: 13px;
        margin-bottom: 4px;
      }
      .auth-feature-desc {
        color: #475569;
        font-size: 12px;
        line-height: 1.5;
      }

      /* ----- Auth Trust Bar ----- */
      .auth-trust-bar {
        display: flex;
        align-items: center;
        gap: 16px;
        padding: 12px 0;
        animation: authFadeIn 0.6s ease forwards;
      }
      .auth-trust-item {
        font-size: 12px;
        color: #64748b;
        font-weight: 600;
      }
      .auth-trust-divider {
        width: 1px;
        height: 14px;
        background: rgba(15, 118, 110, 0.15);
      }

      /* ----- Auth Form (Light Green Premium context) ----- */
      .auth-form-title {
        font-size: 18px;
        font-weight: 800;
        color: #0f172a;
        margin-bottom: 20px;
      }
      .auth-form-tabs {
        display: flex;
        margin-bottom: 24px;
        background: rgba(241, 245, 249, 0.8);
        border-radius: 10px;
        padding: 4px;
        border: 1px solid rgba(226, 232, 240, 0.8);
      }
      .auth-form-tab {
        flex: 1;
        text-align: center;
        padding: 9px;
        border-radius: 7px;
        font-size: 13px;
        font-weight: 700;
        cursor: pointer;
        transition: all 0.2s ease;
        color: #64748b;
      }
      .auth-form-tab-active {
        background: #ffffff;
        color: #0f766e;
        box-shadow: 0 2px 8px rgba(15, 118, 110, 0.08);
      }
      .auth-form-input {
        width: 100%;
        background: rgba(255, 255, 255, 0.9);
        border: 1px solid #cbd5e1;
        border-radius: 10px;
        padding: 12px 14px;
        color: #0f172a;
        font-family: inherit;
        font-size: 14px;
        outline: none;
        box-sizing: border-box;
        transition: all 0.2s ease;
      }
      .auth-form-input:focus {
        border-color: #0f766e !important;
        box-shadow: 0 0 0 3px rgba(15, 118, 110, 0.15) !important;
      }
      .auth-form-input::placeholder { color: #94a3b8; }
      .auth-form-label {
        font-size: 12px;
        color: #475569;
        font-weight: 700;
        margin-bottom: 6px;
      }
      .auth-form-btn-primary {
        width: 100%;
        padding: 12px 16px;
        border-radius: 10px;
        border: none;
        cursor: pointer;
        font-size: 14px;
        font-weight: 800;
        font-family: inherit;
        background: linear-gradient(135deg, #0f766e 0%, #047857 100%);
        color: #fff;
        box-shadow: 0 8px 24px rgba(15, 118, 110, 0.25);
        transition: all 0.2s ease;
      }
      .auth-form-btn-primary:hover:not(:disabled) {
        box-shadow: 0 12px 32px rgba(15, 118, 110, 0.35);
        transform: translateY(-1px);
      }
      .auth-form-btn-secondary {
        width: 100%;
        padding: 10px 16px;
        border-radius: 10px;
        border: 1px solid #cbd5e1;
        cursor: pointer;
        font-size: 13px;
        font-weight: 700;
        font-family: inherit;
        background: #ffffff;
        color: #475569;
        transition: all 0.2s ease;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
      }
      .auth-form-btn-secondary:hover:not(:disabled) {
        background: #f8fafc;
        color: #0f172a;
        border-color: #94a3b8;
      }
      .auth-form-alert-error {
        padding: 12px 14px;
        border-radius: 10px;
        font-size: 13px;
        margin-bottom: 14px;
        background: rgba(254, 226, 226, 0.8);
        border: 1px solid #fecaca;
        color: #b91c1c;
        line-height: 1.5;
        font-weight: 500;
      }
      .auth-form-alert-success {
        padding: 12px 14px;
        border-radius: 10px;
        font-size: 13px;
        margin-bottom: 14px;
        background: rgba(209, 250, 229, 0.8);
        border: 1px solid #a7f3d0;
        color: #047857;
        line-height: 1.5;
        font-weight: 500;
      }
      .auth-form-footer {
        text-align: center;
        margin-top: 16px;
        font-size: 11px;
        color: #64748b;
        font-family: ui-monospace, SFMono-Regular, monospace;
      }

      /* ----- Auth Logo ----- */
      .auth-form-logo {
        margin-bottom: 24px;
      }
      .auth-form-logo-title {
        font-size: 22px;
        font-weight: 900;
        color: #0f172a;
        letter-spacing: -0.02em;
      }
      .auth-form-logo-sub {
        font-size: 13px;
        color: #64748b;
        margin-top: 4px;
      }

      /* ----- Responsive ----- */
      @media (max-width: 900px) {
        .auth-page-inner {
          grid-template-columns: 1fr !important;
          gap: 32px !important;
          max-width: 480px !important;
          margin: 0 auto;
        }
        .auth-features-grid { grid-template-columns: 1fr 1fr; }
        .auth-metrics-row { gap: 16px; }
        .auth-metric-value { font-size: 22px; }
      }
      @media (max-width: 520px) {
        .auth-features-grid { grid-template-columns: 1fr; }
        .auth-metrics-row { flex-wrap: wrap; }
      }

      @media (prefers-reduced-motion: reduce) {
        .auth-hero-orb,
        .auth-hero-path,
        .auth-hero-grid,
        .auth-feature-card {
          animation: none !important;
        }
      }
    `}</style>
  );
}

// AUTH VIEW
