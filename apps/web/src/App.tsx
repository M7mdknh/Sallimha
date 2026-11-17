import { type ReactElement, useCallback, useEffect, useState } from "react";

import { ApiError, api, isAdmin, type Me } from "./api/client";
import { Shell } from "./components/Shell";
import { Forbidden, LoadFailed, SkeletonRows } from "./components/States";
import { Carryover } from "./pages/Carryover";
import { Dashboard } from "./pages/Dashboard";
import { Incidents } from "./pages/Incidents";
import { Integrations } from "./pages/Integrations";
import { Live } from "./pages/Live";
import { Login } from "./pages/Login";
import { Manage } from "./pages/Manage";
import { Operations } from "./pages/Operations";
import { OpsHome } from "./pages/Ops";
import { Outages } from "./pages/Outages";
import { Report } from "./pages/Report";
import { Settings } from "./pages/Settings";
import { Simulator } from "./pages/Simulator";
import { Team } from "./pages/Team";
import { navigate, usePath } from "./router";
import { lastEvent, rememberEvent } from "./session";
import { ValetApp } from "./valet/ValetApp";

type Session = { status: "loading" } | { status: "anonymous" } | { status: "error" } | { status: "ready"; me: Me };

/** Where each role starts: valets on their work, supervisors on Operations, admins on the Dashboard. */
export const homeFor = (me: Me) => (me.role === "VALET" ? "/work" : isAdmin(me) ? "/dashboard" : "/operations");

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
    if (session.status === "ready" && (path === "/login" || path === "/")) navigate(homeFor(session.me), true);
  }, [session, path]);

  if (session.status === "loading") return <main className="page"><SkeletonRows /></main>;
  if (session.status === "error") return <main className="page"><LoadFailed onRetry={load} /></main>;
  if (session.status === "anonymous") return <Login onSignedIn={load} />;

  const me = session.me;
  if (me.role === "VALET") return <ValetApp me={me} />;

  const scoped = path.match(/^\/events\/(\d+)(?:\/(tickets|incidents|report)(?:\/(\d+))?)?\/?$/);
  const eventId = scoped ? Number(scoped[1]) : undefined;
  if (eventId) rememberEvent(eventId);
  const sub = scoped?.[3] ? Number(scoped[3]) : undefined;
  const adminOnly = (page: () => ReactElement) => () => (isAdmin(me) ? page() : <main className="page"><Forbidden /></main>);
  const pages: Record<string, () => ReactElement> = {
    "/operations": () => <OpsHome me={me} />,
    "/team": () => <Team me={me} eventHint={lastEvent()} />,
    "/staff": () => <Team me={me} eventHint={lastEvent()} />,
    "/outages": () => <Outages me={me} eventId={lastEvent()} />,
    "/carryover": adminOnly(() => <Carryover me={me} eventId={lastEvent()} />),
    "/dashboard": adminOnly(() => <Dashboard me={me} eventHint={lastEvent()} />),
    "/settings": adminOnly(() => <Settings me={me} />),
    "/settings/operation": adminOnly(() => <Manage me={me} />),
    "/settings/delivery": adminOnly(() => <Operations me={me} />),
    "/settings/whatsapp": adminOnly(() => <Integrations me={me} />),
  };
  let page = <OpsHome me={me} />;
  if (scoped && scoped[2] === "incidents") page = <Incidents eventId={eventId!} incidentId={sub} me={me} />;
  else if (scoped && scoped[2] === "report") page = <Report eventId={eventId!} me={me} />;
  else if (scoped) page = <Live me={me} eventId={eventId!} ticketId={scoped[2] === "tickets" ? sub : undefined} />;
  else if (pages[path]) page = pages[path]();
  else if (path === "/dev/simulator" && me.simulator) page = <Simulator me={me} />;
  return (
    <Shell me={me} eventId={eventId ?? lastEvent()}>
      {page}
    </Shell>
  );
}
