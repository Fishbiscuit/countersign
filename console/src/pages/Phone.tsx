import { HoldList } from "../components/HoldList";
import { SealMark } from "../components/Seal";
import type { Status } from "../lib/api";

/** Phone view: just the moves waiting for a signature, with big buttons. */
export function Phone({ status }: { status: Status }) {
  return (
    <main className="phone">
      <header style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
        <SealMark size={30} />
        <div>
          <div className="display" style={{ fontSize: 26, lineHeight: 1 }}>
            Countersign
          </div>
          <div className="muted" style={{ fontSize: 12 }}>
            {status.backend_label}
          </div>
        </div>
      </header>
      <HoldList status={status} via="phone" compact includeExpired={false} />
    </main>
  );
}
