import {
  AllCommunityModule,
  type ColDef,
  type GridApi,
  type ICellRendererParams,
  ModuleRegistry,
  themeQuartz,
} from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { CircleCheck, CircleSlash, Download, PauseCircle, Sparkles, X } from "lucide-react";
import { useCallback, useMemo, useRef, useState } from "react";
import { Avatar, StatusPill } from "../components/bits";
import { api, type Intent, type Status } from "../lib/api";
import { addTotals, clock, money, moneyTotals } from "../lib/format";
import { useLoad } from "../lib/live";

ModuleRegistry.registerModules([AllCommunityModule]);

const gridTheme = themeQuartz.withParams({
  backgroundColor: "var(--paper-raised)",
  foregroundColor: "var(--ink)",
  headerBackgroundColor: "var(--paper)",
  headerTextColor: "var(--ink-2)",
  borderColor: "var(--rule)",
  rowHoverColor: "var(--muted-wash)",
  selectedRowBackgroundColor: "var(--accent-wash)",
  accentColor: "var(--accent)",
  fontFamily: "var(--font-ui)",
  fontSize: 13,
  headerFontWeight: 600,
  rowHeight: 46,
  headerHeight: 40,
  wrapperBorderRadius: 16,
  spacing: 7,
});

const EXAMPLES = ["held payouts over $20", "everything OpenClaw did", "denied or blocked refunds", "biggest executed moves first"];

