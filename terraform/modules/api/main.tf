# Render web service — the fullstack entrypoint (render.yaml + fly.toml +
# DEPLOYMENT.md "Recommended shape").
#
# Dockerfile.fullstack builds the frontend (nginx-served static bundle) and the
# FastAPI backend into one image, so this single service plays the role of both
# the compose `api` and compose `web` services. See terraform/README.md for the
# mapping table.

terraform {
  required_providers {
    render = {
      source = "render-oss/render"
    }
  }
}

resource "render_web_service" "this" {
  name              = var.name
  plan              = var.plan
  region            = var.region
  health_check_path = var.health_check_path

  runtime_source = {
    docker = {
      repo_url        = var.repo_url
      branch          = var.branch
      dockerfile_path = var.dockerfile_path
      auto_deploy     = var.auto_deploy
    }
  }

  # The provider's env_vars attribute is a map of objects
  # ({ name = { value = ... } }); the module input stays a plain map.
  env_vars = {
    for name, value in var.env_vars : name => { value = value }
  }
}

# Render assigns the public subdomain https://<name>.onrender.com. The root
# module uses this for ALLOWED_ORIGINS/PUBLIC_APP_URL, mirroring render.yaml's
# hardcoded https://llm-guardrails.onrender.com without assuming the URL.
# The URL is deterministic (same convention render.yaml relies on) so the
# service environment does not depend on the service resource — if Render ever
# assigns a suffixed URL (name collision), set public_url_override.
locals {
  service_url = var.public_url_override != "" ? var.public_url_override : "https://${replace(var.name, "_", "-")}.onrender.com"
}

output "service_url" {
  description = "Public https URL of the service (deterministic; used for ALLOWED_ORIGINS/PUBLIC_APP_URL)."
  value       = local.service_url
}

output "service_url_assigned" {
  description = "The URL Render actually assigned (verify against service_url after first apply)."
  value       = render_web_service.this.url
}

output "service_id" {
  description = "Render web service ID."
  value       = render_web_service.this.id
}
