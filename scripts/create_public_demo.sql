-- Public demo account seed for Supabase.
-- Run only against the demo deployment database.
-- This account is intentionally public and must never be used for real data.

create extension if not exists pgcrypto;

-- Ensure budget columns exist even if alembic migration 0016_api_key_budgets
-- hasn't been applied (e.g. pasting this seed directly in Supabase SQL Editor).
-- Must be top-level DDL — if placed inside DO $$, later INSERTs in the same
-- block are planned before the ALTER runs and fail with 42703.
alter table api_keys add column if not exists budget_tokens bigint;
alter table api_keys add column if not exists budget_used bigint not null default 0;
alter table api_keys add column if not exists budget_reset_at timestamptz;

do $$
declare
    demo_org_id uuid;
    demo_user_id uuid;
    demo_key_id uuid;
begin
    select id into demo_org_id from organizations where slug = 'public-demo';
    if demo_org_id is null then
        demo_org_id := gen_random_uuid();
        insert into organizations (id, name, slug, created_at)
        values (demo_org_id, 'Public Demo Workspace', 'public-demo', now());
    end if;

    insert into org_policies (id, org_id, input_rules, output_rules, topic_policy, compliance_rules, updated_at)
    values (
        gen_random_uuid(), demo_org_id,
        '{"block_secrets": true, "block_pii": true, "block_prompt_injection": true, "block_jailbreak": true}'::jsonb,
        '{"enforce_schema": false, "block_toxic_content": true}'::jsonb,
        '{"blocked_topics": ["medical advice"]}'::jsonb,
        '{"block_medical_advice": true}'::jsonb,
        now()
    )
    on conflict (org_id) do nothing;

    select id into demo_user_id from users where email = 'demo@example.com';
    if demo_user_id is null then
        demo_user_id := gen_random_uuid();
        insert into users (id, email, hashed_password, full_name, is_active, is_admin, email_verified, org_id, created_at)
        values (
            demo_user_id,
            'demo@example.com',
            crypt('Demo-Guardrails-2026!', gen_salt('bf', 12)),
            'Public Demo Admin',
            true, true, true, demo_org_id, now()
        );
    else
        update users
        set hashed_password = crypt('Demo-Guardrails-2026!', gen_salt('bf', 12)),
            full_name = 'Public Demo Admin', is_active = true, is_admin = true,
            email_verified = true, org_id = demo_org_id
        where id = demo_user_id;
    end if;

    insert into token_wallets (user_id, balance_tokens, tokens_used_lifetime, tokens_purchased_lifetime, updated_at)
    values (demo_user_id, 10000, 0, 0, now())
    on conflict (user_id) do nothing;

    select id into demo_key_id from api_keys where name = 'Public demo key' and owner_id = demo_user_id;
    if demo_key_id is null then
        -- Use dynamic SQL so this statement is parsed at runtime, after the
        -- top-level ALTER TABLEs have created the budget_* columns if needed.
        -- Without EXECUTE, PL/pgSQL would plan this INSERT at block entry
        -- and fail with 42703 when migration 0016_api_key_budgets hasn't run.
        execute format(
            'insert into api_keys (id, name, key_prefix, key_hash, is_active, owner_id, org_id, '
            'scopes, budget_tokens, budget_used, total_requests, total_blocked, total_tokens, created_at) '
            'values (gen_random_uuid(), %L, %L, crypt(%L, gen_salt(%L, 12)), true, %L, %L, %L::jsonb, 10000, 0, 0, 0, 0, now())',
            'Public demo key', 'grg_demo_pub', 'grg_demo_public_key_2026_replace_me', 'bf',
            demo_user_id, demo_org_id, '["chat"]'
        );
    end if;
end $$;

select email, full_name, is_admin, email_verified
from users
where email = 'demo@example.com';

-- Public demo login:
-- Email: demo@example.com
-- Password: Demo-Guardrails-2026!
-- Gateway key: grg_demo_public_key_2026_replace_me
