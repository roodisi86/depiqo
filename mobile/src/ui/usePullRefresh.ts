/**
 * Pull-to-refresh spinner only for a refresh the user started. Background refetches (after login, on focus,
 * after a change elsewhere) also set react-query's isRefetching; showing the spinner for those left a spinner
 * at the top of a loaded screen on iOS. The spinner stays from the pull until that refetch has finished.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

export function usePullRefresh(refreshing: boolean | undefined, onRefresh?: () => void) {
  const [pulled, setPulled] = useState(false);
  const wasRefreshing = useRef(false);

  useEffect(() => {
    if (pulled && wasRefreshing.current && !refreshing) setPulled(false);
    wasRefreshing.current = !!refreshing;
  }, [refreshing, pulled]);

  // Safety net: never leave the spinner on if the refetch finished before isRefetching was ever seen.
  useEffect(() => {
    if (!pulled) return undefined;
    const timer = setTimeout(() => setPulled(false), 15000);
    return () => clearTimeout(timer);
  }, [pulled]);

  const handle = useCallback(() => {
    setPulled(true);
    onRefresh?.();
  }, [onRefresh]);

  return { refreshing: pulled, onRefresh: handle };
}
