import { KeyRound, Pause, Pencil, Play, Plus, X } from "lucide-react";
import { useState } from "react";
import { Avatar, CopyField } from "../components/bits";
import { type Agent, type ClientInfo, type ConnectInfo, type Mandate, type Status, api } from "../lib/api";
import { ago, money } from "../lib/format";
import { useLoad, useNow } from "../lib/live";

const PRESETS: Record<string, Partial<Mandate>> = {
  Cautious: {
    auto_approve_up_to: "10.00",
    max_per_move: "200.00",
    daily_limit: "50.00",
    velocity_per_minute: 3,
    untrusted_auto_approve_up_to: "5.00",
  },
  Standard: {
    auto_approve_up_to: "25.00",
    max_per_move: "500.00",
    daily_limit: "200.00",
    velocity_per_minute: 5,
    untrusted_auto_approve_up_to: "15.00",
  },
  Generous: {
    auto_approve_up_to: "75.00",
    max_per_move: "1000.00",
    daily_limit: "1000.00",
    velocity_per_minute: 10,
    untrusted_auto_approve_up_to: "25.00",
  },
};

export function Agents({ status }: { status: Status }) {
  const agents = useLoad(() => api.agents());
  const clients = useLoad(() => api.clients());
  const now = useNow(10000);
  const [connecting, setConnecting] = useState(false);
  const [editing, setEditing] = useState<Agent | null>(null);
  const [rotated, setRotated] = useState<ConnectInfo | null>(null);
  const visible = (agents.data ?? []).filter((a) => !a.name.startsWith("Bench readiness"));

  return (
    <>
      <header className="page-head">
        <div>
          <div className="eyebrow">Agents</div>
          <h1 className="page-title">Give each agent its own mandate.</h1>
          <p className="page-sub">
            Claude, ChatGPT, OpenClaw, Cursor, Grok or your own agent: each connects with its own key and moves money only
            within its limits. Pause one and its next move is blocked.
          </p>
        </div>
        <button className="btn btn-primary btn-lg" onClick={() => setConnecting(true)}>
          <Plus size={17} /> Connect an agent
        </button>
      </header>

      {visible.length === 0 && agents.data && (
        <div className="card empty">
          <span className="display">No agents yet</span>
          <span>Connect your first agent. It takes about a minute.</span>
          <button className="btn btn-primary" onClick={() => setConnecting(true)}>
            Connect an agent
          </button>
        </div>
      )}

      <div className="agent-grid">
        {visible.map((agent) => (
          <AgentCard
            key={agent.id}
            agent={agent}
            clients={clients.data ?? []}
            now={now}
            onEdit={() => setEditing(agent)}
            onToggle={async () => {
              await api.updateAgent(agent.id, { active: !agent.active });
              agents.reload();
            }}
            onRotate={async () => {
              const result = await api.rotateKey(agent.id);
              setRotated(result.connect);
            }}
          />
        ))}
      </div>

      {connecting && (
        <ConnectModal
          clients={clients.data ?? []}
          status={status}
          onClose={() => {
            setConnecting(false);
            agents.reload();
          }}
        />
      )}
      {editing && (
        <MandateModal
          agent={editing}
          onClose={() => {
            setEditing(null);
            agents.reload();
          }}
        />
      )}
      {rotated && (
        <Modal title="New key issued" onClose={() => setRotated(null)}>
          <p className="muted">The old URL stopped working. Update the agent with this one; it is shown only once.</p>
          <ConnectResult info={rotated} />
        </Modal>
      )}
    </>
  );
}

