import type { Page, Request } from "@playwright/test";
export const user = { id: "ui-user", email: "reviewer@example.com", full_name: "Alex Reviewer", is_admin: true, is_active: true, email_verified: true, org_id: "ui-org", created_at: "2026-01-01T00:00:00Z", last_login: "2026-10-13T10:00:00Z" };
export const org = { id: "ui-org", name: "Northstar workspace", slug: "northstar", created_at: "2026-01-01T00:00:00Z", member_count: 2, skill_count: 1, is_leader: true };
export const policy = { org_id: "ui-org", version: 3, updated_at: "2026-10-13T12:00:00Z", input_rules: { block_secrets: true, block_pii: true, pii_redaction_mode: "warn", pii_patterns: [], block_prompt_injection: true, block_jailbreak: true, injection_keywords: ["ignore previous instructions"], jailbreak_patterns: ["DAN mode"] }, output_rules: { block_toxic_content: true, enforce_schema: false, required_fields: [] }, compliance_rules: { block_medical_advice: true, never_discuss_competitors: true, full_prompt_logging: false, webhook_url: "", blocked_ips: [], custom_retained_field: "keep-me" }, topic_policy: { blocked_topics: ["medical advice"] }, llm_backend: "groq", llm_model: "llama-3.3-70b-versatile", custom_rule_rego: null, rate_limit_rpm: 60, rate_limit_rpd: 10000 };
export const log = { id: "request-1", request_id: "req-ui-1", user_id: "ui-user", api_key_id: null, status: "delivered", prompt_preview: "Explain safe AI workflows", full_prompt: null, reason: null, fired_rule: null, input_block_reason: null, output_block_reason: null, input_passed: true, output_passed: true, backend: "groq", model: "llama-3.3-70b-versatile", latency_ms: 212, input_tokens: 180, output_tokens: 240, tokens_total: 420, created_at: "2026-10-13T12:10:00Z" };
export const dashboard = { summary: { total_requests: 1248, delivered: 1134, input_blocked: 82, output_blocked: 14, rate_limited: 10, error_count: 8, block_rate_pct: 8.49, avg_latency_ms: 246.8, total_tokens: 428600, estimated_cost_usd: 3.2 }, time_series: Array.from({ length: 7 }, (_, index) => ({ ts: `2026-10-${String(index + 7).padStart(2, "0")}`, total: 120 + index * 20, delivered: 110 + index * 17, blocked: 10 + index * 3 })), top_rules: [{ rule: "prompt_injection", count: 46 }, { rule: "pii_detected", count: 24 }], provider_usage: [{ backend: "groq", model: "llama-3.3-70b-versatile", count: 820, tokens: 305000 }, { backend: "openai", model: "gpt-4o-mini", count: 314, tokens: 123600 }], recent_suspicious: [{ ...log, id: "suspicious-1", status: "input_blocked", input_passed: false, output_passed: false, prompt_preview: "Ignore previous instructions…", reason: "Prompt injection detected", fired_rule: "prompt_injection" }], recent_logs: [log] };
export const memory = { id: "memory-1", title: "Response style", content: "Prefer concise explanations with concrete examples.", category: "preference", kind: "semantic", confidence: .95, importance: 3, pinned: true, archived: false, source_type: "manual", source_id: null, created_at: "2026-10-13T10:00:00Z", updated_at: "2026-10-13T10:00:00Z", last_accessed: null };
export const key = { id: "key-1", name: "Application gateway", key_prefix: "grg_demo", scopes: ["chat"], expires_at: null, is_active: true, created_at: "2026-10-01T10:00:00Z", last_used_at: "2026-10-13T10:00:00Z", user_id: "ui-user", total_requests: 124, total_blocked: 6 };
export const skill = { slug: "agent_b", name: "Support agent", description: "Summarize public documentation safely.", version: 2, hash: "aabbccddeeff", full_hash: "a".repeat(64), update_mode: "overwrite", updated_at: "2026-10-13T10:00:00Z", created_at: "2026-10-01T10:00:00Z", content_preview: "# Support agent\nSummarize public documentation.", content: "# Support agent\nSummarize public documentation." };
export const member = { ...user, tokens_used: 18000, tokens_balance: 82000, total_requests: 124, total_blocked: 6, api_keys_count: 1 };
export const fixtureMetrics = { recall_leak: 1, precision_safe: 1, f1: 1, severity_calibration: 1, latency_p50_ms: 1.5, latency_p95_ms: 3.2, bump_accuracy: 1, hash_integrity: 1, mode_adherence: 1, safe_total: 2, leak_total: 7, tp: 7, tn: 2, fp: 0, fn: 0, details: [{ fixture: "clean-skill.md", expected: "safe", has_conflict: false }, { fixture: "leak-skill.md", expected: "leak", has_conflict: true }] };
type MockResponse = { status?: number; json?: unknown; body?: string; contentType?: string };
export type RecordedRequest = { path: string; method: string; body: any; authorization: string | undefined };
export async function mockWorkspace(page: Page, options: { admin?: boolean; empty?: boolean; override?: (request: RecordedRequest, raw: Request) => MockResponse | undefined | Promise<MockResponse | undefined> } = {}) {
  await page.addInitScript(() => localStorage.setItem("access_token", "ui-test-token"));
  const requests: RecordedRequest[] = [], unknown: string[] = [];
  let activeUser = { ...user, is_admin: options.admin !== false }, activeOrg = { ...org }, activePolicy = structuredClone(policy);
  let memories = options.empty ? [] : [{ ...memory }], keys = options.empty ? [] : [{ ...key }];
  let teams = options.empty ? [] : [{ ...org }, { ...org, id: "ui-org-2", name: "Research team", slug: "research" }];
  let revoked = false, minted = 0;
  await page.routeWebSocket("**/live-feed/websocket*", socket => socket.close());
  await page.route("**/*", async route => {
    const raw = route.request(), url = new URL(raw.url()), path = url.pathname, method = raw.method();
    if (!/^\/(auth|analytics|chat|feedback|billing|org|policy|admin|memories|skills|api-keys|health|mandate|runs|references|gateway)(\/|$)/.test(path)) {
      if (/posthog|sentry/i.test(url.hostname)) return route.abort();
      return route.continue();
    }
    const headers = { "access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "GET,POST,PATCH,PUT,DELETE,OPTIONS" };
    if (method === "OPTIONS") return route.fulfill({ status: 204, headers });
    let body: any = null; try { body = raw.postDataJSON(); } catch { /* GET/download. */ }
    const request = { path: path + url.search, method, body, authorization: raw.headers().authorization }; requests.push(request);
    const custom = await options.override?.(request, raw);
    if (custom) return route.fulfill({ status: custom.status ?? 200, headers, ...(custom.body !== undefined ? { body: custom.body, contentType: custom.contentType || "text/plain" } : { json: custom.json ?? {} }) });
    let json: any;
    if (path === "/auth/me") json = activeUser;
    else if (path === "/auth/profile") { activeUser = { ...activeUser, ...body }; json = activeUser; }
    else if (path === "/auth/change-password") json = { message: "Password updated." };
    else if (path === "/policy/validate-rego") json = { valid: true, error: null };
    else if (path === "/policy/reset") { activePolicy = structuredClone(policy); json = activePolicy; }
    else if (path === "/policy") { if (method === "PATCH") activePolicy = { ...activePolicy, ...body, version: activePolicy.version + 1 }; json = activePolicy; }
    else if (path === "/analytics/dashboard") json = options.empty ? { ...dashboard, summary: { ...dashboard.summary, total_requests: 0, delivered: 0, input_blocked: 0, output_blocked: 0, rate_limited: 0, error_count: 0, total_tokens: 0, estimated_cost_usd: 0, block_rate_pct: 0, avg_latency_ms: 0 }, time_series: [], top_rules: [], provider_usage: [], recent_suspicious: [], recent_logs: [] } : dashboard;
    else if (path === "/analytics/users") json = options.empty ? [] : [{ id: user.id, user_id: user.id, email: user.email, full_name: user.full_name, requests: 124, total_requests: 124, total_tokens: 18000, tokens_used_lifetime: 18000, tokens_balance: 82000, input_tokens: 8000, output_tokens: 10000, delivered: 118, blocked: 6, avg_latency_ms: 212 }];
    else if (path === "/analytics/logs") json = { total: options.empty ? 0 : 1, items: options.empty ? [] : [log], page: Number(url.searchParams.get("page") || 1), page_size: 25 };
    else if (path === "/analytics/export") return route.fulfill({ headers, contentType: "text/csv", body: "request_id,status\nreq-ui-1,delivered\n" });
    else if (path === "/org/export") json = { total: options.empty ? 0 : 1, items: options.empty ? [] : [log] };
    else if (path === "/org/list") json = teams;
    else if (path === "/org/switch") { activeOrg = teams.find(team => team.id === body.org_id) || activeOrg; activeUser.org_id = activeOrg.id; json = activeOrg; }
    else if (path === "/org/leave") { activeUser.org_id = "ui-org-2"; json = { message: "Left team" }; }
    else if (path === "/org") { if (method === "PATCH") activeOrg = { ...activeOrg, ...body }; if (method === "POST") { activeOrg = { ...org, id: "ui-org-new", name: body.name || "Team 3" }; teams.push(activeOrg); activeUser.org_id = activeOrg.id; } json = activeOrg; }
    else if (/^\/org\/[^/]+$/.test(path)) { if (method === "DELETE") teams = teams.filter(team => team.id !== path.split("/").at(-1)); else teams = teams.map(team => team.id === path.split("/").at(-1) ? { ...team, ...body } : team); json = teams.find(team => team.id === path.split("/").at(-1)) || { message: "Deleted" }; }
    else if (path === "/api-keys") { if (method === "POST") { const created = { ...key, ...body, id: "key-new" }; keys.push(created); json = { ...created, raw_key: "grg_ui_test_only_key_value" }; } else json = keys; }
    else if (/^\/api-keys\/[^/]+$/.test(path)) { keys = keys.map(item => item.id === path.split("/").at(-1) ? { ...item, is_active: false } : item); json = null; }
    else if (path === "/billing/wallet") json = { balance_tokens: 82000, tokens_used_lifetime: 18000, tokens_purchased_lifetime: 100000, billing_enabled: true, unlimited: false };
    else if (path === "/billing/plans") json = [{ slug: "starter", name: "Starter", tokens: 100000, price_cents: 500, currency: "usd", description: "A small token pack for your next project.", popular: false, price_display: "$5.00" }, { slug: "builder", name: "Builder", tokens: 500000, price_cents: 2000, currency: "usd", description: "More room to build and test.", popular: true, price_display: "$20.00" }];
    else if (path === "/billing/purchases") json = options.empty ? [] : [{ id: "purchase-1", plan_slug: "starter", tokens_granted: 100000, amount_cents: 500, currency: "usd", status: "completed", created_at: "2026-10-01T10:00:00Z", completed_at: "2026-10-01T10:00:01Z" }];
    else if (path === "/billing/config") json = { billing_enabled: true, free_signup_tokens: 10000, stripe_configured: false, stripe_publishable_key: null };
    else if (path === "/billing/checkout") json = { checkout_url: null, purchase_id: "purchase-test", message: "Test checkout credited." };
    else if (path === "/admin/users/stats") json = options.empty ? [] : [member, { ...member, id: "ui-user-2", email: "sam@example.com", full_name: "Sam Taylor", is_admin: false, last_login: null }];
    else if (path === "/admin/api-keys") json = options.empty ? [] : keys;
    else if (path === "/admin/bans") json = [];
    else if (path === "/admin/users/lookup") json = { ...user, id: "ui-user-3", email: url.searchParams.get("email"), full_name: "Invited User", is_admin: false };
    else if (path.startsWith("/admin/")) json = { ...user, ...body, message: "Updated" };
    else if (path === "/memories/stats") json = { total: memories.length, pinned: memories.filter(item => item.pinned).length, by_category: { preference: memories.length } };
    else if (path === "/memories/recall") json = { query: body.query, memories };
    else if (path === "/memories/extract/preview") json = { candidates: [{ title: "Communication preference", content: "Use concrete examples.", category: "preference", confidence: .9, importance: 3 }] };
    else if (path === "/memories/extract/confirm") { json = body.items.map((item: any, index: number) => ({ ...memory, ...item, id: "extracted-" + index })); memories.push(...json); }
    else if (path === "/memories") { if (method === "POST") { json = { ...memory, ...body, id: "memory-new" }; memories.push(json); } else json = memories.filter(item => (!url.searchParams.get("q") || (item.title + item.content).toLowerCase().includes(url.searchParams.get("q")!.toLowerCase())) && (!url.searchParams.get("category") || item.category === url.searchParams.get("category")) && (url.searchParams.get("pinned_only") !== "true" || item.pinned)); }
    else if (/^\/memories\/[^/]+$/.test(path)) { const id = path.split("/").at(-1); if (method === "DELETE") { memories = memories.filter(item => item.id !== id); json = null; } else { memories = memories.map(item => item.id === id ? { ...item, ...body } : item); json = memories.find(item => item.id === id); } }
    else if (path === "/skills/managed/metrics") json = fixtureMetrics;
    else if (path === "/skills/managed/metrics/combined") json = { macro_f1: .94, sample_per_dataset: 150, measured: true };
    else if (path === "/skills/managed/metrics/export-pdf") return route.fulfill({ headers, contentType: "application/pdf", body: "%PDF-1.4\n% synthetic UI test download\n" });
    else if (path === "/skills/managed") json = options.empty ? [] : [skill];
    else if (path === "/skills/rejections") json = [];
    else if (path === "/skills/scan") json = { safe: true, risk_score: 0, findings: [], line_count: body.content.split("\n").length, char_count: body.content.length, filename: body.filename, blocked: false, agent_may_continue: true, agent_status: "ok", blocking_findings: [] };
    else if (path.includes("check-conflict")) json = { has_conflict: false, conflicts: [], summary: "No conflicts found" };
    else if (path.includes("check-identical-block")) json = { identical: false, already_blocked: false, matches: [] };
    else if (/^\/skills\/managed\/[^/]+$/.test(path)) json = skill;
    else if (path === "/health") json = { status: "ok", env: "production", backend: "groq", database: "ok" };
    else if (path === "/health/detailed") json = { overall: "ok", database: { status: "ok", latency_ms: 4.2 }, redis: { status: "ok", latency_ms: 1.3 }, vectorstore: { status: "not_configured" } };
    else if (path === "/health/breakers") json = { overall: "ok", breakers: { groq: "closed", openai: "closed" } };
    else if (path === "/mandate/bench") json = { iterations: 100, go_available: true, python_ms: 42, go_ms: 20, speedup_go_vs_python: 2.1 };
    else if (path === "/mandate") { revoked = false; json = { id: "mandate-ui-1", policy_context: { pinned_rule: "NO_PAYMENT_REIDENTIFICATION" } }; }
    else if (path.endsWith("/revoke")) { revoked = true; json = { revoked: true }; }
    else if (path === "/runs" || path.endsWith("/retry")) json = { run_id: "run-ui-1", mandate_id: "mandate-ui-1", runtime_id: "python", capability: "test-fixture-capability" };
    else if (path.endsWith("/evidence")) json = { crmCounter: 2, decisions: 10, receipts: [] };
    else if (path === "/references/mint") json = { handle: body.kind === "payment_case" ? "payment-handle" : "support-handle-" + ++minted, provenance: body.provenance || "SUPPORT" };
    else if (path === "/gateway/call") { if (revoked) return route.fulfill({ status: 401, headers, json: { detail: "Capability revoked" } }); json = body.tool === "crm.resolve_customer" && body.handle === "payment-handle" ? { decision: "DENY", ruleId: "NO_PAYMENT_REIDENTIFICATION" } : { decision: "ALLOW" }; }
    else if (path === "/feedback") json = { message: "Feedback received" };
    else { unknown.push(method + " " + path); return route.fulfill({ status: 501, headers, json: { detail: "UI fixture missing for " + path } }); }
    await route.fulfill({ status: json === null ? 204 : 200, headers, ...(json === null ? {} : { json }) });
  });
  return { requests, unknown };
}
