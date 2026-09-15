/**
 * Shared `/api/v1/overview` (polled) + `/api/v1/config` (fetched once, manually refreshable)
 * state — the health ring (rail + page), the top bar's "updated at", and the Overview page's
 * cards all need the same data, so this follows the same Context + hook pattern as
 * `AuthContext.tsx` rather than each consumer polling independently.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { useApiClient } from "../api/useApiClient";
import type { ConfigView, OverviewResponse } from "../api/types";
import { usePolling } from "../hooks/usePolling";

const POLL_MS = 60_000;

interface OverviewContextValue {
  overview: OverviewResponse | null;
  config: ConfigView | null;
  error: unknown;
  loading: boolean;
  /** Re-polls /overview only (the top bar's plain "Aggiorna" action). */
  refresh: () => void;
  /** Re-fetches /overview and /config (the "Health check" action — a real, distinct, read-only
   * call, not just a relabeled refresh). */
  refreshAll: () => void;
  updatedAt: Date | null;
}

const OverviewContext = createContext<OverviewContextValue | null>(null);

export function OverviewProvider({ children }: { children: ReactNode }) {
  const { get } = useApiClient();

  const fetchOverview = useCallback(() => get<OverviewResponse>("/api/v1/overview"), [get]);
  const {
    data: overview,
    error,
    loading,
    refresh,
  } = usePolling<OverviewResponse>(fetchOverview, POLL_MS);

  const [config, setConfig] = useState<ConfigView | null>(null);
  const fetchConfig = useCallback(async () => {
    try {
      setConfig(await get<ConfigView>("/api/v1/config"));
    } catch {
      // Config is a secondary enrichment (blocklist freshness for the health score); a failure
      // here must not break the rest of the dashboard, which usePolling's own overview state
      // already handles independently.
    }
  }, [get]);

  useEffect(() => {
    void fetchConfig();
  }, [fetchConfig]);

  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  useEffect(() => {
    if (overview) setUpdatedAt(new Date());
  }, [overview]);

  const refreshAll = useCallback(() => {
    refresh();
    void fetchConfig();
  }, [refresh, fetchConfig]);

  const value = useMemo<OverviewContextValue>(
    () => ({ overview, config, error, loading, refresh, refreshAll, updatedAt }),
    [overview, config, error, loading, refresh, refreshAll, updatedAt],
  );

  return <OverviewContext.Provider value={value}>{children}</OverviewContext.Provider>;
}

export function useOverview(): OverviewContextValue {
  const value = useContext(OverviewContext);
  if (!value) throw new Error("useOverview must be used within an OverviewProvider");
  return value;
}
