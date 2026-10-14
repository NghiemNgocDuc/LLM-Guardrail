import { useCallback, useEffect, useState } from "react";
import { api } from "../utils/api";
import { trackEvent } from "../utils/analytics";
import type { components } from "../api-types";
import { Badge, Button, Dialog, EmptyState, LoadingState, Notice, PageHeader, Panel, TableWrap } from "../components/ui";
import "../styles/accounts.css";

type Wallet = components["schemas"]["BillingWalletOut"];
type Plan = components["schemas"]["BillingPlanOut"];
type Purchase = components["schemas"]["BillingPurchaseOut"];
type Config = components["schemas"]["BillingConfigOut"];
type Checkout = components["schemas"]["BillingCheckoutResponse"];
const amount = (cents: number, currency: string) => new Intl.NumberFormat(undefined, { style: "currency", currency: currency.toUpperCase() }).format(cents / 100);
const number = (value: number) => value.toLocaleString();

export default function BillingView() {
  const [wallet, setWallet] = useState<Wallet | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [purchases, setPurchases] = useState<Purchase[]>([]);
  const [config, setConfig] = useState<Config | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [buying, setBuying] = useState<string | null>(null);
  const [receipt, setReceipt] = useState<Purchase | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [nextWallet, nextPlans, nextPurchases, nextConfig] = await Promise.all([
        api<Wallet>("/billing/wallet"), api<Plan[]>("/billing/plans"),
        api<Purchase[]>("/billing/purchases"), api<Config>("/billing/config"),
      ]);
      setWallet(nextWallet); setPlans(nextPlans); setPurchases(nextPurchases); setConfig(nextConfig);
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    const url = new URL(window.location.href);
    const status = url.searchParams.get("checkout");
    if (status !== "success" && status !== "cancel") return;
    trackEvent("checkout_stripe_return", { status });
    setInfo(status === "success" ? "Checkout completed. Your balance updates when payment is confirmed; refresh if the credits are still pending." : "Checkout cancelled. Your balance has not changed.");
    url.searchParams.delete("checkout"); url.searchParams.set("view", "billing");
    window.history.replaceState({}, "", url);
  }, []);

  async function buyPlan(slug: string) {
    setBuying(slug); setError(""); setInfo("");
    try {
      const checkout = await api<Checkout>("/billing/checkout", { method: "POST", body: { plan_slug: slug } });
      trackEvent("checkout_started", { plan: slug });
      if (checkout.checkout_url) { window.location.assign(checkout.checkout_url); return; }
      setInfo(checkout.message || "Purchase completed. Your wallet has been refreshed.");
      trackEvent("checkout_completed", { plan: slug }); await load();
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : String(reason);
      trackEvent("checkout_failed", { plan: slug, error: message }); setError(message);
    } finally { setBuying(null); }
  }

  return <div className="accounts-page">
    <PageHeader eyebrow="Usage & billing" title="Room for your next idea." description="See your token balance, buy credits, and keep track of your purchases." actions={<Button variant="secondary" icon="refresh" onClick={() => void load()} loading={loading}>Refresh balance</Button>} />
    {info && <Notice tone="info">{info}</Notice>}
    {error && <Notice tone="danger">{error}{!wallet && <Button variant="ghost" onClick={() => void load()}>Try again</Button>}</Notice>}
    {loading && !wallet ? <LoadingState label="Loading your wallet and token packs" /> : wallet && config && <>
      <div className="accounts-wallet-grid">
        <Panel className="accounts-wallet" title="Available tokens" actions={<Badge tone={config.billing_enabled ? "success" : "neutral"}>{config.billing_enabled ? "Purchases enabled" : "Purchases disabled"}</Badge>}>
          <div className="accounts-wallet-balance">{wallet.unlimited ? "Unlimited" : number(wallet.balance_tokens)}</div>
          <p className="accounts-copy">{wallet.unlimited ? "Your account has unlimited token access." : "Credits are used for model input and output tokens."}</p>
          <div className="accounts-wallet-stats"><div><span>Used to date</span><strong>{number(wallet.tokens_used_lifetime)}</strong></div><div><span>Purchased to date</span><strong>{number(wallet.tokens_purchased_lifetime)}</strong></div></div>
        </Panel>
        <Panel title="One-time credit packs" description="Choose the amount you need. Pack prices come directly from your billing configuration.">
          <div className="accounts-detail-row"><span>Signup allowance</span><strong>{number(config.free_signup_tokens)} tokens</strong></div>
          <div className="accounts-detail-row"><span>Payment checkout</span><Badge tone={config.stripe_configured ? "success" : "warning"}>{config.stripe_configured ? "Configured" : "Not configured"}</Badge></div>
          <p className="accounts-copy">{config.stripe_configured ? "Continue to Stripe to review payment details before completing your purchase." : "The payment provider is not configured. Checkout may be unavailable; development accounts can receive test credits."}</p>
          <a className="accounts-link" href="#token-packs">Explore token packs <span aria-hidden="true">↓</span></a>
        </Panel>
      </div>
      <section id="token-packs" aria-labelledby="accounts-packs-title" className="accounts-section">
        <div className="accounts-section-heading"><div><h2 id="accounts-packs-title">Find your next token pack</h2><p>One purchase. Credits added after confirmation.</p></div><Badge>{plans.length} packs available</Badge></div>
        {plans.length ? <div className="accounts-plans">{plans.map((plan) => <article className="accounts-plan" key={plan.slug}>
          <span className="accounts-kicker">{plan.name}</span><h3>{amount(plan.price_cents, plan.currency)}<small>one-time</small></h3>
          <div className="accounts-plan-tokens">{number(plan.tokens)} tokens</div><p>{plan.description}</p>
          <Button variant="primary" onClick={() => void buyPlan(plan.slug)} loading={buying === plan.slug} disabled={Boolean(buying) || !config.billing_enabled}>Buy {plan.name}</Button>
        </article>)}</div> : <EmptyState icon="card" title="No packs available" description="Token packs will appear when billing is configured." />}
      </section>
      <Panel title="Purchase history" description="Your latest token purchases and their payment status." actions={<Badge>{purchases.length} records</Badge>}>
        {purchases.length ? <TableWrap label="Token purchase history"><table className="ui-table accounts-table"><thead><tr><th scope="col">Purchase</th><th scope="col">Tokens</th><th scope="col">Amount</th><th scope="col">Status</th><th scope="col">Created</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead><tbody>{purchases.map((purchase) => <tr key={purchase.id}>
          <td><strong className="accounts-table-name">{plans.find((plan) => plan.slug === purchase.plan_slug)?.name || purchase.plan_slug}</strong><span className="accounts-mono accounts-secondary">{purchase.id.slice(0, 8)}</span></td><td className="accounts-mono">{number(purchase.tokens_granted)}</td><td className="accounts-mono">{amount(purchase.amount_cents, purchase.currency)}</td><td><Badge tone={purchase.status === "completed" ? "success" : purchase.status === "pending" ? "warning" : "danger"}>{purchase.status}</Badge></td><td className="accounts-nowrap"><time dateTime={purchase.created_at}>{new Date(purchase.created_at).toLocaleDateString()}</time></td><td><Button variant="ghost" onClick={() => setReceipt(purchase)}>View record</Button></td>
        </tr>)}</tbody></table></TableWrap> : <EmptyState icon="card" title="No purchases yet" description="Your first purchase will appear here with its payment status." />}
      </Panel>
    </>}
    <Dialog open={Boolean(receipt)} onClose={() => setReceipt(null)} title="Purchase record" description="Details of this token purchase." footer={<><Button variant="secondary" onClick={() => setReceipt(null)}>Close</Button><Button icon="logs" onClick={() => window.print()}>Print record</Button></>}>
      {receipt && <div className="accounts-receipt"><h2>AI Guardrails · purchase record</h2><dl><div><dt>Reference</dt><dd className="accounts-mono">{receipt.id}</dd></div><div><dt>Token pack</dt><dd>{receipt.plan_slug}</dd></div><div><dt>Tokens</dt><dd>{number(receipt.tokens_granted)}</dd></div><div><dt>Amount</dt><dd>{amount(receipt.amount_cents, receipt.currency)}</dd></div><div><dt>Status</dt><dd>{receipt.status}</dd></div><div><dt>Created</dt><dd>{new Date(receipt.created_at).toLocaleString()}</dd></div>{receipt.completed_at && <div><dt>Completed</dt><dd>{new Date(receipt.completed_at).toLocaleString()}</dd></div>}</dl></div>}
    </Dialog>
  </div>;
}
