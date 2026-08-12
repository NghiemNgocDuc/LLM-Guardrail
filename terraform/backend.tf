# Remote state — Terraform Cloud.
#
# Chosen over an S3-compatible bucket because this project has no existing
# cloud-storage presence (it is Render + Upstash + Supabase only), so a bucket
# would itself be infrastructure that needs bootstrapping. Terraform Cloud
# provides encrypted state, locking, and a free tier; it also gives a natural
# home for CI-driven `terraform plan` on pull requests later.
#
# The organization is deliberately NOT committed. Initialize with:
#
#   terraform init -backend-config="organization=YOUR-ORG"
#
# (or edit this block locally and never commit your edit). Workspace:
# llm-guardrails-production. CI runs `terraform init -backend=false` so
# fmt/validate work without a Terraform Cloud token.
terraform {
  backend "remote" {
    hostname = "app.terraform.io"
    workspaces {
      name = "llm-guardrails-production"
    }
  }
}
