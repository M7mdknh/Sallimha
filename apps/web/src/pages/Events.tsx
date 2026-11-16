import { useEffect } from "react";

import { api } from "../api/client";
import { Empty, LoadFailed, SkeletonRows, StatusPill } from "../components/States";
import { navigate } from "../router";
import { useT } from "../strings";
import { usePoll } from "../usePoll";
import { rememberZone } from "../venueTime";

export function Events() {
  const { t, state } = useT();
  const { data, error, refresh } = usePoll(api.events, 30_000, []);
  const open = data?.filter((e) => e.status === "OPEN") ?? [];

  useEffect(() => {
    if (open.length === 1) rememberZone(open[0].time_zone);
    if (open.length === 1) navigate(`/events/${open[0].id}`, true);
  }, [open.length]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <main className="page">
      <h1>{t("chooseEvent")}</h1>
      {data === null && error ? <LoadFailed onRetry={refresh} /> : null}
      {data === null && !error ? <SkeletonRows /> : null}
      {data && data.length === 0 ? <Empty text={t("noEvents")} /> : null}
      <ul className="list">
        {data?.map((e) => (
          <li key={e.id}>
            <a className="row-link" href={`/events/${e.id}`} onClick={(ev) => { ev.preventDefault(); navigate(`/events/${e.id}`); }}>
              <span className="row-title">{e.name}</span>
              <span className="muted">{e.venue}</span>
              <StatusPill tone={e.status === "OPEN" ? "success" : "neutral"} icon={e.status === "OPEN" ? "check" : "clock"} label={state(e.status)} />
            </a>
          </li>
        ))}
      </ul>
    </main>
  );
}
