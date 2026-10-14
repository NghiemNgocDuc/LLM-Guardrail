// ─── Supplementary types ───────────────────────────────────────────────────────
// Shapes returned by the backend but not modeled in the OpenAPI spec (verified
// against app/routers/analytics.py and app/routers/chat.py).

export interface RequestLogItem {
  id: string;
  status: string;
  prompt_preview: string;
  full_prompt: null;
  model: string;
  backend: string;
  latency_ms: number;
  input_passed: boolean;
  output_passed: boolean;
  input_block_reason: string | null;
  output_block_reason: string | null;
  fired_rule: string | null;
  input_tokens: number;
  output_tokens: number;
  created_at: string;
  request_id: string;
}

export interface LogsResponse {
  total: number;
  page: number;
  page_size: number;
  items: RequestLogItem[];
}

export interface SuspiciousLogItem {
  id: string;
  status: string;
  prompt_preview: string;
  backend: string;
  fired_rule: string | null;
  reason: string | null;
  created_at: string;
}

export interface RecentLogItem {
  id: string;
  status: string;
  prompt_preview: string;
  model: string;
  backend: string;
  latency_ms: number;
  fired_rule: string | null;
  created_at: string;
}

export interface ChatFeedbackOut {
  rating: number;
  request_id: string;
}

export interface UserUsageStat {
  id: string;
  email: string;
  full_name: string | null;
  tokens_balance: number;
  tokens_used_lifetime: number;
  requests: number;
  blocked: number;
}

export interface ServiceHealth {
  status: string;
  latency_ms?: number;
  detail?: string;
  note?: string;
  http_status?: number;
}

export interface HealthDetailed {
  overall: string;
  database?: ServiceHealth;
  redis?: ServiceHealth;
  vectorstore?: ServiceHealth;
  llm_backends?: Record<string, ServiceHealth>;
  default_backend?: string;
  app_env?: string;
  billing_enabled?: boolean;
}
