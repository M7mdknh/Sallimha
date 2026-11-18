import { useEffect, useState } from "react";

import { ApiError, api, type Dashboard as Board, type EventSummary, type Me } from "../api/client";
import { ActivityChart } from "../components/ActivityChart";
import { Icon } from "../components/Icon";
import { Empty, Id, PageData, StaleBanner, StatusPill } from "../components/States";
import { navigate } from "../router";
import { rememberEvent } from "../session";
import { useT } from "../strings";
import { usePoll } from "../usePoll";
import { venueClock, venueTime } from "../venueTime";
import { formatElapsed } from "./Live";

const Duration = ({ seconds }: { seconds: number | null | undefined }) =>
  <Id>{seconds === null || seconds === undefined ? "—" : formatElapsed(seconds)}</Id>;

const STATUS: Record<string, [string, string]> = {
  available: ["success", "check"], busy: ["info", "car"], unavailable: ["neutral", "clock"],
};

/** Four counts in one band: what is parked, who is waiting, what was delivered, how long a request takes to be ready
 *  (defined on screen). No scores and no invented figures. */
function Figures({ d }: { d: Board }) {
  const { t } = useT();
  const r2r = d.request_to_ready;
  return (
    <ul className="figures" aria-label={t("dashTitle")}>
      <li data-testid="metric-parked">
        <span className="figure-label">{t("dashParked")}</span>
        <span className="figure-n"><Id>{d.cars.parked}</Id></span>
        <span className="figure-sub">{t("dashReceiving")} <Id>{d.cars.receiving}</Id></span>
      </li>
      <li data-testid="metric-waiting" className={d.delayed_requests ? "is-late" : d.waiting_requests ? "is-attention" : ""}>
        <span className="figure-label">{t("dashWaiting")}</span>
        <span className="figure-n"><Id>{d.waiting_requests}</Id></span>
        <span className="figure-sub">
          {d.delayed_requests ? <><Icon name="alert" size={14} /> {t("dashDelayed")} <Id>{d.delayed_requests}</Id> · </> : null}
          {t("dashOldest")} <Duration seconds={d.oldest_wait_s} />
        </span>
      </li>
      <li data-testid="metric-delivered">
        <span className="figure-label">{t("dashDelivered")}</span>
        <span className="figure-n"><Id>{d.cars.delivered}</Id></span>
        <span className="figure-sub">{t("dashOnTheWay")} <Id>{d.cars.retrieving + d.cars.ready}</Id></span>
      </li>
      <li data-testid="request-to-ready">
        <span className="figure-label">{t("dashRequestToReady")}</span>
        <span className="figure-n">{r2r.count ? <Duration seconds={r2r.median_s} /> : "—"}</span>
        <span className="figure-sub">{r2r.count
          ? <>{t("dashMedian")} · {t("dashP95")} <Duration seconds={r2r.p95_s} /> · <Id>{r2r.count}</Id> {t("dashRequests")}</>
          : t("dashNoData")}</span>
      </li>
    </ul>
  );
}

function Problems({ d }: { d: Board }) {
  const { t } = useT();
  const p = d.problems;
  const total = p.alerts + p.incidents + p.holds;
  return (
    <section className="dash-section" aria-labelledby="prob-h" data-testid="dash-problems">
      <h2 id="prob-h">{t("dashProblems")} {total ? <span className="count-badge is-alert"><Id>{total}</Id></span> : null}</h2>
      {total === 0 ? <p className="quiet-ok"><Icon name="check" size={18} /> {t("problemsEmpty")}</p> : (
        <ul className="problem-tally">
          {p.critical ? <li className="is-critical"><StatusPill tone="danger" icon="alert" label={t("dashCritical")} /> <Id>{p.critical}</Id></li> : null}
          {p.alerts - p.critical ? <li><StatusPill tone="warning" icon="clock" label={t("dashAlerts")} /> <Id>{p.alerts - p.critical}</Id></li> : null}
          {p.incidents ? <li><StatusPill tone="warning" icon="alert" label={t("dashIncidents")} /> <Id>{p.incidents}</Id></li> : null}
          {p.holds ? <li><StatusPill tone="danger" icon="shield" label={t("dashHolds")} /> <Id>{p.holds}</Id></li> : null}
        </ul>
      )}
      <button type="button" className="btn btn-secondary" onClick={() => navigate(`/events/${d.event.id}`)}>
        {t("dashOpenOps")}
      </button>
    </section>
  );
}

