/**
 * Polls `fetcher` every `intervalMs`, paused while the tab is hidden and resumed immediately
 * when it becomes visible again (Page Visibility API — docs/specs/a8-frontend-dashboard.md
 * §13). Never overlaps two in-flight requests. Errors are reported but never clear the last
 * good `data`, so a page keeps showing valid information through a transient failure.
 */
import { useCallback, useEffect, useRef, useState, type DependencyList } from "react";

export interface PollingResult<T> {
  data: T | null;
  error: unknown;
  loading: boolean;
  refresh: () => void;
}

export function usePolling<T>(
  fetcher: () => Promise<T>,
  intervalMs: number,
  deps: DependencyList = [],
): PollingResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const inFlight = useRef(false);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const run = useCallback(async () => {
    if (inFlight.current || document.hidden) return;
    inFlight.current = true;
    try {
      const result = await fetcherRef.current();
      setData(result);
      setError(null);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
      inFlight.current = false;
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    setData(null);
    void run();
    const intervalId = window.setInterval(() => void run(), intervalMs);
    const onVisibilityChange = () => {
      if (!document.hidden) void run();
    };
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      window.clearInterval(intervalId);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
    // `deps` intentionally drives a full re-subscribe (e.g. a changed device_id on the
    // Device Detail page); `run`/`intervalMs` are the hook's own stable inputs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs, run, ...deps]);

  return { data, error, loading, refresh: () => void run() };
}
