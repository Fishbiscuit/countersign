export type RuleOutcome = "pass" | "hold" | "block";

export interface RuleResult {
  rule: string;
  outcome: RuleOutcome;
  detail: string;
}

export interface Explanation {
  risk?: "low" | "medium" | "high";
  headline?: string;
  signals?: string[];
  suggested_decision?: "approve" | "deny" | "check_with_customer";
  model?: string;
  error?: string;
}

export interface UntrustedRead {
  tool: string;
  excerpt: string;
  at: string;
}

export type IntentStatus =
  | "evaluating"
  | "allowed"
  | "held"
  | "approved"
  | "denied"
  | "expired"
  | "blocked"
  | "executing"
  | "executed"
  | "failed";

export interface Intent {
  id: string;
  created_at: string;
  updated_at: string;
  agent_id: string;
  agent_name: string;
  client: string | null;
  session_id: string | null;
  action: "refund" | "payout";
  amount: string;
  amount_value: number | null;
  currency: string;
  target: string;
  reference: string;
  request_id: string;
  status: IntentStatus;
  rules: RuleResult[];
  hold_reason: string | null;
  hold_expires_at: string | null;
  decided_by: string | null;
  decided_at: string | null;
  backend: "sandbox" | "simulated";
  attempts: number;
  paypal_id: string | null;
  paypal_status: string | null;
  paypal_debug_id: string | null;
  error: string | null;
  confirmed_status: string | null;
  confirmed_at: string | null;
  context: {
    agent_name?: string;
    client?: string;
    note?: string;
    untrusted?: UntrustedRead[];
    private_data_seen?: boolean;
    gateway_trifecta?: string | null;
  };
  explanation: Explanation | null;
}

export interface Mandate {
  allowed_actions: string[];
  currencies: string[];
  auto_approve_up_to: string;
  max_per_move: string;
  daily_limit: string;
  payout_allowlist: string[];
  velocity_per_minute: number;
  repeat_target_window_minutes: number;
  untrusted_auto_approve_up_to: string;
}

export interface Agent {
  id: string;
  name: string;
  client: string;
  key_hint: string;
  mandate: Mandate;
  active: boolean;
  created_at: string;
  last_seen_at: string | null;
  spent_24h?: Record<string, string>;
}

export interface ClientInfo {
  id: string;
  name: string;
  cloud: boolean;
}

export interface ConnectInfo {
  client: string;
  name: string;
  url: string;
  command: string | null;
  link: string | null;
  steps: string[];
  warning: string | null;
}

export interface Status {
  name: string;
  version: string;
  backend: "sandbox" | "simulated";
  backend_label: string;
  gateway_running: boolean;
  public_url: string;
  public: boolean;
  ai_explanations: boolean;
  ai_model: string | null;
  approval_timeout_s: number;
  demo_shop: boolean;
  signed_in: boolean;
}

export interface Summary {
  by_status: Record<string, { count: number; totals: Record<string, number> }>;
  retries_absorbed: number;
  agents: number;
  held_now: number;
}

export interface StreamEvent {
  id: number;
  at: string;
  intent_id: string | null;
  agent_id: string | null;
  kind: string;
  data: Record<string, unknown>;
}

export interface BenchRun {
  mode: string;
  moved: string;
  excess: string;
  calls: number;
  errors: number;
  holds?: { intent: string; amount: string; reason: string; decision: string }[];
  retries_absorbed?: number;
  statuses?: string[];
  agent_saw?: string[];
}

export interface BenchReport {
  status: "complete" | "not_run";
  generated_at?: string;
  backend?: string;
  human?: string;
  totals?: Record<string, string | number>;
  scenarios?: {
    id: string;
    title: string;
    story: string;
    intended: string;
    unguarded: BenchRun;
    countersign: BenchRun;
  }[];
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method,
    credentials: "same-origin",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    let message = response.statusText;
    try {
      const data = await response.json();
      message = data.detail ?? data.error ?? message;
    } catch {
      /* keep status text */
    }
    throw new ApiError(response.status, typeof message === "string" ? message : JSON.stringify(message));
  }
  return response.json() as Promise<T>;
}

export const api = {
  status: () => request<Status>("GET", "/api/status"),
  login: (token: string) => request<{ ok: boolean }>("POST", "/api/login", { token }),
  logout: () => request<{ ok: boolean }>("POST", "/api/logout"),
  intents: (status?: string) => request<Intent[]>("GET", status ? `/api/intents?status=${status}` : "/api/intents"),
  decide: (id: string, approve: boolean, via: "console" | "phone") =>
    request<Intent>("POST", `/api/intents/${id}/decision`, { approve, via }),
  summary: () => request<Summary>("GET", "/api/summary"),
  agents: () => request<Agent[]>("GET", "/api/agents"),
  clients: () => request<ClientInfo[]>("GET", "/api/clients"),
  createAgent: (name: string, client: string, mandate: Partial<Mandate>) =>
    request<{ agent: Agent; key: string; connect: ConnectInfo }>("POST", "/api/agents", { name, client, mandate }),
  updateAgent: (id: string, patch: { mandate?: Partial<Mandate>; active?: boolean }) =>
    request<Agent>("PATCH", `/api/agents/${id}`, patch),
  rotateKey: (id: string) => request<{ agent: Agent; key: string; connect: ConnectInfo }>("POST", `/api/agents/${id}/rotate`),
  askGrid: (question: string) =>
    request<{ filter_model: Record<string, unknown>; sort: { colId: string; sort: "asc" | "desc" }[]; summary: string }>(
      "POST",
      "/api/ask-grid",
      { question },
    ),
  bench: () => request<BenchReport>("GET", "/api/bench"),
  runBench: () => request<BenchReport>("POST", "/api/bench/run"),
  testPayment: (amount: string, currency: string) =>
    request<{ order_id: string; status: string; approve_url: string | null; capture_id: string | null; backend: string }>(
      "POST",
      "/api/test-payments",
      { amount, currency },
    ),
  captureTestPayment: (orderId: string) =>
    request<{ order_id: string; status: string; capture_id: string | null }>("POST", `/api/test-payments/${orderId}/capture`),
};
