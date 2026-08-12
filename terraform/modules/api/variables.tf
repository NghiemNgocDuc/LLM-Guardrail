variable "name" {
  description = "Render service name (becomes the public subdomain)."
  type        = string
}

variable "public_url_override" {
  description = "Override for the public URL when Render assigns a suffixed subdomain (name collision) or a custom domain is attached manually."
  type        = string
  default     = ""
}

variable "repo_url" {
  description = "GitHub repository URL Render deploys from."
  type        = string
}

variable "branch" {
  description = "Git branch Render deploys from."
  type        = string
  default     = "main"
}

variable "plan" {
  description = "Render plan (starter = free tier)."
  type        = string
  default     = "starter"
}

variable "region" {
  description = "Render region (default: oregon)."
  type        = string
  default     = "oregon"
}

variable "auto_deploy" {
  description = "Automatically redeploy on new commits to `branch`."
  type        = bool
  default     = true
}

variable "dockerfile_path" {
  description = "Dockerfile to build (defaults to the fullstack image)."
  type        = string
  default     = "Dockerfile.fullstack"
}

variable "health_check_path" {
  description = "Health check path (app serves /health)."
  type        = string
  default     = "/health"
}

variable "env_vars" {
  description = "Environment variables for the service — app/config.py Settings field names (sensitive values included)."
  type        = map(string)
  sensitive   = true
}
