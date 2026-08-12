import React, { useState, useEffect, useCallback, useRef } from "react";
import { api, getToken, setTokens, clearTokens, getGatewayKey, setGatewayKey, maskGatewayKey, gatewayKeyInputProps, formatApiError, USER_PROMPT, AI_RESPONSE } from "../utils/api";
import { s } from "../styles/theme";
function useTypewriter(text: string, { speed = 36, delay = 0, active = false, wordByWord = false }: { speed?: number; delay?: number; active?: boolean; wordByWord?: boolean } = {}): { displayed: string; done: boolean } {
  const [displayed, setDisplayed] = useState("");
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!active) {
      setDisplayed("");
      setDone(false);
      return;
    }

    setDisplayed("");
    setDone(false);
    
    const items: string[] = wordByWord ? text.split(" ") : [text];
    let index = 0;
    let intervalId: number | null = null;
    
    const startId = window.setTimeout(() => {
      intervalId = window.setInterval(() => {
        index += 1;
        const next = items.slice(0, index).join(" ") + (wordByWord && index < items.length ? " " : "");
        setDisplayed(next);
        if (index >= items.length) {
          if (intervalId) window.clearInterval(intervalId);
          setDone(true);
        }
      }, speed);
    }, delay);

    return () => {
      window.clearTimeout(startId);
      if (intervalId) window.clearInterval(intervalId);
    };
  }, [text, speed, delay, active, wordByWord]);

  return { displayed, done };
}

function TypeCursor({ visible }: { visible: boolean }) {
  if (!visible) return null;
  return <span className="auth-cursor">▍</span>;
}

function AnimatedCounter({ end, suffix = "", duration = 2000, delay = 0, active = false }: {
  end: number; suffix?: string; duration?: number; delay?: number; active?: boolean;
}) {
  const [value, setValue] = useState(0);
  useEffect(() => {
    if (!active) { setValue(0); return; }
    const startTime = Date.now() + delay;
    const tick = () => {
      const elapsed = Date.now() - startTime;
      if (elapsed < 0) { requestAnimationFrame(tick); return; }
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setValue(Math.round(end * eased));
      if (progress < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }, [end, duration, delay, active]);
  return <>{value.toLocaleString()}{suffix}</>;
}

function ShieldIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
    </svg>
  );
}

function LockIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0110 0v4"/>
    </svg>
  );
}

function ChartIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>
    </svg>
  );
}

function ZapIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
    </svg>
  );
}

