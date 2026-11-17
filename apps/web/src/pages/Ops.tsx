import { useEffect, useState } from "react";

import { api, isAdmin, type Me } from "../api/client";
import { Icon } from "../components/Icon";
import { Empty, LoadFailed, SkeletonRows, StatusPill } from "../components/States";
import { navigate, usePath } from "../router";
import { useT, type StringKey } from "../strings";
import { usePoll } from "../usePoll";
import { rememberZone } from "../venueTime";

/** Operations' sections: cars first, then incidents, carryover (admins) and outages. One row of tabs, the same on
 *  every Operations screen, so supervisors never hunt through the top navigation for an exception. */
export function OpsTabs({ me, eventId }: { me: Me; eventId?: number }) {
  const { t } = useT();
  const path = usePath();
  const tabs: [string, StringKey, string][] = [];
  if (eventId) tabs.push([`/events/${eventId}`, "opsCars", "car"], [`/events/${eventId}/incidents`, "navIncidents", "alert"]);
  if (isAdmin(me)) tabs.push(["/carryover", "navCarryover", "key"]);
  tabs.push(["/outages", "navOutages", "message"]);
  const current = tabs.map(([href]) => href).filter((href) =>
    path === href || path.startsWith(`${href}/`) || (href.endsWith(`/${eventId}`) && path.includes(`/${eventId}/tickets`)))
    .sort((a, b) => b.length - a.length)[0];
  return (
    <nav className="subtabs" aria-label={t("navOps")}>
      {tabs.map(([href, label, icon]) => (
        <a key={href} href={href} aria-current={href === current ? "page" : undefined}
          onClick={(e) => { e.preventDefault(); navigate(href); }}>
          <Icon name={icon} size={18} /> {t(label)}
        </a>
      ))}
    </nav>
  );
}

/** /operations: the pilot runs one operation at a time, so the open one opens directly. */
export function OpsHome({ me }: { me: Me }) {
  const { t, state } = useT();
  const { data, error, refresh } = usePoll(api.events, 30_000, []);
  const open = data?.filter((e) => e.status === "OPEN") ?? [];
  useEffect(() => {
    if (open.length === 1) {
      rememberZone(open[0].time_zone);
      navigate(`/events/${open[0].id}`, true);
    }
  }, [open.length]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <main className="page">
      <h1>{t("navOps")}</h1>
      {data === null && error ? <LoadFailed onRetry={refresh} /> : null}
      {data === null && !error ? <SkeletonRows /> : null}
      {data && open.length === 0 ? (
        <section className="state-block">
          <Icon name="clock" />
          <h2>{t("opsNoOperation")}</h2>
          <p className="muted">{isAdmin(me) ? t("opsNoOperationBody") : t("opsNoOperationSupervisor")}</p>
          {isAdmin(me) ? (
            <button type="button" className="btn btn-primary" onClick={() => navigate("/settings/operation")}>
              {t("navEvents")}
            </button>
          ) : null}
        </section>
      ) : null}
      {open.length > 1 ? (
        <>
          <h2>{t("opsChoose")}</h2>
          <ul className="list">
            {open.map((e) => (
              <li key={e.id}>
                <a className="row-link" href={`/events/${e.id}`}
                  onClick={(ev) => { ev.preventDefault(); rememberZone(e.time_zone); navigate(`/events/${e.id}`); }}>
                  <span className="row-title">{e.name}</span>
                  <span className="muted">{e.venue}</span>
                  <StatusPill tone="success" icon="check" label={state(e.status)} />
                </a>
              </li>
            ))}
          </ul>
        </>
      ) : null}
      {data && data.length === 0 ? <Empty text={t("noEvents")} /> : null}
    </main>
  );
}

/** The operation a page works on: the one last opened in this tab, else the single open one. */
export function useActiveEvent(hint?: number): { eventId?: number; loading: boolean } {
  const [resolved, setResolved] = useState<number | undefined>(hint);
  const [loading, setLoading] = useState(hint === undefined);
  useEffect(() => {
    if (hint !== undefined) { setResolved(hint); setLoading(false); return; }
    let live = true;
    api.events().then((rows) => {
      const open = rows.filter((e) => e.status === "OPEN");
      if (live) {
        if (open.length === 1) rememberZone(open[0].time_zone);
        setResolved(open.length === 1 ? open[0].id : undefined);
      }
    }).catch(() => undefined).finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [hint]);
  return { eventId: resolved, loading };
}
