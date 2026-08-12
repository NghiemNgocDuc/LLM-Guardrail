# All secrets are sensitive = true. Provide real values in terraform.tfvars
# (gitignored) or via TF_VAR_* environment variables — never commit them.

# ---------------------------------------------------------------------------
# Provider credentials
# ---------------------------------------------------------------------------

variable "render_api_key" {
  description = "Render API key (https://dashboard.render.com/u/settings#api-keys). Stored encrypted by Render."
  type        = string
  sensitive   = true
}

variable "render_owner_id" {
  description = "Render owner/team ID — the personal or team account that owns the services (dashboard URL /u/settings#owner-id)."
  type        = string
}

variable "upstash_api_key" {
  description = "Upstash REST API key (https://console.upstash.com/account/api)."
  type        = string
  sensitive   = true
}

variable "upstash_email" {
  description = "Upstash account email (required by the provider alongside the API key)."
  type        = string
}

# ---------------------------------------------------------------------------
# Render web service (Dockerfile.fullstack — serves both API and web UI)
# ---------------------------------------------------------------------------

variable "service_name" {
  description = "Render service name; becomes the public subdomain <name>.onrender.com."
  type        = string
  default     = "llm-guardrails"
}

variable "repo_url" {
  description = "GitHub repository URL Render deploys from (e.g. https://github.com/you/llm_guardrails_v2_wired)."
  type        = string
}

variable "branch" {
  description = "Git branch Render deploys from."
  type        = string
  default     = "main"
}

variable "render_plan" {
  description = "Render plan for the web service (starter = free tier)."
  type        = string
  default     = "starter"
}

variable "render_region" {
  description = "Render region for the web service (Render default: oregon)."
  type        = string
  default     = "oregon"
}

variable "auto_deploy" {
  description = "Automatically redeploy on new commits to `branch` (Render default)."
  type        = bool
  default     = true
}

variable "dockerfile_path" {
  description = "Path to the Dockerfile Render builds. Defaults to the fullstack image that serves API + web UI together (render.yaml, fly.toml)."
  type        = string
  default     = "Dockerfile.fullstack"
}

variable "health_check_path" {
  description = "Render health check path — mirrors DEPLOYMENT.md post-deploy check curl /health."
  type        = string
  default     = "/health"
}

variable "public_url_override" {
  description = "Override for PUBLIC_APP_URL/ALLOWED_ORIGINS if Render assigns a suffixed subdomain (name collision) or you attach a custom domain manually. Empty = https://<service_name>.onrender.com."
  type        = string
  default     = ""
}

# ---------------------------------------------------------------------------
# Database — Supabase Postgres (external dependency, no official provider)
# ---------------------------------------------------------------------------

variable "supabase_database_url" {
  description = "Supabase pooler connection string, postgresql+asyncpg://... (DEPLOYMENT.md §Supabase Postgres). Either this or the POSTGRES_* pair is required in production."
  type        = string
  default     = ""
  sensitive   = true
}

variable "postgres_user" {
  description = "POSTGRES_USER as shown in render.yaml (Supabase user)."
  type        = string
  default     = ""
}

variable "postgres_password" {
  description = "POSTGRES_PASSWORD — SECURITY.md required production secret."
  type        = string
  default     = ""
  sensitive   = true
}

variable "postgres_db" {
  description = "POSTGRES_DB (Supabase database name)."
  type        = string
  default     = ""
}

variable "postgres_host" {
  description = "POSTGRES_HOST (Supabase pooler host)."
  type        = string
  default     = ""
}

variable "postgres_port" {
  description = "POSTGRES_PORT — render.yaml pins this to the Supabase pooler port 6543."
  type        = string
  default     = "6543"
}

# ---------------------------------------------------------------------------
# Cache — Upstash Redis (provisioned by modules/cache)
# ---------------------------------------------------------------------------

variable "redis_database_name" {
  description = "Upstash Redis database name."
  type        = string
  default     = "llm-guardrails-redis"
}

variable "redis_region" {
  description = "Upstash Redis region (e.g. us-east-1, eu-west-1)."
  type        = string
  default     = "us-east-1"
}

variable "redis_tls" {
  description = "Use the TLS (rediss://) endpoint, as recommended by DEPLOYMENT.md."
  type        = bool
  default     = true
}

# ---------------------------------------------------------------------------
# Application (app/config.py Settings fields; non-secret, render.yaml values)
# ---------------------------------------------------------------------------

variable "log_level" {
  description = "LOG_LEVEL (render.yaml sets INFO)."
  type        = string
  default     = "INFO"
}

variable "default_llm_backend" {
  description = "DEFAULT_LLM_BACKEND — render.yaml pins anthropic."
  type        = string
  default     = "anthropic"
}

variable "default_model" {
  description = "DEFAULT_MODEL — render.yaml pins claude-sonnet-4-20250514."
  type        = string
  default     = "claude-sonnet-4-20250514"
}

variable "llm_failover_backends" {
  description = "LLM_FAILOVER_BACKENDS — optional comma-separated failover order (config.py)."
  type        = string
  default     = ""
}

variable "pinecone_environment" {
  description = "PINECONE_ENVIRONMENT (render.yaml: us-east-1)."
  type        = string
  default     = "us-east-1"
}

variable "pinecone_index_name" {
  description = "PINECONE_INDEX_NAME (render.yaml: guardrails)."
  type        = string
  default     = "guardrails"
}

variable "billing_enabled" {
  description = "BILLING_ENABLED (render.yaml: true)."
  type        = bool
  default     = true
}

variable "free_signup_tokens" {
  description = "FREE_SIGNUP_TOKENS (render.yaml: 10000)."
  type        = number
  default     = 10000
}

