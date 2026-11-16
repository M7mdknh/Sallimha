import { type ReactElement, useCallback, useEffect, useState } from "react";

import { ApiError, api, type Me } from "./api/client";
import { Shell } from "./components/Shell";
import { LoadFailed, SkeletonRows } from "./components/States";
import { Carryover } from "./pages/Carryover";
import { Events } from "./pages/Events";
import { Incidents } from "./pages/Incidents";
import { Integrations } from "./pages/Integrations";
import { Live } from "./pages/Live";
import { Login } from "./pages/Login";
import { Manage } from "./pages/Manage";
import { Operations } from "./pages/Operations";
import { Outages } from "./pages/Outages";
import { Report } from "./pages/Report";
import { Settings } from "./pages/Settings";
import { Simulator } from "./pages/Simulator";
import { Staff } from "./pages/Staff";
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

  const me = session.me;
  const scoped = path.match(/^\/events\/(\d+)(?:\/(tickets|incidents|report)(?:\/(\d+))?)?\/?$/);
  const eventId = scoped ? Number(scoped[1]) : undefined;
  if (eventId) rememberEvent(eventId);
  const sub = scoped?.[3] ? Number(scoped[3]) : undefined;
  const pages: Record<string, () => ReactElement> = {
    "/manage": () => <Manage />,
    "/staff": () => <Staff me={me} />,
    "/carryover": () => <Carryover />,
    "/settings": () => <Settings />,
    "/operations": () => <Operations />,
    "/integrations": () => <Integrations />,
    "/outages": () => <Outages me={me} eventId={lastEvent()} />,
  };
  let page = <Events />;
  if (scoped && scoped[2] === "incidents") page = <Incidents eventId={eventId!} incidentId={sub} me={me} />;
  else if (scoped && scoped[2] === "report") page = <Report eventId={eventId!} me={me} />;
  else if (scoped) page = <Live eventId={eventId!} ticketId={scoped[2] === "tickets" ? sub : undefined} />;
  else if (pages[path]) page = pages[path]();
  else if (path === "/dev/simulator" && me.simulator) page = <Simulator />;
  return (
    <Shell me={me} eventId={eventId ?? lastEvent()}>
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
