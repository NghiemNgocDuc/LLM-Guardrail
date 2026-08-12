# Supabase Postgres — EXTERNAL dependency (DEPLOYMENT.md §Supabase Postgres).
#
# No official Terraform provider exists for Supabase, so the project itself
# is created manually in the Supabase dashboard (DEPLOYMENT.md steps 1–3) and
# its pooler connection string is supplied as a sensitive input. This module
# validates the value, mirrors the render.yaml POSTGRES_* variables, and
# re-emits the environment the app expects (config.py:normalize_database_url).
#
# Either database_url or the POSTGRES_* component pair must be set; production
# startup fails without a usable DATABASE_URL (config.py:validate_production_config).

locals {
  postgres_component_env = merge(
    var.postgres_user != "" ? { "POSTGRES_USER" = var.postgres_user } : {},
    var.postgres_password != "" ? { "POSTGRES_PASSWORD" = var.postgres_password } : {},
    var.postgres_db != "" ? { "POSTGRES_DB" = var.postgres_db } : {},
    var.postgres_host != "" ? { "POSTGRES_HOST" = var.postgres_host } : {},
    var.postgres_port != "" ? { "POSTGRES_PORT" = var.postgres_port } : {},
  )

  database_url_env = var.database_url != "" ? { "DATABASE_URL" = var.database_url } : {}

  database_env = merge(local.database_url_env, local.postgres_component_env)
}

output "database_env" {
  description = "DATABASE_URL and/or POSTGRES_* map to merge into the service environment."
  value       = local.database_env
  sensitive   = true
}
