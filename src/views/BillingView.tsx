import React, { useState, useEffect, useCallback } from "react";
import { api } from "../utils/api";
import { trackEvent } from "../utils/analytics";
import { s } from "../styles/theme";
import type { components } from "../api-types";

type BillingWalletOut = components["schemas"]["BillingWalletOut"];
type BillingPlanOut = components["schemas"]["BillingPlanOut"];
type BillingPurchaseOut = components["schemas"]["BillingPurchaseOut"];
type BillingConfigOut = components["schemas"]["BillingConfigOut"];
type BillingCheckoutResponse = components["schemas"]["BillingCheckoutResponse"];

// Stripe-inspired plan feature matrix — mirrors Linear's pricing clarity
const PLAN_FEATURES: Record<string, string[]> = {
  starter: ["10k tokens", "Community support", "Basic guardrails", "7-day log retention"],
  growth: ["100k tokens", "Email support", "Advanced guardrails", "30-day retention", "Webhooks"],
  scale: ["1M tokens", "Priority support", "Custom Rego rules", "90-day retention", "SSO ready"],
  enterprise: ["Unlimited", "Dedicated support", "On-prem option", "Audit export", "SLA"],
};

export default function BillingView() {
  const [wallet, setWallet] = useState<BillingWalletOut | null>(null);
  const [plans, setPlans] = useState<BillingPlanOut[]>([]);
  const [purchases, setPurchases] = useState<BillingPurchaseOut[]>([]);
  const [config, setConfig] = useState<BillingConfigOut | null>(null);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [loading, setLoading] = useState(true);
  const [buying, setBuying] = useState<string | null>(null);
  const [annual, setAnnual] = useState(false);

  const load = useCallback(() => {
    setLoading(true); setError("");
    Promise.all([
      api<BillingWalletOut>("/billing/wallet"),
      api<BillingPlanOut[]>("/billing/plans"),
      api<BillingPurchaseOut[]>("/billing/purchases"),
      api<BillingConfigOut>("/billing/config"),
    ]).then(([w, p, pur, c]) => { setWallet(w); setPlans(p); setPurchases(pur); setConfig(c); })
      .catch((e: Error) => setError(e.message)).finally(() => setLoading(false));
  }, []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    if (q.get("checkout") === "success") {
      trackEvent("checkout_stripe_return", { status: "success" });
      setInfo("Payment received — tokens are being added to your wallet (refresh in a few seconds).");
      load(); window.history.replaceState({}, "", window.location.pathname + "?view=billing");
    }
    if (q.get("checkout") === "cancel") {
      trackEvent("checkout_stripe_return", { status: "cancel" });
      setInfo("Checkout cancelled."); window.history.replaceState({}, "", window.location.pathname + "?view=billing");
    }
  }, [load]);

  async function buyPlan(slug: string) {
    setBuying(slug); setError(""); setInfo("");
    try {
      const data = await api<BillingCheckoutResponse>("/billing/checkout", { method: "POST", body: { plan_slug: slug } });
      trackEvent("checkout_started", { plan: slug });
      if (data.checkout_url) { window.location.href = data.checkout_url; return; }
      setInfo(data.message || "Tokens credited."); trackEvent("checkout_completed", { plan: slug }); load();
    } catch (e) { trackEvent("checkout_failed", { plan: slug, error: e instanceof Error ? e.message : String(e) }); setError(e instanceof Error ? e.message : String(e)); }
    finally { setBuying(null); }
  }
  const fmt = (n: number | null | undefined) => Number(n || 0).toLocaleString();
  if (loading) return <div style={{ display:"grid", placeItems:"center", padding:40, color:"#8a9bb0" }}><div style={{ width:28, height:28, borderRadius:"50%", border:"3px solid #e7eef6", borderTopColor:"#0f766e", animation:"spin 0.85s linear infinite" } as React.CSSProperties}/><span style={{ fontSize:13, fontWeight:700, marginTop:10 }}>Loading billing…</span></div>;

  const unlimited = wallet?.unlimited;
  const balance = wallet?.balance_tokens ?? 0;
  const used = wallet?.tokens_used_lifetime ?? 0;
  const total = balance + used;
  const pct = unlimited ? 100 : total ? Math.min(100, Math.round((balance/total)*100)) : 100;
  const low = !unlimited && balance < 2000;

  return (
    <div>
      {/* Hero — Stripe dashboard style */}
      <div style={{ ...s.heroPanel, background:"linear-gradient(135deg,#ffffff 0%,#f0fdfa 55%,#ecfeff 100%)", border:"1px solid #ccfbf1", position:"relative", overflow:"hidden" }}>
        <div style={{ position:"absolute", inset:0, background:"radial-gradient(600px 280px at 90% -10%, rgba(20,184,166,0.10), transparent 60%)", pointerEvents:"none"}}/>
        <div style={{ position:"relative", display:"flex", justifyContent:"space-between", gap:16, flexWrap:"wrap", alignItems:"flex-start" }}>
          <div style={{ minWidth:300 }}>
            <div style={{ display:"flex", alignItems:"center", gap:10, marginBottom:6 }}>
              <div style={{ ...s.pageTitle, marginBottom:0 }}>Billing</div>
              <span style={{ background:"#0f766e", color:"#fff", fontSize:10, fontWeight:800, letterSpacing:"0.06em", textTransform:"uppercase", padding:"3px 8px", borderRadius:999 }}>Stripe • Linear</span>
            </div>
            <div style={{ color:"#405166", fontSize:14, lineHeight:1.6, maxWidth:560 }}>Tokens = LLM in + out per request. New accounts get <b>{fmt(config?.free_signup_tokens)}</b> free. Pay as you grow — no seat limits.</div>
          </div>
          <div style={{ display:"flex", gap:8, alignItems:"center" }}>
            <span style={{ fontSize:12, fontWeight:700, color:"#607086" }}>Billing period</span>
            <div style={{ display:"flex", background:"#eef3f8", borderRadius:999, padding:3, gap:2 }}>
              <button onClick={()=>setAnnual(false)} style={{ padding:"6px 14px", borderRadius:999, border:"none", cursor:"pointer", fontSize:12, fontWeight:800, background: !annual ? "#0f766e" : "transparent", color: !annual ? "#fff" : "#405166" }}>Monthly</button>
              <button onClick={()=>setAnnual(true)} style={{ padding:"6px 14px", borderRadius:999, border:"none", cursor:"pointer", fontSize:12, fontWeight:800, background: annual ? "#0f766e" : "transparent", color: annual ? "#fff" : "#405166" }}>Annual <span style={{ opacity:0.7, fontWeight:600 }}>-20%</span></button>
            </div>
          </div>
        </div>
      </div>

      {error && <div style={{ ...s.alert("error"), marginBottom:14 }}>{error}</div>}
      {info && <div style={{ ...s.alert("success"), marginBottom:14 }}>{info}</div>}

      {/* Wallet — Stripe balance card */}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(320px,1fr))", gap:14, marginBottom:16 }}>
        <div style={{ ...s.card, padding:0, overflow:"hidden", position:"relative" }}>
          <div style={{ position:"absolute", top:0, left:0, right:0, height:3, background: low ? "linear-gradient(90deg,#f43f5e,#fb7185)" : "linear-gradient(90deg,#0f766e,#14b8a6)", opacity:0.95 }}/>
          <div style={{ padding:22, display:"flex", gap:18, alignItems:"center" }}>
            <div style={{ position:"relative", width:72, height:72, flexShrink:0 }}>
              <svg width={72} height={72} viewBox="0 0 72 72" style={{ transform:"rotate(-90deg)" }}>
                <circle cx={36} cy={36} r={30} fill="none" stroke="#e7eef6" strokeWidth={6}/>
                <circle cx={36} cy={36} r={30} fill="none" stroke={low ? "#f43f5e" : "#0f766e"} strokeWidth={6} strokeLinecap="round" strokeDasharray={`${pct*1.884} 188.4`} style={{ transition:"stroke-dasharray 0.8s cubic-bezier(0.22,1,0.36,1)" }}/>
              </svg>
              <div style={{ position:"absolute", inset:0, display:"grid", placeItems:"center", fontSize:13, fontWeight:850, color: low ? "#be123c" : "#0f766e" }}>{pct}%</div>
            </div>
            <div style={{ minWidth:0, flex:1 }}>
              <div style={{ fontSize:11, fontWeight:800, color:"#7b8a9d", letterSpacing:"0.06em", textTransform:"uppercase" }}>Token balance</div>
              <div style={{ fontSize:30, fontWeight:900, color: low ? "#be123c" : "#0f766e", lineHeight:1.1 }}>{unlimited ? "Unlimited" : fmt(balance)}</div>
              <div style={{ fontSize:12, color:"#607086", marginTop:4 }}>{unlimited ? "Owner • no deduction" : `${fmt(used)} used • ${fmt(wallet?.tokens_purchased_lifetime ?? 0)} purchased`}{low && !unlimited && <span style={{ color:"#be123c", fontWeight:700 }}> • Low — refill soon</span>}</div>
              <div style={{ marginTop:10, height:6, background:"#e7eef6", borderRadius:999, overflow:"hidden" }}><div style={{ width:`${pct}%`, height:"100%", background: low ? "linear-gradient(90deg,#f43f5e,#fb7185)" : "linear-gradient(90deg,#0f766e,#14b8a6)", borderRadius:999, transition:"width 0.6s" }}/></div>
            </div>
          </div>
          <div style={{ padding:"0 22px 16px", display:"flex", gap:8, flexWrap:"wrap" }}>
            <span style={{ fontSize:11, fontWeight:700, color:"#607086", background:"#f8fbff", border:"1px solid #dce7f0", padding:"6px 10px", borderRadius:999 }}>{wallet?.billing_enabled ? "Billing on" : "Billing off"} • {config?.stripe_configured ? "Stripe live" : "Stripe dev"}</span>
            <span style={{ fontSize:11, color:"#8a9bb0", alignSelf:"center" }}>Auto-refills on checkout</span>
          </div>
        </div>

        <div style={{ ...s.card, background:"linear-gradient(135deg,#0f766e 0%,#0d5c55 100%)", color:"#fff", border:"none", position:"relative", overflow:"hidden" }}>
          <div style={{ position:"absolute", inset:0, background:"radial-gradient(400px 200px at 85% 0%, rgba(255,255,255,0.14), transparent 60%)", pointerEvents:"none"}}/>
          <div style={{ position:"relative" }}>
            <div style={{ fontSize:11, fontWeight:800, letterSpacing:"0.06em", textTransform:"uppercase", opacity:0.85 }}>Need more?</div>
            <div style={{ fontSize:18, fontWeight:850, marginTop:6, lineHeight:1.3 }}>Scales from hobby to enterprise</div>
            <div style={{ fontSize:13, opacity:0.85, marginTop:6, lineHeight:1.5 }}>Start free, upgrade when you ship. Volume discounts beyond Scale.</div>
            <div style={{ display:"flex", gap:8, marginTop:14, flexWrap:"wrap" }}>
              <button style={{ background:"#fff", color:"#0f766e", border:"none", borderRadius:10, padding:"9px 16px", fontSize:13, fontWeight:800, cursor:"pointer" }} onClick={()=>document.getElementById("plans-grid")?.scrollIntoView({behavior:"smooth"})}>View plans</button>
              <a href="mailto:support@llm-guardrails.dev" style={{ background:"rgba(255,255,255,0.14)", color:"#fff", border:"1px solid rgba(255,255,255,0.22)", borderRadius:10, padding:"9px 14px", fontSize:13, fontWeight:700, textDecoration:"none", backdropFilter:"blur(6px)" }}>Talk to sales</a>
            </div>
          </div>
        </div>
      </div>

      {!config?.stripe_configured && (
        <div style={{ ...s.alert("info"), marginBottom:14, display:"flex", gap:10, alignItems:"center", flexWrap:"wrap" }}>
          <span>Stripe not configured — dev mode: Buy credits instantly (no checkout).</span>
          <a href="https://dashboard.stripe.com/test/dashboard" target="_blank" rel="noreferrer" style={{ fontSize:12, fontWeight:700, color:"#0f766e" }}>Open Stripe test dashboard --</a>
        </div>
      )}

      {/* Plans — Stripe pricing table */}
      <div id="plans-grid" style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(240px,1fr))", gap:14, marginBottom:16 }}>
        {plans.map(p=>{
          const feats = PLAN_FEATURES[p.slug] || [p.description];
          const price = annual ? (p.price_cents * 0.8 / 100).toFixed(2) : (p.price_cents/100).toFixed(2);
          return (
            <div key={p.slug} style={{ ...s.card, padding:0, overflow:"hidden", border: p.popular ? "2px solid #0f766e" : "1px solid rgba(15,118,110,0.12)", position:"relative", transform: p.popular ? "translateY(-2px)" : undefined, boxShadow: p.popular ? "0 16px 36px rgba(15,118,110,0.16)" : undefined }}>
              {p.popular && <div style={{ position:"absolute", top:10, right:10, background:"linear-gradient(135deg,#0f766e,#14b8a6)", color:"#fff", fontSize:10, fontWeight:850, letterSpacing:"0.06em", textTransform:"uppercase", padding:"4px 9px", borderRadius:999, boxShadow:"0 6px 14px rgba(15,118,110,0.22)" }}>Most popular</div>}
              <div style={{ padding:20 }}>
                <div style={{ fontSize:13, fontWeight:800, color:"#7b8a9d", letterSpacing:"0.06em", textTransform:"uppercase" }}>{p.name}</div>
                <div style={{ display:"flex", alignItems:"baseline", gap:6, marginTop:10 }}>
                  <span style={{ fontSize:30, fontWeight:900, color:"#102033", letterSpacing:"-0.02em" }}>${price}</span>
                  <span style={{ fontSize:12, color:"#7b8a9d", fontWeight:700 }}>{annual ? "/mo billed yearly" : "one-time"}</span>
                </div>
                <div style={{ fontSize:12, color:"#0f766e", fontWeight:800, marginTop:6 }}>{fmt(p.tokens)} tokens • {fmt(Math.round(p.tokens/1000))}k</div>
                <ul style={{ margin:"14px 0 0", padding:0, listStyle:"none", display:"flex", flexDirection:"column", gap:8 }}>
                  {feats.map(f=>(
                    <li key={f} style={{ display:"flex", gap:8, alignItems:"center", fontSize:13, color:"#27394f" }}>
                      <span style={{ width:18, height:18, borderRadius:999, background:"#ecfdf5", border:"1px solid #a7f3d0", display:"grid", placeItems:"center", color:"#0f766e", fontSize:11, flexShrink:0 }}></span>{f}
                    </li>
                  ))}
                </ul>
              </div>
              <div style={{ padding:"0 20px 20px" }}>
                <button type="button" style={{ ...s.btn(p.popular ? "primary" : "secondary"), width:"100%", borderRadius:10, padding:"11px 14px", opacity: buying?0.7:1 }} disabled={!!buying} onClick={()=>buyPlan(p.slug)}>
                  {buying===p.slug ? "Redirecting…" : `Buy ${p.name}`}
                </button>
                <div style={{ fontSize:11, color:"#8a9bb0", textAlign:"center", marginTop:8 }}>Secure by Stripe • instant credit</div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Invoices — Stripe-style */}
      <div style={{ ...s.card, padding:0, overflow:"hidden", marginBottom:16 }}>
        <div style={{ padding:"18px 22px 0", display:"flex", justifyContent:"space-between", alignItems:"center" }}>
          <div style={s.sectionTitle}>Invoices</div>
          <span style={{ fontSize:11, fontWeight:700, color:"#8a9bb0" }}>{purchases.length} records</span>
        </div>
        <div style={{ overflowX:"auto", marginTop:12 }}>
          <table style={s.table}>
            <thead><tr>{["Invoice","Tokens","Amount","Status","Date",""].map(h=> <th key={h} style={s.th}>{h}</th>)}</tr></thead>
            <tbody>
              {purchases.length===0 ? <tr><td colSpan={6} style={{ ...s.td, textAlign:"center", color:"#7b8a9d", padding:24 }}>No purchases yet — pick a plan above.</td></tr> :
                purchases.map(r=>(
                  <tr key={r.id} style={{ transition:"background .12s" }} onMouseEnter={e=>e.currentTarget.style.background="#f8fbff"} onMouseLeave={e=>e.currentTarget.style.background="transparent"}>
                    <td style={{ ...s.td, fontFamily:"ui-monospace,monospace", fontSize:12, fontWeight:700, color:"#0f766e" }}>{r.id.slice(0,8)}…</td>
                    <td style={s.td}><span style={{ fontWeight:750 }}>{fmt(r.tokens_granted)}</span> <span style={{ fontSize:11, color:"#7b8a9d" }}>tokens</span></td>
                    <td style={s.td}>{r.amount_cents ? `$${(r.amount_cents/100).toFixed(2)}` : <span style={{ color:"#7b8a9d" }}>—</span>}</td>
                    <td style={s.td}><span style={s.badge(r.status==="completed"?"delivered": r.status==="pending"?"rate_limited":"error")}>{r.status}</span></td>
                    <td style={{ ...s.td, fontSize:12, color:"#7b8a9d" }}>{new Date(r.created_at).toLocaleDateString()} • {new Date(r.created_at).toLocaleTimeString()}</td>
                    <td style={s.td}><button style={{ ...s.btn("secondary"), padding:"6px 10px", fontSize:11, borderRadius:8 }} onClick={()=>window.print()}>Receipt</button></td>
                  </tr>
                ))
              }
            </tbody>
          </table>
        </div>
        <div style={{ padding:"12px 22px", background:"#f8fbff", borderTop:"1px solid #eef3f8", display:"flex", gap:8, flexWrap:"wrap", alignItems:"center" }}>
          <span style={{ fontSize:11, color:"#7b8a9d" }}>Need help? <a href="mailto:billing@llm-guardrails.dev" style={{ color:"#0f766e", fontWeight:700 }}>billing@llm-guardrails.dev</a></span>
          <span style={{ marginLeft:"auto", fontSize:11, color:"#a8a29e" }}>Tax calculated at checkout • Stripe • 3D Secure</span>
        </div>
      </div>

      {/* Publish checklist — Linear callout */}
      <div style={{ ...s.card, background:"#f8fbff", border:"1px dashed #c7d2fe" }}>
        <div style={{ display:"flex", gap:10, alignItems:"center", marginBottom:10 }}>
          <span style={{ width:26, height:26, borderRadius:8, background:"#0f766e", color:"#fff", display:"grid", placeItems:"center", fontSize:12 }}></span>
          <div style={s.sectionTitle}>Production checklist</div>
          <span style={{ fontSize:11, fontWeight:700, color:"#6366f1", background:"#eef2ff", border:"1px solid #c7d2fe", padding:"3px 8px", borderRadius:999 }}>Stripe live</span>
        </div>
        <pre style={{ margin:0, fontSize:12, lineHeight:1.6, padding:14, background:"#fff", borderRadius:10, border:"1px solid #e7eef6", overflow:"auto" }}>{`# .env — production (Render / Vercel env, not repo)
STRIPE_SECRET_KEY=sk_live_…
STRIPE_PUBLISHABLE_KEY=pk_live_…
STRIPE_WEBHOOK_SECRET=whsec_…
BILLING_ENABLED=true
FREE_SIGNUP_TOKENS=10000

# Stripe Dashboard -- Developers -- Webhooks -- Add endpoint:
#   https://YOUR_APP/billing/webhook
# Events: checkout.session.completed`}</pre>
      </div>
    </div>
  );
}
