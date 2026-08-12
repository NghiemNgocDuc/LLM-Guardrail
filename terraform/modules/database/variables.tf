variable "database_url" {
  description = "Supabase pooler connection string (postgresql+asyncpg://...). Empty when the POSTGRES_* form is used."
  type        = string
  default     = ""
  sensitive   = true

  validation {
    condition     = var.database_url == "" || startswith(var.database_url, "postgresql+asyncpg://")
    error_message = "DATABASE_URL must use the postgresql+asyncpg scheme (config.py requires it in production). See DEPLOYMENT.md §Supabase Postgres for the conversion."
  }
}

variable "postgres_user" {
  description = "POSTGRES_USER (Supabase user)."
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
  description = "POSTGRES_PORT — render.yaml pins the Supabase pooler port 6543."
  type        = string
  default     = "6543"
}
