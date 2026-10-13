import { useEffect, useRef, useState } from "react";
import { ApiError } from "../services/api";

export const POLL_INTERVAL_MS = 3000;

export interface PollState<T> {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
  lastSuccess: Date | null;
}

const INITIAL = { data: null, error: null, loading: true, lastSuccess: null };

/** Polls `load` sequentially; stale data is kept when a refresh fails. Changing `key` restarts polling. */
export function usePolling<T>(
  load: (signal: AbortSignal) => Promise<T>,
  key: string,
  intervalMs = POLL_INTERVAL_MS,
): PollState<T> {
  const [state, setState] = useState<PollState<T>>(INITIAL);
  const loadRef = useRef(load);

  useEffect(() => {
    loadRef.current = load;
  });

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    let controller: AbortController | undefined;
    setState(INITIAL);

    const tick = async () => {
      controller = new AbortController();
      try {
        const data = await loadRef.current(controller.signal);
        if (cancelled) return;
        setState({ data, error: null, loading: false, lastSuccess: new Date() });
      } catch (caught) {
        if (cancelled || (caught as Error).name === "AbortError") return;
        const error = caught instanceof ApiError ? caught : new ApiError("http", String(caught));
        setState((previous) => ({ ...previous, error, loading: false }));
      }
      if (!cancelled) timer = window.setTimeout(tick, intervalMs);
    };

    void tick();
    return () => {
      cancelled = true;
      controller?.abort();
      window.clearTimeout(timer);
    };
  }, [key, intervalMs]);

  return state;
}
