import { useCallback, useEffect, useState } from "react";

import { ApiError, api, type Me } from "./api/client";
import { Shell } from "./components/Shell";
import { LoadFailed, SkeletonRows } from "./components/States";
import { Events } from "./pages/Events";
import { Live } from "./pages/Live";
import { Login } from "./pages/Login";
import { Simulator } from "./pages/Simulator";
import { navigate, usePath } from "./router";

type Session = { status: "loading" } | { status: "anonymous" } | { status: "error" } | { status: "ready"; me: Me };

export function App() {
  const path = usePath();
  const [session, setSession] = useState<Session>({ status: "loading" });

  const load = useCallback(async () => {
    try {
      setSession({ status: "ready", me: await api.me() });
    } catch (err) {
      setSession(err instanceof ApiError && err.status !== 0 ? { status: "anonymous" } : { status: "error" });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (session.status === "anonymous" && path !== "/login") navigate("/login", true);
    if (session.status === "ready" && path === "/login") navigate("/", true);
  }, [session.status, path]);

  if (session.status === "loading") return <main className="page"><SkeletonRows /></main>;
  if (session.status === "error") return <main className="page"><LoadFailed onRetry={load} /></main>;
  if (session.status === "anonymous") return <Login onSignedIn={load} />;

  const live = path.match(/^\/events\/(\d+)(?:\/tickets\/(\d+))?/);
  const eventId = live ? Number(live[1]) : undefined;
  let page = <Events />;
  if (live) rememberEvent(eventId!);
  if (live) page = <Live eventId={eventId!} ticketId={live[2] ? Number(live[2]) : undefined} />;
  else if (path === "/dev/simulator") page = <Simulator />;
  return (
    <Shell me={session.me} eventId={eventId ?? lastEvent()}>
      {page}
    </Shell>
  );
}

// Remember the event last opened so the "Live operations" link survives a visit to the simulator.
function lastEvent(): number | undefined {
  try {
    const value = window.sessionStorage.getItem("sallimha.event");
    return value ? Number(value) : undefined;
  } catch {
    return undefined;
  }
}

export function rememberEvent(eventId: number) {
  try {
    window.sessionStorage.setItem("sallimha.event", String(eventId));
  } catch {
    // storage unavailable: the link falls back to the events list
  }
}