function AgentCard({
  agent,
  clients,
  now,
  onEdit,
  onToggle,
  onRotate,
}: {
  agent: Agent;
  clients: ClientInfo[];
  now: number;
  onEdit: () => void;
  onToggle: () => void;
  onRotate: () => void;
}) {
  const m = agent.mandate;
  const currency = m.currencies[0] ?? "USD";
  const spent = Number(agent.spent_24h?.[currency] ?? 0);
  const limit = Number(m.daily_limit);
  const share = limit > 0 ? Math.min(1, spent / limit) : 0;
  const clientName = clients.find((c) => c.id === agent.client)?.name ?? agent.client;
  return (
    <article className={`card agent-card ${agent.active ? "" : "paused"}`}>
      <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
        <Avatar name={agent.name} client={agent.client} size={40} />
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ fontWeight: 650, fontSize: 15 }}>{agent.name}</div>
          <div className="muted" style={{ fontSize: 12 }}>
            {clientName} · key …{agent.key_hint} · seen {ago(agent.last_seen_at, now)}
          </div>
        </div>
        <span className={`badge ${agent.active ? "badge-ok" : ""}`}>
          <span className="dot" />
          {agent.active ? "Active" : "Paused"}
        </span>
      </div>
      <div>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 6 }}>
          <span className="muted">Last 24 hours</span>
          <span className="num">
            {money(spent, currency)} of {money(limit, currency)}
          </span>
        </div>
        <div className={`meter ${share > 0.85 ? "hot" : ""}`}>
          <span style={{ width: `${share * 100}%` }} />
        </div>
      </div>
      <div className="chips">
        <span className="badge">auto ≤ {money(m.auto_approve_up_to, currency)}</span>
        <span className="badge">hard ≤ {money(m.max_per_move, currency)}</span>
        <span className="badge">after untrusted ≤ {money(m.untrusted_auto_approve_up_to, currency)}</span>
        <span className="badge">{m.velocity_per_minute}/min</span>
        <span className="badge">{m.allowed_actions.join(" + ")}</span>
        <span className="badge">{m.payout_allowlist.length} trusted payee{m.payout_allowlist.length === 1 ? "" : "s"}</span>
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button className="btn" onClick={onEdit}>
          <Pencil size={14} /> Mandate
        </button>
        <button className="btn" onClick={onToggle}>
          {agent.active ? <Pause size={14} /> : <Play size={14} />} {agent.active ? "Pause" : "Resume"}
        </button>
        <button className="btn btn-ghost" onClick={onRotate}>
          <KeyRound size={14} /> New key
        </button>
      </div>
    </article>
  );
}

function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="modal-back" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="card modal" role="dialog" aria-modal="true" aria-label={title}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
          <h2 className="section-title">{title}</h2>
          <button className="btn btn-ghost" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

function ConnectModal({ clients, status, onClose }: { clients: ClientInfo[]; status: Status; onClose: () => void }) {
  const [client, setClient] = useState("claude-code");
  const [name, setName] = useState("");
  const [preset, setPreset] = useState("Standard");
  const [payees, setPayees] = useState("");
  const [result, setResult] = useState<ConnectInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const chosen = clients.find((c) => c.id === client);

  const create = async () => {
    setBusy(true);
    setError(null);
    try {
      const allowlist = payees
        .split(/[\s,]+/)
        .map((p) => p.trim())
        .filter(Boolean);
      const response = await api.createAgent(name.trim() || `${chosen?.name ?? "Agent"}`, client, {
        ...PRESETS[preset],
        payout_allowlist: allowlist,
      });
      setResult(response.connect);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title={result ? `Connect ${result.name}` : "Connect an agent"} onClose={onClose}>
      {!result ? (
        <>
          <div className="client-grid" role="group" aria-label="Agent">
            {clients.map((c) => (
              <button key={c.id} className="client-tile" aria-pressed={client === c.id} onClick={() => setClient(c.id)}>
                <Avatar name={c.name} client={c.id} size={30} />
                <span style={{ fontWeight: 600 }}>{c.name}</span>
                {c.cloud && <span className="muted" style={{ fontSize: 11 }}>needs a public URL</span>}
              </button>
            ))}
          </div>
          <div className="form-grid">
            <label className="field">
              <span>Name</span>
              <input className="input" placeholder={`${chosen?.name ?? "Agent"} · support desk`} value={name} onChange={(e) => setName(e.target.value)} />
            </label>
            <label className="field">
              <span>Trusted payees (optional)</span>
              <input className="input" placeholder="friend@example.com, supplier@example.com" value={payees} onChange={(e) => setPayees(e.target.value)} />
            </label>
          </div>
          <div className="field" style={{ marginTop: 14 }}>
            <span>Mandate</span>
            <div className="preset-row">
              {Object.keys(PRESETS).map((p) => (
                <button key={p} className={`btn ${preset === p ? "btn-primary" : ""}`} onClick={() => setPreset(p)}>
                  {p}
                </button>
              ))}
            </div>
            <span className="muted" style={{ fontSize: 12, fontWeight: 400 }}>
              {preset}: auto-approve up to {money(PRESETS[preset].auto_approve_up_to ?? "0")}, never more than{" "}
              {money(PRESETS[preset].max_per_move ?? "0")} per move or {money(PRESETS[preset].daily_limit ?? "0")} a day. You can
              change it later.
            </span>
          </div>
          {!status.public && chosen?.cloud && (
            <div className="warn" style={{ marginTop: 14 }}>
              {chosen.name} runs in the cloud and can't reach {status.public_url}. Deploy Countersign (Render blueprint in
              the repo) or set COUNTERSIGN_PUBLIC_URL to a public https URL first.
            </div>
          )}
          {error && <p className="error-text">{error}</p>}
          <div className="hold-actions">
            <button className="btn btn-primary btn-lg" onClick={create} disabled={busy}>
              {busy ? "Creating…" : "Create agent and key"}
            </button>
          </div>
        </>
      ) : (
        <ConnectResult info={result} />
      )}
    </Modal>
  );
}