export default function AuthTerminalIntro() {
  const [showPrompt, setShowPrompt] = useState(false);
  const [showThinking, setShowThinking] = useState(false);
  const [showResponse, setShowResponse] = useState(false);
  const [responseDone, setResponseDone] = useState(false);
  const [showFeatures, setShowFeatures] = useState(false);
  const [showMetrics, setShowMetrics] = useState(false);

  const promptText = useTypewriter(USER_PROMPT, {
    speed: 28, delay: 500, active: showPrompt, wordByWord: false
  });

  const responseText = useTypewriter(AI_RESPONSE, {
    speed: 22, delay: 0, active: showResponse, wordByWord: false
  });

  useEffect(() => {
    setShowPrompt(true);
  }, []);

  useEffect(() => {
    if (promptText.done) {
      setShowThinking(true);
      const id = window.setTimeout(() => {
        setShowThinking(false);
        setShowResponse(true);
      }, 700);
      return () => window.clearTimeout(id);
    }
  }, [promptText.done]);

  useEffect(() => {
    if (responseText.done) {
      setResponseDone(true);
      const id1 = window.setTimeout(() => setShowMetrics(true), 300);
      const id2 = window.setTimeout(() => setShowFeatures(true), 600);
      return () => { window.clearTimeout(id1); window.clearTimeout(id2); };
    }
  }, [responseText.done]);

  const features = [
    { Icon: ShieldIcon, title: "LLM Gateway", desc: "Block PII, jailbreaks, and prompt injections in real-time", color: "#2dd4bf" },
    { Icon: LockIcon, title: "Skill Guard", desc: "Detect secrets and destructive commands in agent context", color: "#818cf8" },
    { Icon: ChartIcon, title: "Policy Engine", desc: "Customizable rules for input, output, and compliance", color: "#60a5fa" },
    { Icon: ZapIcon, title: "Git & CI", desc: "Pre-push hooks and GitHub Actions integration", color: "#fbbf24" },
  ];

  return (
    <div className="auth-intro-panel">
      {/* Badge */}
      <div className="auth-hero-badge">
        <span className="auth-hero-badge-dot" />
        AI Guardrails Platform
      </div>

      {/* Headline */}
      <h1 className="auth-hero-headline">
        Secure every AI workflow<br />
        <span className="auth-hero-headline-gradient">before it ships.</span>
      </h1>

      <p className="auth-hero-subhead">
        Enterprise-grade protection for LLM traffic, agent skills,
        and system prompts — from one unified dashboard.
      </p>

      {/* Animated metrics */}
      {showMetrics && (
        <div className="auth-metrics-row">
          {[
            { value: 99.9, suffix: "%", label: "Uptime SLA" },
            { value: 12, suffix: "ms", label: "Avg Latency" },
            { value: 847, suffix: "K", label: "Threats Blocked" },
          ].map((m, i) => (
            <div key={m.label} className="auth-metric-item">
              <div className="auth-metric-value">
                <AnimatedCounter end={m.value} suffix={m.suffix} delay={i * 200} active={showMetrics} />
              </div>
              <div className="auth-metric-label">{m.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Terminal */}
      <div className="auth-terminal">
        <div className="auth-terminal-bar">
          <span className="auth-terminal-dot" style={{ background: "#ff5f57" }} />
          <span className="auth-terminal-dot" style={{ background: "#febc2e" }} />
          <span className="auth-terminal-dot" style={{ background: "#28c840" }} />
          <span className="auth-terminal-title">AI Assistant</span>
        </div>
        <div className="auth-terminal-body">
          {showPrompt && (
            <div className="auth-chat-bubble auth-chat-user">
              <div className="auth-chat-avatar auth-chat-avatar-user">U</div>
              <div className="auth-chat-content auth-chat-content-user">
                {promptText.displayed}
                {!promptText.done && <TypeCursor visible />}
              </div>
            </div>
          )}

          {(showThinking || showResponse) && (
            <div className="auth-chat-bubble auth-chat-ai" style={{ animation: "authFadeIn 0.3s ease forwards" }}>
              <div className="auth-chat-avatar auth-chat-avatar-ai">AI</div>
              <div className="auth-chat-content auth-chat-content-ai">
                {showThinking && <span className="auth-thinking">Analyzing request...</span>}
                {showResponse && (
                  <>
                    {responseText.displayed}
                    {!responseText.done && <TypeCursor visible />}
                  </>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Feature cards */}
      {showFeatures && (
        <div className="auth-features-grid">
          {features.map(({ Icon, title, desc, color }, i) => (
            <div key={title} className="auth-feature-card" style={{ animationDelay: `${i * 100}ms` }}>
              <div className="auth-feature-icon" style={{ color }}>
                <Icon />
              </div>
              <div className="auth-feature-title">{title}</div>
              <div className="auth-feature-desc">{desc}</div>
            </div>
          ))}
        </div>
      )}

      {/* Trust bar */}
      {responseDone && (
        <div className="auth-trust-bar">
          <span className="auth-trust-item">SOC 2 Ready</span>
          <span className="auth-trust-divider" />
          <span className="auth-trust-item">Sub-15ms Latency</span>
          <span className="auth-trust-divider" />
          <span className="auth-trust-item">Zero Data Retention</span>
        </div>
      )}
    </div>
  );
}

