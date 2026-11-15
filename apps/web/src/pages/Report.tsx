import { api, atLeast, type Me } from "../api/client";
import { Icon } from "../components/Icon";
import { Empty, Id, PageData } from "../components/States";
import { useT, type StringKey } from "../strings";
import { usePoll } from "../usePoll";
import { formatElapsed } from "./Live";

const STAGES = ["received_to_parked", "request_to_accept", "accept_to_ready", "ready_to_delivered"] as const;
const OUTCOMES = ["DELIVERED", "PARKED", "RETRIEVING", "READY", "RECEIVED", "CANCELLED", "UNCLAIMED"];
const dur = (s: number | null | undefined) => (s === null || s === undefined ? "—" : formatElapsed(s));

export function Report({ eventId, me }: { eventId: number; me: Me }) {
  const { t, state } = useT();
  const poll = usePoll(() => api.report(eventId), 60_000, [eventId]);
  return (
    <main className="page">
      <h1>{t("reportTitle")}</h1>
      <PageData poll={poll}>
        {(r) => (
          <>
            <ul className="counts" aria-label={t("outcomes")}>
              {OUTCOMES.filter((s) => (r.outcomes[s] ?? 0) > 0 || ["DELIVERED", "PARKED", "CANCELLED"].includes(s)).map((s) => (
                <li key={s} className="count" data-testid={`outcome-${s}`}>
                  <span className="count-n">{r.outcomes[s] ?? 0}</span>
                  <span className="count-label">{state(s)}</span>
                </li>
              ))}
              <li className="count">
                <span className="count-n">{r.unresolved_incidents}</span>
                <span className="count-label">{t("unresolvedIncidents")}</span>
              </li>
            </ul>

            <section className="card" aria-labelledby="stages-h">
              <h2 id="stages-h"><Icon name="clock" /> {t("stages")}</h2>
              <div className="table-wrap">
                <table className="table">
                  <thead><tr><th scope="col">{t("stages")}</th><th scope="col">{t("count")}</th>
                    <th scope="col">{t("median")}</th><th scope="col">{t("p95")}</th></tr></thead>
                  <tbody>
                    {STAGES.map((k) => (
                      <tr key={k}>
                        <th scope="row">{t(`stage_${k}` as StringKey)}</th>
                        <td><Id>{r.stages[k].count}</Id></td>
                        <td><Id>{dur(r.stages[k].median_s)}</Id></td>
                        <td><Id>{dur(r.stages[k].p95_s)}</Id></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="card" aria-labelledby="hours-h">
              <h2 id="hours-h"><Icon name="users" /> {t("hours")}</h2>
              {r.hours.length === 0 ? <Empty text={t("noneYet")} /> : (
                <div className="table-wrap">
                  <table className="table">
                    <thead><tr><th scope="col">{t("name")}</th><th scope="col">{t("hours")}</th>
                      <th scope="col">{t("breaks")}</th></tr></thead>
                    <tbody>
                      {r.hours.map((h, i) => (
                        <tr key={`${h.staff_id}-${i}`}>
                          <th scope="row">{h.name}</th>
                          <td><Id>{dur(h.worked_s)}</Id></td>
                          <td><Id>{dur(h.break_s)}</Id></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {Object.keys(r.ratings).length ? (
                <p className="muted">{t("ratings")}: {Object.entries(r.ratings).map(([k, v]) => `${k}: ${v}`).join(" · ")}</p>
              ) : null}
            </section>

            <section className="card" aria-labelledby="exports-h">
              <h2 id="exports-h">{t("exports")}</h2>
              <p className="muted">{t("exportHint")}</p>
              <div className="row-actions start">
                <a className="btn btn-secondary" href={api.exportUrl(eventId, "tickets")} download>{t("exportTickets")}</a>
                {atLeast(me, "ADMIN") ? (
                  <a className="btn btn-secondary" href={api.exportUrl(eventId, "guest-phones")} download>{t("exportPhones")}</a>
                ) : null}
              </div>
            </section>
          </>
        )}
      </PageData>
    </main>
  );
}