function ConnectResult({ info }: { info: ConnectInfo }) {
  return (
    <div style={{ display: "grid", gap: 12, marginTop: 10 }}>
      <div className="field">
        <span>This agent's Countersign URL (contains its key; shown once)</span>
        <CopyField value={info.url} label="MCP URL" />
      </div>
      {info.command && (
        <div className="field">
          <span>Command</span>
          <CopyField value={info.command} label="Command" />
        </div>
      )}
      {info.link && (
        <a className="btn" href={info.link} target="_blank" rel="noreferrer">
          Open install link
        </a>
      )}
      <ol className="steps">
        {info.steps.map((step) => (
          <li key={step}>{step}</li>
        ))}
      </ol>
      {info.warning && <div className="warn">{info.warning}</div>}
    </div>
  );
}

function MandateModal({ agent, onClose }: { agent: Agent; onClose: () => void }) {
  const [m, setM] = useState<Mandate>(agent.mandate);
  const [payees, setPayees] = useState(agent.mandate.payout_allowlist.join(", "));
  const [error, setError] = useState<string | null>(null);
  const set = (key: keyof Mandate, value: string | number | string[]) => setM((current) => ({ ...current, [key]: value }));
  const toggleAction = (action: string) =>
    set("allowed_actions", m.allowed_actions.includes(action) ? m.allowed_actions.filter((a) => a !== action) : [...m.allowed_actions, action]);

  const save = async () => {
    setError(null);
    try {
      await api.updateAgent(agent.id, {
        mandate: { ...m, payout_allowlist: payees.split(/[\s,]+/).map((p) => p.trim()).filter(Boolean) },
      });
      onClose();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const amountField = (key: keyof Mandate, label: string) => (
    <label className="field">
      <span>{label}</span>
      <input className="input num" inputMode="decimal" value={String(m[key])} onChange={(e) => set(key, e.target.value)} />
    </label>
  );

  return (
    <Modal title={`${agent.name}'s mandate`} onClose={onClose}>
      <div className="preset-row" style={{ margin: "10px 0 14px" }}>
        {["refund", "payout"].map((action) => (
          <button key={action} className={`btn ${m.allowed_actions.includes(action) ? "btn-primary" : ""}`} onClick={() => toggleAction(action)}>
            {action === "refund" ? "Refunds" : "Payouts"}
          </button>
        ))}
      </div>
      <div className="form-grid">
        {amountField("auto_approve_up_to", "Auto-approve up to")}
        {amountField("max_per_move", "Hard limit per move")}
        {amountField("daily_limit", "24-hour limit")}
        {amountField("untrusted_auto_approve_up_to", "Auto-approve after untrusted content")}
        <label className="field">
          <span>Moves per minute before holding</span>
          <input className="input num" type="number" min={1} value={m.velocity_per_minute} onChange={(e) => set("velocity_per_minute", Number(e.target.value))} />
        </label>
        <label className="field">
          <span>Hold repeat moves to same target (minutes)</span>
          <input
            className="input num"
            type="number"
            min={0}
            value={m.repeat_target_window_minutes}
            onChange={(e) => set("repeat_target_window_minutes", Number(e.target.value))}
          />
        </label>
      </div>
      <label className="field" style={{ marginTop: 12 }}>
        <span>Trusted payees (payouts to anyone else wait for you)</span>
        <input className="input" value={payees} onChange={(e) => setPayees(e.target.value)} />
      </label>
      {error && <p className="error-text">{error}</p>}
      <div className="hold-actions">
        <button className="btn" onClick={onClose}>
          Cancel
        </button>
        <button className="btn btn-primary" onClick={save}>
          Save mandate
        </button>
      </div>
    </Modal>
  );
}
