import { Activity, Bot, FlaskConical, Hourglass, ReceiptText, Settings2, Smartphone } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { HoldList } from "./components/HoldList";
import { SealMark } from "./components/Seal";
import { type Status, api } from "./lib/api";
import { LiveContext, useLoad, useLiveStream } from "./lib/live";
import { Agents } from "./pages/Agents";
import { Bench } from "./pages/Bench";
import { Live } from "./pages/Live";
import { Phone } from "./pages/Phone";
import { Setup } from "./pages/Setup";
import { SignIn } from "./pages/SignIn";
import { Trail } from "./pages/Trail";

const ROUTES = [
  { path: "/", label: "Live", icon: Activity },
  { path: "/holds", label: "Holds", icon: Hourglass },
  { path: "/trail", label: "Money trail", icon: ReceiptText },
  { path: "/agents", label: "Agents", icon: Bot },
  { path: "/bench", label: "Chaos bench", icon: FlaskConical },
  { path: "/setup", label: "Setup", icon: Settings2 },
] as const;

function usePath(): [string, (path: string) => void] {
  const [path, setPath] = useState(window.location.pathname);
  useEffect(() => {
    const onPop = () => setPath(window.location.pathname);
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  const go = useCallback((next: string) => {
    window.history.pushState({}, "", next);
    setPath(next);
    window.scrollTo(0, 0);
  }, []);
  return [path, go];
}

export function App() {
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState<string | null>(null);
  const refresh = useCallback(async () => {
    try {
      const params = new URLSearchParams(window.location.search);
      const token = params.get("token");
      if (token) {
        await api.login(token).catch(() => undefined);
        params.delete("token");
        window.history.replaceState({}, "", window.location.pathname + (params.size ? `?${params}` : ""));
      }
      setStatus(await api.status());
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);
  useEffect(() => {
    refresh();
  }, [refresh]);

  const live = useLiveStream(Boolean(status?.signed_in));

  if (error) return <p className="error-text" style={{ padding: 24 }}>Countersign is not reachable: {error}</p>;
  if (!status) return null;
  if (!status.signed_in) return <SignIn onSignedIn={refresh} />;

  return (
    <LiveContext.Provider value={live}>
      <Console status={status} connected={live.connected} />
    </LiveContext.Provider>
  );
}

function Console({ status, connected }: { status: Status; connected: boolean }) {
  const [path, go] = usePath();
  const held = useLoad(() => api.intents("held"));
  const heldCount = held.data?.length ?? 0;

  useEffect(() => {
    document.title = heldCount > 0 ? `(${heldCount}) Countersign` : "Countersign";
  }, [heldCount]);

  if (path === "/m") return <Phone status={status} />;

  return (
    <div className="shell">
      <header className="xp-titlebar">
        <div className="xp-window-title"><SealMark size={18} /><strong>Countersign</strong><span> — Agent payment console</span></div>
        <span className="xp-title-status">{status.backend_label}</span>
      </header>
      <nav className="sidebar" aria-label="Countersign">
        <a
          className="brand"
          href="/"
          onClick={(e) => {
            e.preventDefault();
            go("/");
          }}
        >
          <SealMark size={30} />
          <span className="brand-name">Countersign</span>
        </a>
        {ROUTES.map(({ path: to, label, icon: Icon }) => (
          <a
            key={to}
            href={to}
            className="nav-link"
            aria-current={path === to ? "page" : undefined}
            onClick={(e) => {
              e.preventDefault();
              go(to);
            }}
          >
            <Icon size={17} />
            {label}
            {to === "/holds" && heldCount > 0 && <span className="badge badge-held">{heldCount}</span>}
          </a>
        ))}
        <a className="nav-link" href="/m" target="_blank" rel="noreferrer">
          <Smartphone size={17} />
          Phone view
        </a>
        <div className="sidebar-foot">
          <div className={`backend-tag ${status.backend === "sandbox" ? "backend-sandbox" : "backend-sim"}`}>
            <strong>{status.backend_label}</strong>
            <span className="muted">
              {status.backend === "sandbox" ? "Real PayPal API · test money" : "No PayPal calls · simulated money"}
            </span>
          </div>
          <span className="muted" style={{ fontSize: 12, display: "flex", alignItems: "center", gap: 6 }}>
            <span className="dot" style={{ color: connected && status.gateway_running ? "var(--ok)" : "var(--seal)" }} />
            {status.gateway_running ? (connected ? "Gateway live" : "Reconnecting…") : "Gateway stopped"}
          </span>
        </div>
      </nav>
      <main className="main">
        {path === "/" && <Live status={status} />}
        {path === "/holds" && (
          <>
            <header className="page-head">
              <div>
                <div className="eyebrow">Holds</div>
                <h1 className="page-title">Waiting for your signature.</h1>
                <p className="page-sub">
                  The agent is paused on each of these. Countersign it and the money moves; deny it and nothing is paid. Expired
                  holds can still be approved; the agent's retry then goes through.
                </p>
              </div>
            </header>
            <div style={{ maxWidth: 860 }}>
              <HoldList status={status} via="console" />
            </div>
          </>
        )}
        {path === "/trail" && <Trail status={status} />}
        {path === "/agents" && <Agents status={status} />}
        {path === "/bench" && <Bench />}
        {path === "/setup" && <Setup status={status} />}
      </main>
      <footer className="xp-statusbar">
        <span>{status.gateway_running ? (connected ? "Gateway connected" : "Reconnecting to gateway…") : "Gateway stopped"}</span>
        <span>{status.backend === "sandbox" ? "PayPal Sandbox · test money" : "Simulated PayPal · no PayPal calls"}</span>
      </footer>
    </div>
  );
}
