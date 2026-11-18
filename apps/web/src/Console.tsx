import type { ReactElement } from "react";

import { isAdmin, type Me } from "./api/client";
import { Shell } from "./components/Shell";
import { Forbidden } from "./components/States";
import { Carryover } from "./pages/Carryover";
import { Dashboard } from "./pages/Dashboard";
import { Incidents } from "./pages/Incidents";
import { Integrations } from "./pages/Integrations";
import { Live } from "./pages/Live";
import { Manage } from "./pages/Manage";
import { Operations } from "./pages/Operations";
import { OpsHome } from "./pages/Ops";
import { Outages } from "./pages/Outages";
import { Report } from "./pages/Report";
import { Settings } from "./pages/Settings";
import { Simulator } from "./pages/Simulator";
import { Team } from "./pages/Team";
import { lastEvent, rememberEvent } from "./session";

/** The supervisor and admin console, loaded only for those roles: valets and the sign-in page never download it. */
export default function Console({ me, path }: { me: Me; path: string }) {
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
