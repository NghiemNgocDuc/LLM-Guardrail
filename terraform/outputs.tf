output "service_url" {
  description = "Public URL of the fullstack service (used for ALLOWED_ORIGINS/PUBLIC_APP_URL and post-deploy checks)."
  value       = module.api.service_url
}

output "service_id" {
  description = "Render web service ID."
  value       = module.api.service_id
}

output "redis_database_id" {
  description = "Upstash Redis database ID."
  value       = module.cache.database_id
}

output "redis_url" {
  description = "RATE_LIMIT_REDIS_URL (rediss://) wired into the service."
  value       = module.cache.redis_url
  sensitive   = true
}

output "database_env" {
  description = "DATABASE_URL / POSTGRES_* environment wired into the service (Supabase, external)."
  value       = module.database.database_env
  sensitive   = true
}
