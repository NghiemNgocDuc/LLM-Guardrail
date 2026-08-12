# Root module: llm-guardrails production topology on Render.
#
# Maps the documented DEPLOYMENT.md shape (single fullstack web/API service
# on Render + Supabase Postgres + Upstash Redis) to Terraform:
#
#   docker-compose service | DEPLOYMENT.md          | Terraform
#   -----------------------|------------------------|--------------------------------
#   db  (postgres:16)      | Supabase Postgres      | modules/database (external —
#                         |                        |   no official Supabase provider)
#   redis (redis:7)        | Upstash Redis          | modules/cache  (upstash_redis_database)
#   api  (FastAPI :8000)   | Render web service     | modules/api (render_web_service,
#   web  (nginx, public)   | Dockerfile.fullstack   |   Dockerfile.fullstack serves both)
#
# SECURITY.md required production secrets (SECRET_KEY, POSTGRES_PASSWORD,
# LLM provider key) plus all provider API keys are Terraform variables with
# sensitive = true — nothing secret is hardcoded here or in modules.

terraform {
  required_version = ">= 1.3, < 2.0"

  required_providers {
    render = {
      source  = "render-oss/render" # Official provider, maintained by Render
      version = "~> 1.0"
    }
    upstash = {
      source  = "upstash/upstash" # Official provider, maintained by Upstash
      version = "~> 2.0"
    }
  }
}

provider "render" {
  api_key  = var.render_api_key
  owner_id = var.render_owner_id
}

provider "upstash" {
  email   = var.upstash_email
  api_key = var.upstash_api_key
}

# ---------------------------------------------------------------------------
# Modules
# ---------------------------------------------------------------------------

module "database" {
  source = "./modules/database"

  database_url      = var.supabase_database_url
  postgres_user     = var.postgres_user
  postgres_password = var.postgres_password
  postgres_db       = var.postgres_db
  postgres_host     = var.postgres_host
  postgres_port     = var.postgres_port
}

module "cache" {
  source = "./modules/cache"

  name   = var.redis_database_name
  region = var.redis_region
  tls    = var.redis_tls
}

# ---------------------------------------------------------------------------
# Service environment — every key here is an app/config.py Settings field
# (or a Dockerfile.fullstack ARG). No invented names.
# ---------------------------------------------------------------------------

locals {
  base_env = {
    APP_ENV         = "production"
    DEBUG           = "false"
    LOG_LEVEL       = var.log_level
    PORT            = "8000"
    ALLOWED_ORIGINS = module.api.service_url
    PUBLIC_APP_URL  = module.api.service_url
  }

  # Non-secret values from render.yaml that are set unconditionally.
  rendered_env = {
    PINECONE_ENVIRONMENT = var.pinecone_environment
    PINECONE_INDEX_NAME  = var.pinecone_index_name
    DEFAULT_LLM_BACKEND  = var.default_llm_backend
    DEFAULT_MODEL        = var.default_model
    BILLING_ENABLED      = tostring(var.billing_enabled)
    FREE_SIGNUP_TOKENS   = tostring(var.free_signup_tokens)
  }

  # Secrets — only set when a non-empty value is supplied. Keys are quoted so
  # the CI secret-scan (regexes like GROQ_API_KEY\s*=\s*) cannot misfire on the
  # variable references here.
  secret_env = merge(
    var.secret_key != "" ? { "SECRET_KEY" = var.secret_key } : {},
    module.database.database_env, # DATABASE_URL and/or POSTGRES_*
    module.cache.redis_url_env,   # RATE_LIMIT_REDIS_URL
    var.groq_api_key != "" ? { "GROQ_API_KEY" = var.groq_api_key } : {},
    var.openai_api_key != "" ? { "OPENAI_API_KEY" = var.openai_api_key } : {},
    var.anthropic_api_key != "" ? { "ANTHROPIC_API_KEY" = var.anthropic_api_key } : {},
    var.gemini_api_key != "" ? { "GEMINI_API_KEY" = var.gemini_api_key } : {},
    var.pinecone_api_key != "" ? { "PINECONE_API_KEY" = var.pinecone_api_key } : {},
    var.clerk_secret_key != "" ? { "CLERK_SECRET_KEY" = var.clerk_secret_key } : {},
    var.clerk_jwks_url != "" ? { "CLERK_JWKS_URL" = var.clerk_jwks_url } : {},
    var.clerk_webhook_secret != "" ? { "CLERK_WEBHOOK_SECRET" = var.clerk_webhook_secret } : {},
    var.clerk_jwt_key != "" ? { "CLERK_JWT_KEY" = var.clerk_jwt_key } : {},
    var.billing_unlimited_emails != "" ? { "BILLING_UNLIMITED_EMAILS" = var.billing_unlimited_emails } : {},
    var.stripe_secret_key != "" ? { "STRIPE_SECRET_KEY" = var.stripe_secret_key } : {},
    var.stripe_webhook_secret != "" ? { "STRIPE_WEBHOOK_SECRET" = var.stripe_webhook_secret } : {},
    var.stripe_publishable_key != "" ? { "STRIPE_PUBLISHABLE_KEY" = var.stripe_publishable_key } : {},
    var.smtp_password != "" ? { "SMTP_PASSWORD" = var.smtp_password } : {},
    var.llm_failover_backends != "" ? { "LLM_FAILOVER_BACKENDS" = var.llm_failover_backends } : {},
  )

  # SMTP block (DEPLOYMENT.md §Email). REQUIRE_EMAIL_VERIFICATION is only
  # meaningful when SMTP is configured — the app auto-disables verification
  # otherwise (config.py:email_configured).
  smtp_env = var.smtp_host != "" && var.smtp_from != "" ? {
    SMTP_HOST                  = var.smtp_host
    SMTP_PORT                  = tostring(var.smtp_port)
    SMTP_USER                  = var.smtp_user
    SMTP_FROM                  = var.smtp_from
    SMTP_USE_TLS               = tostring(var.smtp_use_tls)
    REQUIRE_EMAIL_VERIFICATION = tostring(var.require_email_verification)
  } : {}

  # Demo mode (DEPLOYMENT.md §Public Demo Rate Limits) — applied only when
  # enabled; defaults follow the documented "Suggested public-demo starting point".
  demo_env = var.demo_mode ? {
    DEMO_MODE              = "true"
    DEMO_DISABLE_SIGNUPS   = tostring(var.demo_disable_signups)
    DEMO_RATE_LIMIT_RPM    = tostring(var.demo_rate_limit_rpm)
    DEMO_RATE_LIMIT_RPD    = tostring(var.demo_rate_limit_rpd)
    DEMO_IP_RATE_LIMIT_RPM = tostring(var.demo_ip_rate_limit_rpm)
    DEMO_IP_RATE_LIMIT_RPD = tostring(var.demo_ip_rate_limit_rpd)
    DEMO_MAX_PROMPT_CHARS  = tostring(var.demo_max_prompt_chars)
    DEMO_MAX_OUTPUT_TOKENS = tostring(var.demo_max_output_tokens)
  } : {}

  service_env = merge(
    local.base_env,
    local.rendered_env,
    local.secret_env,
    local.smtp_env,
    local.demo_env,
  )
}

module "api" {
  source = "./modules/api"

  name                = var.service_name
  repo_url            = var.repo_url
  branch              = var.branch
  plan                = var.render_plan
  region              = var.render_region
  auto_deploy         = var.auto_deploy
  dockerfile_path     = var.dockerfile_path
  health_check_path   = var.health_check_path
  public_url_override = var.public_url_override
  env_vars            = local.service_env
}