function Team({ d }: { d: Board }) {
  const { t, state } = useT();
  return (
    <section className="dash-section" aria-labelledby="dteam-h" data-testid="dash-team">
      <h2 id="dteam-h">{t("dashTeam")}</h2>
      <p className="team-glance">
        <StatusPill tone="success" icon="check" label={`${state("available")} ${d.team.available}`} />
        <StatusPill tone="info" icon="car" label={`${state("busy")} ${d.team.busy}`} />
        <StatusPill tone="neutral" icon="clock" label={`${state("unavailable")} ${d.team.unavailable}`} />
        {d.team.not_started ? <span className="muted">{t("dashNotStarted")} <Id>{d.team.not_started}</Id></span> : null}
      </p>
      {d.team.members.length === 0 ? <Empty text={t("teamNobodyOnShift")} /> : (
        <div className="table-wrap">
          <table className="table team-table">
            <thead><tr><th scope="col">{t("dashColName")}</th><th scope="col">{t("dashColStatus")}</th>
              <th scope="col">{t("dashColTask")}</th><th scope="col" className="num">{t("dashParkedBy")}</th>
              <th scope="col" className="num">{t("dashDeliveredBy")}</th></tr></thead>
            <tbody>
              {d.team.members.map((m) => {
                const [tone, icon] = STATUS[m.status];
                return (
                  <tr key={m.staff_id}>
                    <th scope="row">{m.name}</th>
                    <td><StatusPill tone={tone} icon={icon} label={state(m.status)} /></td>
                    <td><Id>{m.task ?? "—"}</Id></td>
                    <td className="num"><Id>{m.parked}</Id></td>
                    <td className="num"><Id>{m.delivered}</Id></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function Body({ d }: { d: Board }) {
  const { t, lang } = useT();
  useEffect(() => rememberEvent(d.event.id), [d.event.id]);
  const zone = d.event.time_zone;
  const start = venueTime(d.event.period.start, lang, zone);
  const end = d.event.period.end ? venueTime(d.event.period.end, lang, zone) : t("dashOngoing");
  return (
    <>
      <p className="dash-scope">
        <strong>{d.event.name}</strong> · {d.event.venue} · <bdi>{start}</bdi> – <bdi>{end}</bdi>
        <span className="muted"> · {t("lastUpdate")} <Id>{venueClock(d.generated_at, lang, zone)}</Id></span>
      </p>
      <Figures d={d} />
      <p className="figure-def" data-testid="request-to-ready-def"><strong>{t("dashRequestToReady")}:</strong> {t("dashRequestToReadyDef")}</p>
      <section className="dash-section" aria-labelledby="act-h" data-testid="activity">
        <h2 id="act-h">{t("activityTitle")}</h2>
        <ActivityChart hours={d.activity} zone={zone} />
      </section>
      <div className="dash-cols">
        <Problems d={d} />
        <Team d={d} />
      </div>
      <a className="row-link" href={`/events/${d.event.id}/report`}
        onClick={(e) => { e.preventDefault(); navigate(`/events/${d.event.id}/report`); }}>
        <Icon name="chevron" /> <span className="row-title">{t("dashFullReport")}</span>
      </a>
    </>
  );
}

/** Admin dashboard (ADR-0011, ADR-0013): the selected operation's period at a glance, then the team and the problems.
 *  Add staff is always one tap away. */
export function Dashboard({ me: _me, eventHint }: { me: Me; eventHint?: number }) {
  const { t, state } = useT();
  const [events, setEvents] = useState<EventSummary[]>([]);
  const [chosen, setChosen] = useState<number | undefined>(eventHint);
  useEffect(() => { api.events().then(setEvents).catch(() => undefined); }, []);
  const poll = usePoll(() => api.dashboard(chosen), 10_000, [chosen]);
  const current = chosen ?? poll.data?.event.id;
  return (
    <main className="page dash">
      <header className="dash-head">
        <h1>{t("dashTitle")}</h1>
        <div className="dash-actions">
          {events.length > 1 ? (
            <label className="field inline-field"><span className="visually-hidden">{t("dashOperation")}</span>
              <select value={current ?? ""} onChange={(e) => setChosen(Number(e.target.value))} aria-label={t("dashOperation")}>
                {events.map((e) => <option key={e.id} value={e.id}>{e.name} · {state(e.status)}</option>)}
              </select>
            </label>
          ) : null}
          <a className="btn btn-primary" href="/team#add-person" data-testid="add-staff"
            onClick={(e) => { e.preventDefault(); navigate("/team#add-person"); }}>
            <Icon name="user" /> {t("addStaff")}
          </a>
        </div>
      </header>
      <StaleBanner show={poll.stale} />
      {poll.error instanceof ApiError && poll.error.status === 404 && !poll.data ? <Empty text={t("opsNoOperationBody")} /> : (
        <PageData poll={poll}>{(d) => <Body d={d} />}</PageData>
      )}
    </main>
  );
}
