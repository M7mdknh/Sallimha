import { useEffect } from "react";

import { ApiError, api, type Dashboard as Board, type Me } from "../api/client";
import { Icon } from "../components/Icon";
import { Empty, Id, PageData, StaleBanner, StatusPill } from "../components/States";
import { navigate } from "../router";
import { useT } from "../strings";
import { usePoll } from "../usePoll";
import { rememberEvent } from "../session";
import { venueClock } from "../venueTime";
import { formatElapsed } from "./Live";

function Duration({ seconds }: { seconds: number | null | undefined }) {
  return <Id>{seconds === null || seconds === undefined ? "—" : formatElapsed(seconds)}</Id>;
}

const STATUS: Record<string, [string, string]> = {
  available: ["success", "check"], busy: ["info", "car"], unavailable: ["neutral", "clock"],
};

function Body({ d }: { d: Board }) {
  const { t, state, lang } = useT();
  useEffect(() => rememberEvent(d.event.id), [d.event.id]);
  const r2r = d.request_to_ready;
  return (
    <>
      <p className="freshness"><span><strong>{d.event.name}</strong> · {d.event.venue}</span>
        <span>{t("lastUpdate")} <Id>{venueClock(d.generated_at, lang, d.event.time_zone)}</Id></span></p>

      <ul className="metrics" aria-label={t("dashTitle")}>
        <li className="metric" data-testid="metric-parked"><span className="metric-n"><Id>{d.cars.parked}</Id></span>
          <span className="metric-label">{t("dashParked")}</span>
          <span className="muted">{t("dashReceiving")} <Id>{d.cars.receiving}</Id></span></li>
        <li className={`metric ${d.waiting_requests ? "is-attention" : ""}`} data-testid="metric-waiting">
          <span className="metric-n"><Id>{d.waiting_requests}</Id></span>
          <span className="metric-label">{t("dashWaiting")}</span>
          <span className="muted">{t("dashOnTheWay")} <Id>{d.cars.retrieving + d.cars.ready}</Id></span></li>
        <li className="metric" data-testid="metric-delivered"><span className="metric-n"><Id>{d.cars.delivered}</Id></span>
          <span className="metric-label">{t("dashDelivered")}</span></li>
        <li className={`metric ${d.delayed_requests ? "is-late" : ""}`} data-testid="metric-delayed">
          <span className="metric-n"><Id>{d.delayed_requests}</Id></span>
          <span className="metric-label">{t("dashDelayed")}</span>
          <span className="muted">{t("dashDelayedDef")} <Duration seconds={d.delay_threshold_s} /> · {t("dashOldest")} <Duration seconds={d.oldest_wait_s} /></span></li>
      </ul>

      <div className="dash-grid">
        <section className="card" aria-labelledby="r2r-h" data-testid="request-to-ready">
          <h2 id="r2r-h"><Icon name="clock" /> {t("dashRequestToReady")}</h2>
          <p className="muted">{t("dashRequestToReadyDef")}</p>
          {r2r.count === 0 ? <p className="empty">{t("dashNoData")}</p> : (
            <dl className="facts">
              <div><dt>{t("dashMedian")}</dt><dd className="big-number"><Duration seconds={r2r.median_s} /></dd></div>
              <div><dt>{t("dashP95")}</dt><dd className="big-number"><Duration seconds={r2r.p95_s} /></dd></div>
              <div><dt>{t("dashOf")}</dt><dd><Id>{r2r.count}</Id> {t("dashRequests")}</dd></div>
            </dl>
          )}
        </section>

        <section className="card" aria-labelledby="prob-h" data-testid="dash-problems">
          <h2 id="prob-h"><Icon name="alert" /> {t("dashProblems")}</h2>
          <dl className="facts">
            <div><dt>{t("dashAlerts")}</dt><dd><Id>{d.problems.alerts}</Id>
              {d.problems.critical ? <> · <span className="is-bad"><Id>{d.problems.critical}</Id> {t("dashCritical")}</span></> : null}</dd></div>
            <div><dt>{t("dashIncidents")}</dt><dd><Id>{d.problems.incidents}</Id></dd></div>
            <div><dt>{t("dashHolds")}</dt><dd><Id>{d.problems.holds}</Id></dd></div>
          </dl>
          <button type="button" className="btn btn-secondary" onClick={() => navigate(`/events/${d.event.id}`)}>
            {t("dashOpenOps")}
          </button>
        </section>
      </div>

      <section className="card" aria-labelledby="dteam-h" data-testid="dash-team">
        <h2 id="dteam-h"><Icon name="users" /> {t("dashTeam")}</h2>
        <div className="pills">
          <StatusPill tone="success" icon="check" label={`${state("available")} ${d.team.available}`} />
          <StatusPill tone="info" icon="car" label={`${state("busy")} ${d.team.busy}`} />
          <StatusPill tone="neutral" icon="clock" label={`${state("unavailable")} ${d.team.unavailable}`} />
          <StatusPill tone="neutral" icon="user" label={`${t("dashNotStarted")} ${d.team.not_started}`} />
        </div>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th scope="col">{t("dashColName")}</th><th scope="col">{t("dashColStatus")}</th>
              <th scope="col">{t("dashColTask")}</th><th scope="col">{t("dashParkedBy")}</th><th scope="col">{t("dashDeliveredBy")}</th></tr></thead>
            <tbody>
              {d.team.members.map((m) => {
                const [tone, icon] = STATUS[m.status];
                return (
                  <tr key={m.staff_id}>
                    <th scope="row">{m.name}</th>
                    <td><StatusPill tone={tone} icon={icon} label={state(m.status)} /></td>
                    <td><Id>{m.task ?? "—"}</Id></td>
                    <td><Id>{m.parked}</Id></td>
                    <td><Id>{m.delivered}</Id></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <a className="row-link" href={`/events/${d.event.id}/report`}
        onClick={(e) => { e.preventDefault(); navigate(`/events/${d.event.id}/report`); }}>
        <Icon name="chevron" /> <span className="row-title">{t("dashFullReport")}</span>
      </a>
    </>
  );
}

/** Admin dashboard (ADR-0011): counts, one defined duration, problems and who is doing what. No scores. */
export function Dashboard({ me: _me, eventHint }: { me: Me; eventHint?: number }) {
  const { t } = useT();
  const poll = usePoll(() => api.dashboard(eventHint), 10_000, [eventHint]);
  return (
    <main className="page">
      <h1>{t("dashTitle")}</h1>
      <StaleBanner show={poll.stale} />
      {poll.error instanceof ApiError && poll.error.status === 404 && !poll.data ? <Empty text={t("opsNoOperationBody")} /> : (
        <PageData poll={poll}>{(d) => <Body d={d} />}</PageData>
      )}
    </main>
  );
}
