import { ArrowDownLeft, ArrowUpRight, Ban, CircleCheck, Hourglass, RotateCcw, Signature, Timer } from "lucide-react";
import { Suspense, lazy } from "react";
import { HoldList } from "../components/HoldList";
import { StatusPill } from "../components/bits";
import { api, type Intent, type Status } from "../lib/api";
import { addTotals, ago, money, moneyTotals } from "../lib/format";
import { useLoad, useNow } from "../lib/live";

const Timeline = lazy(() => import("./Timeline"));

export function Live({ status }: { status: Status }) {
  const summary = useLoad(() => api.summary());
  const intents = useLoad(() => api.intents());
  const now = useNow(5000);
  const s = summary.data;
  const paid = s?.by_status.executed;
  const stopped = (s?.by_status.denied?.count ?? 0) + (s?.by_status.blocked?.count ?? 0) + (s?.by_status.expired?.count ?? 0);
  const stoppedTotals = addTotals(s?.by_status.denied?.totals, s?.by_status.blocked?.totals, s?.by_status.expired?.totals);

  return (
    <>
      <header className="page-head">
        <div>
          <div className="eyebrow">Live · last 24 hours</div>
          <h1 className="page-title">Every money move gets a second signature.</h1>
          <p className="page-sub">
            Agents move money through PayPal within the mandate you gave them. Anything outside it waits here for you, and
            nothing is paid until you countersign.
          </p>
        </div>
      </header>

      <section className="tiles" aria-label="Summary">
        <Tile label="Paid out" value={moneyTotals(paid?.totals ?? {})} note={`${paid?.count ?? 0} moves executed`} />
        <Tile label="Waiting for you" value={String(s?.held_now ?? 0)} note="held for a countersignature" />
        <Tile label="Stopped" value={moneyTotals(stoppedTotals)} note={`${stopped} denied, blocked or expired`} />
        <Tile label="Retries absorbed" value={String(s?.retries_absorbed ?? 0)} note="never paid twice" />
        <Tile label="Agents connected" value={String(s?.agents ?? 0)} note="each with its own mandate" />
      </section>

      <div className="live-grid">
        <section aria-labelledby="needs">
          <div className="section-head">
            <h2 id="needs" className="section-title">
              Needs your signature
            </h2>
            <span className="muted">Fails closed after {Math.round(status.approval_timeout_s)}s</span>
          </div>
          <HoldList status={status} via="console" />
        </section>

        <section aria-labelledby="wire">
          <div className="section-head">
            <h2 id="wire" className="section-title">
              Live wire
            </h2>
            <span className="muted">what agents asked for</span>
          </div>
          <div className="card">
            {intents.data && intents.data.length === 0 && (
              <div className="empty">
                <span className="display">Quiet so far</span>
                <span>Connect an agent, and every money move it asks for shows up here.</span>
              </div>
            )}
            <ul className="feed">
              {(intents.data ?? []).slice(0, 30).map((intent) => (
                <FeedItem key={intent.id} intent={intent} now={now} />
              ))}
            </ul>
          </div>
        </section>
      </div>

      <section style={{ marginTop: 26 }} aria-labelledby="timeline">
        <div className="section-head">
          <h2 id="timeline" className="section-title">
            Agent activity
          </h2>
          <span className="muted">one row per agent · Bryntum Scheduler</span>
        </div>
        <div className="card timeline-wrap">
          <Suspense fallback={<p className="muted card-pad">Loading timeline…</p>}>
            <Timeline />
          </Suspense>
        </div>
      </section>
    </>
  );
}

function Tile({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="card tile">
      <div className="eyebrow">{label}</div>
      <div className="tile-value num">{value}</div>
      <div className="tile-note">{note}</div>
    </div>
  );
}

const ICONS = {
  executed: { icon: CircleCheck, tone: "ok" },
  held: { icon: Hourglass, tone: "held" },
  approved: { icon: Signature, tone: "accent" },
  allowed: { icon: Timer, tone: "accent" },
  executing: { icon: Timer, tone: "accent" },
  denied: { icon: Ban, tone: "deny" },
  blocked: { icon: Ban, tone: "deny" },
  failed: { icon: Ban, tone: "deny" },
  expired: { icon: Hourglass, tone: "" },
  evaluating: { icon: Timer, tone: "" },
} as const;

function FeedItem({ intent, now }: { intent: Intent; now: number }) {
  const { icon: Icon, tone } = ICONS[intent.status] ?? ICONS.evaluating;
  const Direction = intent.action === "refund" ? ArrowDownLeft : ArrowUpRight;
  return (
    <li>
      <span className={`feed-icon ${tone}`}>
        <Icon size={15} />
      </span>
      <div className="feed-text">
        <div>
          <b>{intent.agent_name}</b> asked to {intent.action}{" "}
          <b className="num">{money(intent.amount, intent.currency)}</b>{" "}
          <span className="muted">
            <Direction size={12} style={{ verticalAlign: -1 }} /> {intent.target}
          </span>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 4, flexWrap: "wrap" }}>
          <StatusPill status={intent.status} />
          {intent.attempts > 1 && (
            <span className="badge">
              <RotateCcw size={11} /> {intent.attempts - 1} retr{intent.attempts > 2 ? "ies" : "y"} absorbed
            </span>
          )}
          {intent.paypal_id && <span className="mono muted">{intent.paypal_id}</span>}
        </div>
      </div>
      <span className="feed-time">{ago(intent.updated_at, now)}</span>
    </li>
  );
}
