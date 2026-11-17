import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, api, type ValetWork } from "../api/client";

const VISIBLE_MS = 3_000;

export type Connection = "ok" | "offline";

/** The valet's work, polled while the app is in front and refreshed the moment it comes back (tab shown, network
 *  back). A failed poll keeps the last answer on screen but marks the connection as lost; nothing is assumed. */
export function useWork() {
  const [work, setWork] = useState<ValetWork | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [connection, setConnection] = useState<Connection>("ok");
  const [checkedAt, setCheckedAt] = useState<number | null>(null);
  const offset = useRef(0); // server clock minus device clock, so countdowns use the server's deadlines
  const inFlight = useRef<Promise<void> | null>(null);

  const refresh = useCallback((): Promise<void> => {
    inFlight.current ??= (async () => {
      try {
        const value = await api.valet.work();
        offset.current = new Date(value.server_time).getTime() - Date.now();
        setWork(value);
        setError(null);
        setConnection("ok");
        setCheckedAt(Date.now());
      } catch (err) {
        setError(err);
        if (!(err instanceof ApiError) || err.status === 0 || err.status >= 500) setConnection("offline");
      } finally {
        inFlight.current = null;
      }
    })();
    return inFlight.current;
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void refresh();
    }, VISIBLE_MS);
    const onVisible = () => { if (document.visibilityState === "visible") void refresh(); };
    const onOffline = () => setConnection("offline");
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("online", onVisible);
    window.addEventListener("focus", onVisible);
    window.addEventListener("offline", onOffline);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("online", onVisible);
      window.removeEventListener("focus", onVisible);
      window.removeEventListener("offline", onOffline);
    };
  }, [refresh]);

  const serverNow = useCallback(() => Date.now() + offset.current, []);
  return { work, error, connection, checkedAt, refresh, serverNow };
}
