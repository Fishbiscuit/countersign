import { useEffect, useRef, useState } from "react";
import { api, type Intent, type Status } from "../lib/api";
import { useLoad, useNow } from "../lib/live";
import { HoldCard } from "./HoldCard";

const SEAL_MS = 3400;

/** Held money moves, newest first. A decided card stays on screen long enough for its seal to land. */
export function HoldList({ status, via, compact, includeExpired = true }: { status: Status; via: "console" | "phone"; compact?: boolean; includeExpired?: boolean }) {
  const now = useNow(1000);
  const held = useLoad(() => api.intents("held"));
  const expired = useLoad(() => (includeExpired ? api.intents("expired") : Promise.resolve([] as Intent[])), [includeExpired]);
  const [decided, setDecided] = useState<Record<string, { intent: Intent; decision: "approved" | "denied"; at: number }>>({});
  const timers = useRef<number[]>([]);

  useEffect(() => () => timers.current.forEach((t) => window.clearTimeout(t)), []);

  const decide = async (intent: Intent, approve: boolean) => {
    await api.decide(intent.id, approve, via);
    setDecided((d) => ({ ...d, [intent.id]: { intent, decision: approve ? "approved" : "denied", at: Date.now() } }));
    timers.current.push(
      window.setTimeout(() => {
        setDecided((d) => {
          const next = { ...d };
          delete next[intent.id];
          return next;
        });
        held.reload();
        expired.reload();
      }, SEAL_MS),
    );
  };

  const live = [...(held.data ?? []), ...(expired.data ?? []).slice(0, 6)].filter((i) => !decided[i.id]);
  const cards = [
    ...Object.values(decided)
      .sort((a, b) => b.at - a.at)
      .map((d) => ({ intent: d.intent, decision: d.decision })),
    ...live.map((intent) => ({ intent, decision: undefined })),
  ];

  if (held.error) return <p className="error-text">{held.error}</p>;
  if (!held.data) return <p className="muted">Loading…</p>;
  if (cards.length === 0) {
    return (
      <div className="card empty">
        <span className="display">Nothing needs your signature</span>
        <span>When an agent asks for a money move outside its mandate, it waits here for you.</span>
      </div>
    );
  }
  return (
    <div className="stack">
      {cards.map(({ intent, decision }) => (
        <HoldCard
          key={intent.id}
          intent={intent}
          now={now}
          timeoutSeconds={status.approval_timeout_s}
          aiEnabled={status.ai_explanations}
          decision={decision}
          compact={compact}
          onDecide={(approve) => decide(intent, approve)}
        />
      ))}
    </div>
  );
}
