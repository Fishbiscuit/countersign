import { useState } from "react";
import { CopyField } from "../components/bits";
import { type Status, api } from "../lib/api";

export function Setup({ status }: { status: Status }) {
  const [amount, setAmount] = useState("50.00");
  const [busy, setBusy] = useState(false);
  const [payment, setPayment] = useState<{ order_id: string; approve_url: string | null; capture_id: string | null } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const create = async () => {
    setBusy(true);
    setError(null);
    try {
      setPayment(await api.testPayment(amount, "USD"));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const capture = async () => {
    if (!payment) return;
    setBusy(true);
    try {
      const result = await api.captureTestPayment(payment.order_id);
      setPayment({ ...payment, capture_id: result.capture_id });
      if (!result.capture_id) setError(`Not approved yet (order status ${result.status}). Approve it as the sandbox buyer first.`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <header className="page-head">
        <div>
          <div className="eyebrow">Setup</div>
          <h1 className="page-title">How this Countersign is wired.</h1>
        </div>
      </header>
      <div className="stack" style={{ maxWidth: 820 }}>
        <section className="card card-pad">
          <div className="eyebrow">PayPal backend</div>
          <h2 className="section-title" style={{ margin: "6px 0" }}>
            {status.backend_label}
          </h2>
          <p className="muted" style={{ margin: 0 }}>
            {status.backend === "sandbox"
              ? "Every refund and payout is a real PayPal Sandbox API call with test money. Countersign is fixed to the sandbox API and cannot reach live PayPal."
              : "No PayPal calls are made. Payments, refunds and payouts are simulated with PayPal's idempotency rules, and every screen says so. Set COUNTERSIGN_BACKEND=sandbox with sandbox app credentials to use the real PayPal Sandbox."}
          </p>
        </section>

        <section className="card card-pad">
          <div className="eyebrow">Create a test payment</div>
          <p className="muted">
            Agents can only refund payments that exist. In the sandbox you approve the checkout once as your sandbox buyer;
            the simulator approves it instantly.
          </p>
          <div style={{ display: "flex", gap: 10, alignItems: "end", flexWrap: "wrap" }}>
            <label className="field">
              <span>Amount (USD)</span>
              <input className="input num" value={amount} onChange={(e) => setAmount(e.target.value)} style={{ width: 140 }} />
            </label>
            <button className="btn btn-primary" onClick={create} disabled={busy}>
              Create payment
            </button>
          </div>
          {payment && (
            <div style={{ display: "grid", gap: 10, marginTop: 14 }}>
              {payment.capture_id ? (
                <div className="field">
                  <span>Capture ID (give this to your agent to refund against)</span>
                  <CopyField value={payment.capture_id} label="Capture ID" />
                </div>
              ) : (
                <>
                  <div className="field">
                    <span>Approve as the sandbox buyer</span>
                    {payment.approve_url && (
                      <a className="btn" href={payment.approve_url} target="_blank" rel="noreferrer">
                        Open PayPal sandbox checkout
                      </a>
                    )}
                  </div>
                  <button className="btn" onClick={capture} disabled={busy}>
                    I approved it — capture
                  </button>
                </>
              )}
            </div>
          )}
          {error && <p className="error-text">{error}</p>}
        </section>

        <section className="card card-pad">
          <div className="eyebrow">Endpoints</div>
          <div className="field" style={{ marginTop: 8 }}>
            <span>Public URL {status.public ? "" : "(local only — cloud agents like ChatGPT need https)"}</span>
            <CopyField value={status.public_url} label="Public URL" />
          </div>
          <div className="field" style={{ marginTop: 10 }}>
            <span>Approve from your phone</span>
            <CopyField value={`${status.public_url}/m`} label="Phone URL" />
          </div>
          <div className="field" style={{ marginTop: 10 }}>
            <span>PayPal webhook (sandbox, set PAYPAL_WEBHOOK_ID)</span>
            <CopyField value={`${status.public_url}/webhooks/paypal`} label="Webhook URL" />
          </div>
        </section>

        <section className="card card-pad">
          <div className="eyebrow">AI</div>
          <p style={{ margin: "6px 0 0" }}>
            {status.ai_explanations
              ? `Claude (${status.ai_model}) explains each hold and powers "Ask the money trail". It never approves or denies.`
              : "Off. Claude can explain holds and answer questions about the money trail. Locally, set COUNTERSIGN_EXPLAINER=claude-code to use your signed-in Claude Code, with no API key. When deployed, set ANTHROPIC_API_KEY."}
          </p>
        </section>
      </div>
    </>
  );
}