export function Trail({ status }: { status: Status }) {
  const { data, error } = useLoad(() => api.intents());
  const grid = useRef<GridApi<Intent> | null>(null);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [aiSummary, setAiSummary] = useState<string | null>(null);
  const [askError, setAskError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Intent | null>(null);
  const [quick, setQuick] = useState("");

  const columns = useMemo<ColDef<Intent>[]>(
    () => [
      { field: "created_at", headerName: "Time", width: 110, sort: "desc", valueFormatter: (p) => (p.value ? clock(p.value) : "") },
      {
        field: "agent_name",
        headerName: "Agent",
        width: 210,
        filter: "agTextColumnFilter",
        cellRenderer: (p: ICellRendererParams<Intent>) =>
          p.data ? (
            <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
              <Avatar name={p.data.agent_name} client={p.data.client} size={24} />
              {p.data.agent_name}
            </span>
          ) : null,
      },
      { field: "action", headerName: "Action", width: 100, filter: "agTextColumnFilter" },
      {
        field: "amount_value",
        headerName: "Amount",
        width: 120,
        type: "rightAligned",
        filter: "agNumberColumnFilter",
        cellClass: "num",
        valueFormatter: (p) => (p.data ? money(p.data.amount, p.data.currency) : ""),
      },
      { field: "currency", headerName: "Cur.", width: 80, filter: "agTextColumnFilter", hide: true },
      { field: "target", headerName: "To / payment", flex: 1, minWidth: 200, filter: "agTextColumnFilter", cellClass: "mono" },
      { field: "reference", headerName: "Reference", width: 140, cellClass: "mono" },
      {
        field: "status",
        headerName: "Status",
        width: 170,
        filter: "agTextColumnFilter",
        cellRenderer: (p: ICellRendererParams<Intent>) => (p.data ? <StatusPill status={p.data.status} /> : null),
      },
      {
        headerName: "Rules",
        width: 110,
        valueGetter: (p) => p.data?.rules.filter((r) => r.outcome !== "pass").length ?? 0,
        valueFormatter: (p) => (p.value ? `${p.value} flagged` : "all clear"),
      },
      { field: "attempts", headerName: "Tries", width: 80, type: "rightAligned" },
      { field: "paypal_id", headerName: "PayPal ID", width: 180, cellClass: "mono" },
      { field: "confirmed_status", headerName: "PayPal says", width: 130 },
      { field: "backend", headerName: "Backend", width: 110 },
    ],
    [],
  );

  const ask = useCallback(
    async (text: string) => {
      if (!text.trim() || !grid.current) return;
      setAsking(true);
      setAskError(null);
      try {
        const result = await api.askGrid(text);
        grid.current.setFilterModel(result.filter_model);
        grid.current.applyColumnState({ state: result.sort, defaultState: { sort: null } });
        setAiSummary(result.summary);
      } catch (err) {
        setAskError((err as Error).message);
      } finally {
        setAsking(false);
      }
    },
    [grid],
  );

  const clear = () => {
    grid.current?.setFilterModel(null);
    grid.current?.applyColumnState({ state: [{ colId: "created_at", sort: "desc" }], defaultState: { sort: null } });
    setAiSummary(null);
    setQuestion("");
  };

  const executed = (data ?? []).filter((i) => i.status === "executed");
  const paidTotals = addTotals(...executed.map((i) => ({ [i.currency]: i.amount_value ?? 0 })));

  return (
    <>
      <header className="page-head">
        <div>
          <div className="eyebrow">Money trail</div>
          <h1 className="page-title">What every agent asked for, and what PayPal did.</h1>
          <p className="page-sub">
            Each row is one money move: the agent's request, the rules that judged it, your decision, and PayPal's own
            confirmation, kept separate from what the agent was told.
          </p>
        </div>
      </header>

      <form
        className="card ask"
        onSubmit={(e) => {
          e.preventDefault();
          ask(question);
        }}
      >
        <Sparkles size={18} color="var(--accent)" aria-hidden="true" />
        <label htmlFor="ask" className="sr-only">
          Ask the money trail
        </label>
        <input
          id="ask"
          className="input"
          placeholder={status.ai_explanations ? `Ask the money trail, e.g. "${EXAMPLES[0]}"` : "Ask the money trail (needs ANTHROPIC_API_KEY)"}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          disabled={!status.ai_explanations}
        />
        <button className="btn btn-primary" disabled={asking || !status.ai_explanations || !question.trim()}>
          {asking ? "Asking Claude…" : "Ask"}
        </button>
      </form>

      <div className="toolbar">
        {aiSummary ? (
          <span className="badge badge-accent">
            <Sparkles size={12} /> {aiSummary}
            <button className="btn btn-ghost" style={{ height: 20, padding: "0 4px" }} onClick={clear} aria-label="Clear AI filter">
              <X size={13} />
            </button>
          </span>
        ) : (
          status.ai_explanations &&
          EXAMPLES.slice(1).map((example) => (
            <button key={example} className="badge" style={{ border: 0, cursor: "pointer" }} onClick={() => (setQuestion(example), ask(example))}>
              {example}
            </button>
          ))
        )}
        {askError && <span className="error-text">{askError}</span>}
        <span style={{ flex: 1 }} />
        <input className="input" placeholder="Quick search" value={quick} onChange={(e) => setQuick(e.target.value)} style={{ width: 200 }} />
        <span className="muted num">
          {executed.length} paid · {moneyTotals(paidTotals)}
        </span>
        <button className="btn" onClick={() => grid.current?.exportDataAsCsv({ fileName: "countersign-money-trail.csv" })}>
          <Download size={15} /> CSV
        </button>
      </div>

      {error && <p className="error-text">{error}</p>}
      <div className="grid-wrap">
        <AgGridReact<Intent>
          theme={gridTheme}
          rowData={data ?? []}
          columnDefs={columns}
          defaultColDef={{ sortable: true, resizable: true }}
          getRowId={(p) => p.data.id}
          quickFilterText={quick}
          animateRows
          onGridReady={(e) => (grid.current = e.api)}
          onRowClicked={(e) => setSelected(e.data ?? null)}
          overlayNoRowsTemplate="<span>No money moves yet. Connect an agent to get started.</span>"
        />
      </div>

      {selected && <IntentDrawer intent={selected} onClose={() => setSelected(null)} />}
    </>
  );
}

function IntentDrawer({ intent, onClose }: { intent: Intent; onClose: () => void }) {
  return (
    <>
      <div className="drawer-back" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-label={`Money move ${intent.id}`}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <StatusPill status={intent.status} />
          <button className="btn btn-ghost" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </div>
        <div className="hold-move">
          <span className="hold-action">{intent.action}</span>
          <span className="hold-amount num">{money(intent.amount, intent.currency)}</span>
        </div>
        <dl className="kv">
          <dt>Agent</dt>
          <dd>{intent.agent_name}</dd>
          <dt>To / payment</dt>
          <dd className="mono">{intent.target}</dd>
          <dt>Reference</dt>
          <dd className="mono">{intent.reference}</dd>
          <dt>Intent</dt>
          <dd className="mono">{intent.id}</dd>
          <dt>PayPal-Request-Id</dt>
          <dd className="mono" title="One per intent; every retry reuses it, so PayPal never pays twice">{intent.request_id}</dd>
          <dt>Attempts</dt>
          <dd>{intent.attempts}</dd>
          <dt>Decided by</dt>
          <dd>{intent.decided_by ?? (intent.status === "allowed" || intent.status === "executed" ? "rules (within mandate)" : "—")}</dd>
          <dt>PayPal ID</dt>
          <dd className="mono">{intent.paypal_id ?? "—"}</dd>
          <dt>PayPal says</dt>
          <dd>{intent.confirmed_status ?? (intent.paypal_status ? `${intent.paypal_status} (at execution)` : "—")}</dd>
          <dt>Backend</dt>
          <dd>{intent.backend === "sandbox" ? "PayPal Sandbox" : "Simulated PayPal"}</dd>
          {intent.error && (
            <>
              <dt>Error</dt>
              <dd className="error-text">{intent.error}</dd>
            </>
          )}
        </dl>
        <div className="eyebrow">Rule receipt</div>
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
      </aside>
    </>
  );
}
