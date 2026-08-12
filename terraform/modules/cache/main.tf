# Upstash Redis — shared rate-limiting store (DEPLOYMENT.md §Upstash Redis).
#
# Provisioned with the official Upstash Terraform provider. The module emits
# RATE_LIMIT_REDIS_URL in the rediss:// form DEPLOYMENT.md documents, using the
# TLS endpoint and the database's computed port (the app accepts both redis://
# and rediss://).

terraform {
  required_providers {
    upstash = {
      source = "upstash/upstash"
    }
  }
}

resource "upstash_redis_database" "this" {
  database_name = var.name
  tls           = var.tls
  region        = var.region
}

locals {
  # The provider returns the REST-style endpoint (https://<host>); the TCP/rediss
  # host is the same <host>. Strip any scheme so it composes into the URI.
  tcp_host = try(
    regex("^(?:https?|rediss?)://([^/]+)", upstash_redis_database.this.endpoint)[0],
    upstash_redis_database.this.endpoint
  )

  # DEPLOYMENT.md: rediss://:<password>@<host>:<port> — password is
  # url-encoded so it survives in the URI regardless of special characters.
  redis_url = "rediss://:${urlencode(upstash_redis_database.this.password)}@${local.tcp_host}:${upstash_redis_database.this.port}"
}

output "redis_url" {
  description = "RATE_LIMIT_REDIS_URL (rediss://) for the app."
  value       = local.redis_url
  sensitive   = true
}

output "redis_url_env" {
  description = "Map form ({ RATE_LIMIT_REDIS_URL = ... }) for the service environment."
  value       = { RATE_LIMIT_REDIS_URL = local.redis_url }
  sensitive   = true
}

output "database_id" {
  description = "Upstash Redis database ID."
  value       = upstash_redis_database.this.id
}

output "database_name" {
  description = "Upstash Redis database name."
  value       = upstash_redis_database.this.database_name
}
