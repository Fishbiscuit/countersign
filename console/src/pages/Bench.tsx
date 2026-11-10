import { FlaskConical, Play } from "lucide-react";
import { useState } from "react";
import { type BenchReport, api } from "../lib/api";
import { money } from "../lib/format";
import { useLoad } from "../lib/live";

export function Bench() {
  const latest = useLoad(() => api.bench());
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fresh, setFresh] = useState<BenchReport | null>(null);
  const report = fresh ?? latest.data;

  const run = async () => {
    setRunning(true);
    setError(null);
    try {
      setFresh(await api.runBench());
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setRunning(false);
    }
  };

  const totals = report?.totals;
  const scenarios = report?.scenarios ?? [];
  const scale = Math.max(1, ...scenarios.flatMap((s) => [Number(s.unguarded.moved), Number(s.countersign.moved), Number(s.intended)]));

  return (
    <>
      <header className="page-head">
        <div>
          <div className="eyebrow">Chaos bench</div>
          <h1 className="page-title">The same failures, with and without Countersign.</h1>
          <p className="page-sub">
            Six things that go wrong when agents hold payment tools: lost responses, prompt injection, look-alike payees,
            runaway loops, and two fair refunds as controls. Each runs against a fresh payment, once calling PayPal directly
            and once through Countersign. The bench counts the money that actually moved.
          </p>
        </div>
        <button className="btn btn-primary btn-lg" onClick={run} disabled={running}>
          {running ? <FlaskConical size={17} /> : <Play size={17} />} {running ? "Running (about a minute)…" : "Run the bench"}
        </button>
      </header>

      {error && <p className="error-text">{error}</p>}
      {report?.status !== "complete" && !running && (
        <div className="card empty">
          <span className="display">Not run yet</span>
          <span>It starts an isolated Countersign on the simulator, so your real money trail stays untouched.</span>
        </div>
      )}

      {totals && (
        <div className="versus">
          <div className="card bad">
            <div className="eyebrow">Agent with direct PayPal tools</div>
            <div className="versus-value num">{money(String(totals.unguarded_excess))}</div>
            <div className="muted">moved that should never have moved</div>
          </div>
          <div className="card good">
            <div className="eyebrow">Same agent through Countersign</div>
            <div className="versus-value num">{money(String(totals.countersign_excess))}</div>
            <div className="muted">
              {totals.holds} {Number(totals.holds) === 1 ? "move" : "moves"} waited for a human · {totals.retries_absorbed} {Number(totals.retries_absorbed) === 1 ? "retry" : "retries"} absorbed · fair refunds still paid
            </div>
          </div>
        </div>
      )}

      <div className="stack">
        {scenarios.map((s) => {
          const holds = s.countersign.holds ?? [];
          return (
            <article key={s.id} className="card scenario">
              <div>
                <h3 className="section-title" style={{ fontSize: 22 }}>
                  {s.title}
                </h3>
                <p className="muted" style={{ margin: "6px 0 10px" }}>
                  {s.story}
                </p>
                <div className="chips">
                  <span className="badge">should move {money(s.intended)}</span>
                  {holds.length > 0 && (
                    <span className="badge badge-held">
                      {holds.length} hold{holds.length > 1 ? "s" : ""} · {holds[0].decision}
                    </span>
                  )}
                  {(s.countersign.retries_absorbed ?? 0) > 0 && <span className="badge badge-accent">{s.countersign.retries_absorbed} retry absorbed</span>}
                </div>
                {s.countersign.agent_saw && s.countersign.agent_saw.length > 0 && (
                  <details className="fold">
                    <summary>What the agent was told</summary>
                    <div className="excerpt">{s.countersign.agent_saw[0]}</div>
                  </details>
                )}
              </div>
              <div className="bars" aria-label={`${s.title}: unguarded moved ${s.unguarded.moved}, Countersign moved ${s.countersign.moved}`}>
                <Bar label="Unguarded" value={Number(s.unguarded.moved)} intended={Number(s.intended)} scale={scale} />
                <Bar label="Countersign" value={Number(s.countersign.moved)} intended={Number(s.intended)} scale={scale} />
                <span className="muted" style={{ fontSize: 11 }}>
                  Black tick: what should have moved
                </span>
              </div>
            </article>
          );
        })}
      </div>

      {report?.generated_at && (
        <p className="muted" style={{ marginTop: 18, fontSize: 12 }}>
          Run {new Date(report.generated_at).toLocaleString()} · {report.backend} · Human: {report.human}
        </p>
      )}
    </>
  );
}

function Bar({ label, value, intended, scale }: { label: string; value: number; intended: number; scale: number }) {
  const over = value > intended + 0.001;
  return (
    <div className="bar-row">
      <span className="muted">{label}</span>
      <div className="bar-track">
        <div className={`bar-fill ${over ? "bad" : "good"}`} style={{ width: `${(value / scale) * 100}%` }} />
        <div className="bar-intended" style={{ left: `${(intended / scale) * 100}%` }} />
      </div>
      <span className="num" style={{ textAlign: "right", fontWeight: 600 }}>
        {money(value)}
      </span>
    </div>
  );
}
