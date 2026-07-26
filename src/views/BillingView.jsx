import React, { useState, useEffect, useCallback, useRef } from "react";
import { api, getToken, setTokens, clearTokens, getGatewayKey, setGatewayKey, maskGatewayKey, gatewayKeyInputProps, formatApiError } from "../utils/api";
import { trackEvent } from "../utils/analytics";
import { s } from "../styles/theme";
export default function BillingView() {
  const [wallet, setWallet] = useState(null);
  const [plans, setPlans] = useState([]);
  const [purchases, setPurchases] = useState([]);
  const [config, setConfig] = useState(null);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [loading, setLoading] = useState(true);
  const [buying, setBuying] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    setError("");
    Promise.all([
      api("/billing/wallet"),
      api("/billing/plans"),
      api("/billing/purchases"),
      api("/billing/config"),
    ])
      .then(([w, p, pur, c]) => {
        setWallet(w);
        setPlans(p);
        setPurchases(pur);
        setConfig(c);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    if (q.get("checkout") === "success") {
      trackEvent("checkout_stripe_return", { status: "success" });
      setInfo("Payment received — tokens are being added to your wallet (refresh in a few seconds).");
      load();
      window.history.replaceState({}, "", window.location.pathname + "?view=billing");
    }
    if (q.get("checkout") === "cancel") {
      trackEvent("checkout_stripe_return", { status: "cancel" });
      setInfo("Checkout cancelled.");
      window.history.replaceState({}, "", window.location.pathname + "?view=billing");
    }
  }, [load]);

  async function buyPlan(slug) {
    setBuying(slug);
    setError("");
    setInfo("");
    try {
      const data = await api("/billing/checkout", { method: "POST", body: { plan_slug: slug } });
      trackEvent("checkout_started", { plan: slug });
      if (data.checkout_url) {
        window.location.href = data.checkout_url;
        return;
      }
      setInfo(data.message || "Tokens credited.");
      trackEvent("checkout_completed", { plan: slug });
      load();
    } catch (e) {
      trackEvent("checkout_failed", { plan: slug, error: e.message });
      setError(e.message);
    } finally {
      setBuying(null);
    }
  }

  function fmt(n) {
    return Number(n || 0).toLocaleString();
  }

  if (loading) return <div style={s.muted}>Loading billing...</div>;

  const unlimited = wallet?.unlimited;
  const balance = wallet?.balance_tokens ?? 0;
  const pct = wallet?.billing_enabled && !unlimited
    ? Math.min(100, Math.round((balance / Math.max(balance + (wallet?.tokens_used_lifetime || 0), 1)) * 100))
    : 100;

  return (
    <div>
      <div style={s.heroPanel}>
        <div style={{ ...s.pageTitle, marginBottom: 8 }}>Token plans</div>
        <div style={{ color: "#405166", fontSize: 15, lineHeight: 1.6, maxWidth: 720 }}>
          Gateway usage is metered in <strong>tokens</strong> (LLM input + output per request).
          New accounts receive {fmt(config?.free_signup_tokens)} free tokens; buy packs when you need more.
        </div>
      </div>

      {error && <div style={{ ...s.alert("error"), marginBottom: 16 }}>{error}</div>}
      {info && <div style={{ ...s.alert("success"), marginBottom: 16 }}>{info}</div>}

      <div style={{ ...s.card, marginBottom: 16 }}>
        <div style={s.sectionTitle}>Your balance</div>
        <div style={{ fontSize: 32, fontWeight: 900, color: "#0f766e" }}>
          {unlimited ? "Unlimited" : fmt(balance)}
        </div>
        <div style={{ fontSize: 13, color: "#607086", marginTop: 4 }}>
          {unlimited ? "gateway tokens (owner account)" : "tokens remaining"}
          {wallet?.billing_enabled && !unlimited && (
            <> · {fmt(wallet.tokens_used_lifetime)} used · {fmt(wallet.tokens_purchased_lifetime)} purchased</>
          )}
        </div>
        {wallet?.billing_enabled && !unlimited && (
          <div style={{ marginTop: 12, height: 8, background: "#e2e8f0", borderRadius: 4, overflow: "hidden" }}>
            <div style={{ width: `${pct}%`, height: "100%", background: "#0f766e" }} />
          </div>
        )}
        {!config?.stripe_configured && (
          <div style={{ ...s.alert("error"), marginTop: 12, marginBottom: 0, fontSize: 12 }}>
            Stripe not configured on server — in development, Buy still credits tokens instantly.
          </div>
        )}
      </div>

      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))",
        gap: 14,
        marginBottom: 16,
      }}>
        {plans.map((p) => (
          <div key={p.slug} style={{
            ...s.card,
            border: p.popular ? "2px solid #0f766e" : undefined,
            position: "relative",
          }}>
            {p.popular && (
              <div style={{
                position: "absolute", top: -10, right: 12,
                background: "#0f766e", color: "#fff", fontSize: 10, fontWeight: 800,
                padding: "4px 8px", borderRadius: 4,
              }}>POPULAR</div>
            )}
            <div style={{ fontWeight: 900, fontSize: 18, color: "#102033" }}>{p.name}</div>
            <div style={{ fontSize: 28, fontWeight: 900, marginTop: 8, color: "#0f766e" }}>
              {p.price_display}
            </div>
            <div style={{ fontSize: 13, color: "#607086", marginTop: 4 }}>{fmt(p.tokens)} tokens</div>
            <div style={{ fontSize: 12, color: "#7b8a9d", marginTop: 8, lineHeight: 1.5, minHeight: 40 }}>
              {p.description}
            </div>
            <button
              type="button"
              style={{ ...s.btn("primary"), width: "100%", marginTop: 14 }}
              disabled={!!buying}
              onClick={() => buyPlan(p.slug)}
            >
              {buying === p.slug ? "Please wait..." : "Buy tokens"}
            </button>
          </div>
        ))}
      </div>

      <div style={s.card}>
        <div style={s.sectionTitle}>Purchase history</div>
        {purchases.length === 0 ? (
          <div style={s.muted}>No purchases yet.</div>
        ) : (
          <table style={s.table}>
            <thead>
              <tr>
                {["Plan", "Tokens", "Amount", "Status", "Date"].map((h) => (
                  <th key={h} style={s.th}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {purchases.map((r) => (
                <tr key={r.id}>
                  <td style={s.td}>{r.plan_slug}</td>
                  <td style={s.td}>{fmt(r.tokens_granted)}</td>
                  <td style={s.td}>
                    {r.amount_cents ? `$${(r.amount_cents / 100).toFixed(2)}` : "—"}
                  </td>
                  <td style={s.td}>
                    <span style={s.badge(r.status === "completed" ? "delivered" : "rate_limited")}>
                      {r.status}
                    </span>
                  </td>
                  <td style={s.td}>{new Date(r.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div style={{ ...s.card, marginTop: 16 }}>
        <div style={s.sectionTitle}>Publish checklist (Stripe)</div>
        <pre style={{ margin: 0, fontSize: 12, lineHeight: 1.5, padding: 14, background: "#f1f5f9",
          borderRadius: 8, border: "1px solid #dce7f0", overflow: "auto" }}>
{`# .env on Render / production
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PUBLISHABLE_KEY=pk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
BILLING_ENABLED=true
FREE_SIGNUP_TOKENS=10000

# Stripe Dashboard → Webhooks → endpoint:
#   https://YOUR_APP/billing/webhook
# Events: checkout.session.completed`}
        </pre>
      </div>
    </div>
  );
}

// REJECTED ACCESS — review and unblock (web control layer)

// Live skill definitions storage key
const LIVE_SKILLS_KEY = "ag_live_skills";

