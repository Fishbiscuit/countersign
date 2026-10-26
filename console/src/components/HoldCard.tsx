import { ChevronRight, CircleCheck, CircleSlash, PauseCircle, ShieldAlert, Sparkles } from "lucide-react";
import { useState } from "react";
import type { Intent } from "../lib/api";
import { ago, describeTarget, highlight, money, readable } from "../lib/format";
import { Seal, SignatureLine } from "./Seal";
import { Avatar, Countdown } from "./bits";

export interface HoldCardProps {
  intent: Intent;
  now: number;
  timeoutSeconds: number;
  aiEnabled: boolean;
  decision?: "approved" | "denied";
  onDecide: (approve: boolean) => Promise<void>;
  compact?: boolean;
}

const RISK_TONE = { high: "badge-deny", medium: "badge-held", low: "badge-ok" } as const;
const SUGGESTION = { approve: "looks fine to approve", deny: "suggests denying", check_with_customer: "suggests checking with the customer" };

export function HoldCard({ intent, now, timeoutSeconds, aiEnabled, decision, onDecide, compact }: HoldCardProps) {
  const [busy, setBusy] = useState<"approve" | "deny" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const held = intent.rules.filter((r) => r.outcome !== "pass");
  const untrusted = intent.context.untrusted ?? [];
  const explanation = intent.explanation;
  const expired = intent.status === "expired";

  const decide = async (approve: boolean) => {
    setBusy(approve ? "approve" : "deny");
    setError(null);
    try {
      await onDecide(approve);
    } catch (err) {
      setError((err as Error).message);
      setBusy(null);
    }
  };

  return (
    <article
      className={`card hold ${decision === "approved" ? "is-approved" : decision === "denied" ? "is-denied" : ""}`}
      aria-label={`${intent.action} of ${money(intent.amount, intent.currency)} waiting for your decision`}
    >
      <div className="hold-top">
        <Avatar name={intent.agent_name} client={intent.client} />
        <div className="hold-agent">
          <b>{intent.agent_name}</b>
          <span>
            asked {ago(intent.created_at, now)} · ref <span className="mono">{intent.reference}</span>
            {intent.attempts > 1 && ` · ${intent.attempts - 1} retr${intent.attempts > 2 ? "ies" : "y"} absorbed`}
          </span>
        </div>
        {!decision &&
          (expired ? (
            <span className="badge">Expired · agent may retry after you approve</span>
          ) : (
            <Countdown expiresAt={intent.hold_expires_at} totalSeconds={timeoutSeconds} now={now} />
          ))}
      </div>

      <div className="hold-move">
        <span className="hold-action">{intent.action === "refund" ? "Refund" : "Payout"}</span>
        <span className="hold-amount num">
          {money(intent.amount, intent.currency)}
          <small>{intent.currency}</small>
        </span>
        <span className="hold-target">{describeTarget(intent)}</span>
      </div>

      <div className="reasons">
        {held.map((rule) => (
          <span key={rule.rule} className={`reason ${rule.outcome === "block" ? "block" : ""}`} title={rule.detail}>
            <PauseCircle size={13} />
            {shortReason(rule.rule)}
          </span>
        ))}
      </div>

      {explanation && !explanation.error && (
        <div className="ai-note" role="note">
          <span className={`badge risk ${RISK_TONE[explanation.risk ?? "medium"]}`}>
            <ShieldAlert size={13} />
            {explanation.risk ?? "?"} risk
          </span>
          <p>
            <b>{explanation.headline}</b>
          </p>
          <div>
            {explanation.signals && explanation.signals.length > 0 && (
              <ul>
                {explanation.signals.map((signal) => (
                  <li key={signal}>{signal}</li>
                ))}
              </ul>
            )}
            <div className="ai-meta">
              <Sparkles size={11} style={{ verticalAlign: -1 }} /> Claude {SUGGESTION[explanation.suggested_decision ?? "check_with_customer"]}. It
              explains; the rules held this and you decide.
            </div>
          </div>
        </div>
      )}
      {explanation?.error && <p className="ai-meta">{explanation.error}</p>}
      {!explanation && aiEnabled && !decision && (
        <p className="ai-meta">
          <Sparkles size={11} style={{ verticalAlign: -1 }} /> Claude is reading what the agent saw…
        </p>
      )}

      {untrusted.length > 0 && (
        <details className="fold" open={!compact}>
          <summary>
            <ChevronRight size={14} className="chev" /> What the agent read first ({untrusted.length} untrusted source
            {untrusted.length > 1 ? "s" : ""})
          </summary>
          {untrusted.slice(-2).map((item) => {
            const { headers, body } = readable(item.excerpt);
            return (
              <div key={item.at + item.tool}>
                <div className="excerpt">
                  {headers.length > 0 && (
                    <div className="excerpt-head">
                      {headers.map(([key, value]) => (
                        <span key={key}>
                          <b>{key}</b> {value}
                        </span>
                      ))}
                    </div>
                  )}
                  {highlight(body).map((part, index) => (part.flagged ? <mark key={index}>{part.text}</mark> : <span key={index}>{part.text}</span>))}
                </div>
                <div className="ai-meta mono">{item.tool}</div>
              </div>
            );
          })}
        </details>
      )}

      {!compact && (
        <details className="fold">
          <summary>
            <ChevronRight size={14} className="chev" /> Rule receipt ({intent.rules.length} checks)
          </summary>
          <ul className="receipt">
            {intent.rules.map((rule) => (
              <li key={rule.rule}>
                {rule.outcome === "pass" ? (
                  <CircleCheck size={15} className="pass" />
                ) : rule.outcome === "hold" ? (
                  <PauseCircle size={15} className="hold-o" />
                ) : (
                  <CircleSlash size={15} className="block-o" />
                )}
                <span>
                  <code>{rule.rule}</code>
                  {rule.detail}
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}

      {error && <p className="error-text">{error}</p>}
      {!decision && (
        <div className="hold-actions">
          <button className="btn btn-deny btn-lg" disabled={busy !== null} onClick={() => decide(false)}>
            {busy === "deny" ? "Denying…" : "Deny"}
          </button>
          <button className="btn btn-sign btn-lg" disabled={busy !== null} onClick={() => decide(true)}>
            {busy === "approve" ? "Signing…" : "Countersign"}
          </button>
        </div>
      )}
      {decision && (
        <SignatureLine
          approved={decision === "approved"}
          caption={
            decision === "approved"
              ? `Countersigned at ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}. The agent's call goes through to PayPal now.`
              : `Denied at ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}. Nothing was paid, and the agent was told not to retry.`
          }
        />
      )}
      {decision && <Seal approved={decision === "approved"} />}
    </article>
  );
}

function shortReason(rule: string): string {
  return (
    {
      "amount.auto_approve": "Over auto-approve limit",
      "amount.max_per_move": "Over hard limit",
      "budget.daily": "Over 24-hour limit",
      "payout.recipient": "New recipient",
      velocity: "Unusual speed",
      "duplicate.same_target": "Possible duplicate",
      "context.lethal_trifecta": "After untrusted content",
      "refund.verified": "Payment not verified",
      "mandate.action": "Action not allowed",
      "mandate.currency": "Currency not allowed",
      "agent.active": "Agent paused",
    }[rule] ?? rule
  );
}
