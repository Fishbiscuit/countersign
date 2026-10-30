import type { Intent, IntentStatus } from "./api";

export function money(amount: string | number, currency = "USD"): string {
  const value = typeof amount === "number" ? amount : Number(amount);
  if (!Number.isFinite(value)) return `${amount} ${currency}`;
  try {
    // A fixed locale: in en-SG, for example, SGD would otherwise show as a bare $ and USD as US$.
    return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(value);
  } catch {
    return `${value.toFixed(2)} ${currency}`;
  }
}

export function addTotals(...groups: (Record<string, number> | undefined)[]): Record<string, number> {
  const totals: Record<string, number> = {};
  for (const group of groups) {
    for (const [currency, amount] of Object.entries(group ?? {})) totals[currency] = (totals[currency] ?? 0) + amount;
  }
  return totals;
}

/** Amounts in different currencies can't be added, so each keeps its own total. */
export function moneyTotals(totals: Record<string, number>): string {
  const parts = Object.entries(totals)
    .sort()
    .map(([currency, total]) => money(total, currency));
  return parts.length ? parts.join(" + ") : money(0);
}

export function ago(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "never";
  const seconds = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return new Date(iso).toLocaleDateString();
}

export function clock(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export const STATUS_LABEL: Record<IntentStatus, string> = {
  evaluating: "Checking",
  allowed: "Allowed",
  held: "Waiting for you",
  approved: "Countersigned",
  denied: "Denied",
  expired: "Expired",
  blocked: "Blocked",
  executing: "Sending to PayPal",
  executed: "Paid",
  failed: "PayPal refused",
};

export function statusTone(status: IntentStatus): "ok" | "held" | "deny" | "accent" | "" {
  if (status === "executed") return "ok";
  if (status === "held") return "held";
  if (status === "denied" || status === "blocked" || status === "failed") return "deny";
  if (status === "approved" || status === "allowed" || status === "executing") return "accent";
  return "";
}

export function describeTarget(intent: Pick<Intent, "action" | "target">): string {
  return intent.action === "refund" ? `back to the buyer of ${intent.target}` : `to ${intent.target}`;
}

export const CLIENT_COLORS: Record<string, string> = {
  "claude-code": "#c2633a",
  claude: "#b4552e",
  chatgpt: "#1f7a63",
  openclaw: "#c0392b",
  cursor: "#2b2b2b",
  grok: "#3d3d3d",
  vscode: "#1f6fbf",
  goose: "#5b4bb7",
  other: "#6b7280",
};

export function initials(name: string): string {
  const words = name.replace(/[^\p{L}\p{N} ]/gu, " ").trim().split(/\s+/).filter(Boolean);
  return ((words[0]?.[0] ?? "A") + (words[1]?.[0] ?? "")).toUpperCase();
}

const SUSPICIOUS = [
  /system note[^.\n]*/gi,
  /ignore (?:your|all|previous)[^.\n]*/gi,
  /(?:manager|admin|owner) (?:has )?(?:already )?approved[^.\n]*/gi,
  /without asking[^.\n]*/gi,
  /do not mention[^.\n]*/gi,
];

/** Split untrusted text into plain and suspicious parts, so the excerpt can highlight injection-like phrases. */
export function highlight(text: string): { text: string; flagged: boolean }[] {
  const ranges: [number, number][] = [];
  for (const pattern of SUSPICIOUS) {
    for (const match of text.matchAll(pattern)) {
      if (match.index !== undefined) ranges.push([match.index, match.index + match[0].length]);
    }
  }
  ranges.sort((a, b) => a[0] - b[0]);
  const parts: { text: string; flagged: boolean }[] = [];
  let cursor = 0;
  for (const [start, end] of ranges) {
    if (start < cursor) continue;
    if (start > cursor) parts.push({ text: text.slice(cursor, start), flagged: false });
    parts.push({ text: text.slice(start, end), flagged: true });
    cursor = end;
  }
  if (cursor < text.length) parts.push({ text: text.slice(cursor), flagged: false });
  return parts;
}

/** Untrusted tool output, made readable: ticket-like JSON becomes headers plus its body text. */
export function readable(excerpt: string): { headers: [string, string][]; body: string } {
  try {
    const data = JSON.parse(excerpt);
    if (data && typeof data === "object" && !Array.isArray(data)) {
      const bodyKey = ["body", "message", "text", "content"].find((k) => typeof data[k] === "string");
      const headers = Object.entries(data)
        .filter(([k, v]) => k !== bodyKey && (typeof v === "string" || typeof v === "number"))
        .slice(0, 4)
        .map(([k, v]) => [k, String(v)] as [string, string]);
      if (bodyKey) return { headers, body: data[bodyKey] };
    }
  } catch {
    /* not JSON */
  }
  return { headers: [], body: excerpt };
}
