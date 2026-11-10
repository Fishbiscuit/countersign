import "@bryntum/core-community/fontawesome/css/fontawesome.css";
import "@bryntum/core-community/fontawesome/css/solid.css";
import "@bryntum/scheduler-community/scheduler.css";
import "@bryntum/scheduler-community/svalbard-light.css";
import { BryntumScheduler } from "@bryntum/scheduler-react-community";
import { useMemo } from "react";
import { api } from "../lib/api";
import { money } from "../lib/format";
import { useLoad } from "../lib/live";

const WINDOW_MS = 2 * 60 * 60 * 1000;
const MIN_SPAN_MS = 30 * 60 * 1000;
const MIN_EVENT_MS = 3 * 60 * 1000;

/** Agent activity on a time axis: one row per agent, one bar per money move, from request to decision. */
export default function Timeline() {
  const agents = useLoad(() => api.agents());
  const intents = useLoad(() => api.intents());

  const { resources, events, start, end } = useMemo(() => {
    const now = Date.now();
    const recent = (intents.data ?? []).filter((i) => now - new Date(i.created_at).getTime() < WINDOW_MS);
    return {
      resources: (agents.data ?? []).filter((a) => !a.name.startsWith("Bench readiness")).map((a) => ({ id: a.id, name: a.name })),
      events: recent.map((i) => {
        const startDate = new Date(i.created_at);
        const finished = i.decided_at ?? (["executed", "blocked", "failed", "denied", "expired"].includes(i.status) ? i.updated_at : null);
        const endDate = new Date(Math.max(startDate.getTime() + MIN_EVENT_MS, finished ? new Date(finished).getTime() : now));
        return {
          id: i.id,
          resourceId: i.agent_id,
          startDate,
          endDate,
          name: `${i.action === "refund" ? "Refund" : "Payout"} ${money(i.amount, i.currency)}`,
          cls: `cs-${i.status}`,
          // Pale pine family, butter yellow and deep burgundy, as in styles.css
          eventColor: i.status === "executed" ? "#2d6a4b" : i.status === "held" ? "#e8c24f" : ["denied", "blocked", "failed"].includes(i.status) ? "#7a1f35" : "#2c5b4e",
        };
      }),
      ...window_(recent.map((i) => new Date(i.created_at).getTime()), now),
    };
  }, [agents.data, intents.data]);

  if (!agents.data || !intents.data) return <p className="muted card-pad">Loading timeline…</p>;
  if (resources.length === 0) return <p className="muted card-pad">Connect an agent to see its activity here.</p>;

  return (
    <BryntumScheduler
      readOnly
      startDate={start}
      endDate={end}
      viewPreset="minuteAndHour"
      rowHeight={44}
      barMargin={7}
      columns={[{ text: "Agent", field: "name", width: 200 }]}
      resources={resources}
      events={events}
      eventStyle="rounded"
      eventTooltipFeature
      eventDragFeature={false}
      eventDragCreateFeature={false}
      eventResizeFeature={false}
      eventEditFeature={false}
      cellMenuFeature={false}
      eventMenuFeature={false}
      scheduleMenuFeature={false}
    />
  );
}

/** Fit the time axis to the activity: from just before the first move to just after now, at least 30 minutes. */
function window_(starts: number[], now: number): { start: Date; end: Date } {
  const first = starts.length ? Math.min(...starts) : now - MIN_SPAN_MS;
  const end = now + 5 * 60 * 1000;
  const start = Math.min(first - 5 * 60 * 1000, end - MIN_SPAN_MS);
  return { start: new Date(start), end: new Date(end) };
}