# ---------------------------------------------------------------------------
# Application secrets (SECURITY.md list + render.yaml sync:false entries)
# ---------------------------------------------------------------------------

variable "secret_key" {
  description = "SECRET_KEY — SECURITY.md required production secret. Generate with `python -c \"import secrets; print(secrets.token_urlsafe(48))\"` (DEPLOYMENT.md)."
  type        = string
  sensitive   = true
}

variable "groq_api_key" {
  description = "GROQ_API_KEY — SECURITY.md required production secret (or the key of your selected LLM backend)."
  type        = string
  default     = ""
  sensitive   = true
}

variable "openai_api_key" {
  description = "OPENAI_API_KEY (render.yaml sync:false)."
  type        = string
  default     = ""
  sensitive   = true
}

variable "anthropic_api_key" {
  description = "ANTHROPIC_API_KEY (render.yaml sync:false)."
  type        = string
  default     = ""
  sensitive   = true
}

variable "gemini_api_key" {
  description = "GEMINI_API_KEY (render.yaml sync:false)."
  type        = string
  default     = ""
  sensitive   = true
}

variable "pinecone_api_key" {
  description = "PINECONE_API_KEY (render.yaml sync:false)."
  type        = string
  default     = ""
  sensitive   = true
}

variable "clerk_secret_key" {
  description = "CLERK_SECRET_KEY (render.yaml sync:false)."
  type        = string
  default     = ""
  sensitive   = true
}

variable "clerk_jwks_url" {
  description = "CLERK_JWKS_URL (render.yaml sync:false)."
  type        = string
  default     = ""
}

variable "clerk_webhook_secret" {
  description = "CLERK_WEBHOOK_SECRET (render.yaml sync:false)."
  type        = string
  default     = ""
  sensitive   = true
}

variable "clerk_jwt_key" {
  description = "CLERK_JWT_KEY — optional PEM public key (render.yaml sync:false)."
  type        = string
  default     = ""
  sensitive   = true
}

variable "billing_unlimited_emails" {
  description = "BILLING_UNLIMITED_EMAILS — comma-separated emails exempt from billing (render.yaml sync:false)."
  type        = string
  default     = ""
  sensitive   = true
}

variable "stripe_secret_key" {
  description = "STRIPE_SECRET_KEY (render.yaml sync:false)."
  type        = string
  default     = ""
  sensitive   = true
}

variable "stripe_webhook_secret" {
  description = "STRIPE_WEBHOOK_SECRET (render.yaml sync:false)."
  type        = string
  default     = ""
  sensitive   = true
}

variable "stripe_publishable_key" {
  description = "STRIPE_PUBLISHABLE_KEY (render.yaml sync:false)."
  type        = string
  default     = ""
  sensitive   = true
}

# ---------------------------------------------------------------------------
# Email / SMTP (DEPLOYMENT.md §Email)
# ---------------------------------------------------------------------------

variable "smtp_host" {
  description = "SMTP_HOST (DEPLOYMENT.md: e.g. smtp.resend.com). Verification is auto-disabled when unset."
  type        = string
  default     = ""
}

variable "smtp_port" {
  description = "SMTP_PORT (DEPLOYMENT.md: 587)."
  type        = number
  default     = 587
}

variable "smtp_user" {
  description = "SMTP_USER (DEPLOYMENT.md: resend)."
  type        = string
  default     = ""
}

variable "smtp_password" {
  description = "SMTP_PASSWORD (DEPLOYMENT.md §Email)."
  type        = string
  default     = ""
  sensitive   = true
}

variable "smtp_from" {
  description = "SMTP_FROM (DEPLOYMENT.md: 'LLM Guardrail <onboarding@yourdomain.com>')."
  type        = string
  default     = ""
}

variable "smtp_use_tls" {
  description = "SMTP_USE_TLS (DEPLOYMENT.md: true)."
  type        = bool
  default     = true
}

variable "require_email_verification" {
  description = "REQUIRE_EMAIL_VERIFICATION — only applied when SMTP_HOST and SMTP_FROM are set (DEPLOYMENT.md)."
  type        = bool
  default     = true
}

# ---------------------------------------------------------------------------
# Demo mode (DEPLOYMENT.md §Public Demo Rate Limits)
# ---------------------------------------------------------------------------

variable "demo_mode" {
  description = "DEMO_MODE — enable rate-limited public demo mode."
  type        = bool
  default     = false
}

variable "demo_disable_signups" {
  description = "DEMO_DISABLE_SIGNUPS."
  type        = bool
  default     = false
}

variable "demo_rate_limit_rpm" {
  description = "DEMO_RATE_LIMIT_RPM (DEPLOYMENT.md suggested start: 3)."
  type        = number
  default     = 3
}

variable "demo_rate_limit_rpd" {
  description = "DEMO_RATE_LIMIT_RPD (DEPLOYMENT.md suggested start: 20)."
  type        = number
  default     = 20
}

variable "demo_ip_rate_limit_rpm" {
  description = "DEMO_IP_RATE_LIMIT_RPM (DEPLOYMENT.md suggested start: 10)."
  type        = number
  default     = 10
}

variable "demo_ip_rate_limit_rpd" {
  description = "DEMO_IP_RATE_LIMIT_RPD (DEPLOYMENT.md suggested start: 50)."
  type        = number
  default     = 50
}

variable "demo_max_prompt_chars" {
  description = "DEMO_MAX_PROMPT_CHARS (DEPLOYMENT.md: 2000)."
  type        = number
  default     = 2000
}

variable "demo_max_output_tokens" {
  description = "DEMO_MAX_OUTPUT_TOKENS (DEPLOYMENT.md: 2048)."
  type        = number
  default     = 2048
}
