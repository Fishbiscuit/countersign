import { useState } from "react";
import { SealMark } from "../components/Seal";
import { api } from "../lib/api";

export function SignIn({ onSignedIn }: { onSignedIn: () => void }) {
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  return (
    <main className="signin">
      <form
        className="card"
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            await api.login(token.trim());
            onSignedIn();
          } catch (err) {
            setError((err as Error).message);
          }
        }}
      >
        <SealMark size={44} />
        <h1 className="page-title" style={{ fontSize: 38, marginTop: 14 }}>
          Countersign
        </h1>
        <p className="muted">Paste the admin token from the server log, or open the sign-in link it printed.</p>
        <label className="field">
          <span>Admin token</span>
          <input className="input" type="password" autoComplete="current-password" value={token} onChange={(e) => setToken(e.target.value)} autoFocus />
        </label>
        {error && <p className="error-text">{error}</p>}
        <button className="btn btn-primary btn-lg" style={{ width: "100%", marginTop: 14 }} disabled={!token.trim()}>
          Sign in
        </button>
      </form>
    </main>
  );
}
