variable "name" {
  description = "Upstash Redis database name."
  type        = string
  default     = "llm-guardrails-redis"
}

variable "region" {
  description = "Upstash region (e.g. us-east-1, eu-west-1)."
  type        = string
  default     = "us-east-1"
}

variable "tls" {
  description = "Enable the TLS (rediss://) endpoint, as recommended by DEPLOYMENT.md."
  type        = bool
  default     = true
}
