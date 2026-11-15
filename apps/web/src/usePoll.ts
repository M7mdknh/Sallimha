import { useCallback, useEffect, useRef, useState } from "react";

const STALE_AFTER_MS = 10_000;

/** Polls a read endpoint. `stale` is true after a failed poll or when the last success is too old. */
export function usePoll<T>(fetcher: () => Promise<T>, intervalMs: number, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [lastSuccess, setLastSuccess] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const refresh = useCallback(async () => {
    try {
      const value = await fetcherRef.current();
      setData(value);
      setError(null);
      setLastSuccess(Date.now());
    } catch (err) {
      setError(err);
    }
  }, []);

  useEffect(() => {
    setData(null);
    setError(null);
    setLastSuccess(null);
    void refresh();
    const timer = window.setInterval(() => {
      setNow(Date.now());
      void refresh();
    }, intervalMs);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  const stale = data !== null && (error !== null || (lastSuccess !== null && now - lastSuccess > STALE_AFTER_MS));
  return { data, error, stale, lastSuccess, refresh };
}
