import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import type { StreamEvent } from "./api";

export interface LiveState {
  /** Increments whenever the money trail changes; pages refetch on it. */
  version: number;
  events: StreamEvent[];
  connected: boolean;
}

export const LiveContext = createContext<LiveState>({ version: 0, events: [], connected: false });

export function useLive(): LiveState {
  return useContext(LiveContext);
}

/** One EventSource for the whole console; reconnects with backoff. */
export function useLiveStream(enabled: boolean): LiveState {
  const [state, setState] = useState<LiveState>({ version: 0, events: [], connected: false });
  const retry = useRef(1000);

  useEffect(() => {
    if (!enabled) return;
    let source: EventSource | null = null;
    let timer: number | undefined;
    let closed = false;

    const open = () => {
      source = new EventSource("/api/stream", { withCredentials: true });
      source.onopen = () => {
        retry.current = 1000;
        setState((s) => ({ ...s, connected: true }));
      };
      source.onmessage = (message) => {
        const event = JSON.parse(message.data) as StreamEvent;
        setState((s) => ({ version: s.version + 1, connected: true, events: [event, ...s.events].slice(0, 80) }));
      };
      source.onerror = () => {
        source?.close();
        setState((s) => ({ ...s, connected: false }));
        if (!closed) timer = window.setTimeout(open, (retry.current = Math.min(retry.current * 2, 15000)));
      };
    };
    open();
    return () => {
      closed = true;
      source?.close();
      window.clearTimeout(timer);
    };
  }, [enabled]);

  return state;
}

/** Fetch something and refetch it whenever the live version changes. */
export function useLoad<T>(load: () => Promise<T>, deps: unknown[] = []): { data: T | undefined; error: string | null; reload: () => void } {
  const { version } = useLive();
  const [data, setData] = useState<T>();
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    let active = true;
    const timer = window.setTimeout(() => {
      load()
        .then((result) => active && (setData(result), setError(null)))
        .catch((err: Error) => active && setError(err.message));
    }, 120);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version, tick, ...deps]);

  return { data, error, reload };
}

/** Re-render every `ms` so countdowns and "ago" labels stay fresh. */
export function useNow(ms = 1000): number {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), ms);
    return () => window.clearInterval(timer);
  }, [ms]);
  return now;
}
