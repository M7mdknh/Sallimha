import { api, type Me } from "../api/client";
import { Empty, Id, PageData, StaleBanner, StatusPill } from "../components/States";
import { navigate } from "../router";
import { useT, type StringKey } from "../strings";
import { usePoll } from "../usePoll";
import { OpsTabs } from "./Ops";
import { venueTime } from "../venueTime";

/** Cars and keys kept past their event. Each row opens the ticket panel, where approval and release happen. */
export function Carryover({ me, eventId }: { me: Me; eventId?: number }) {
  const { t, lang } = useT();
  const poll = usePoll(api.carryover, 30_000, []);
  return (
    <main className="page">
      <h1>{t("carryoverTitle")}</h1>
      <OpsTabs me={me} eventId={eventId} />
      <StaleBanner show={poll.stale} />
      <section className="card" aria-labelledby="carry-h">
        <h2 id="carry-h" className="visually-hidden">{t("carryoverTitle")}</h2>
        <PageData poll={poll}>
          {(rows) => rows.length === 0 ? <Empty text={t("carryoverEmpty")} /> : (
            <ul className="rows">
              {rows.map((c) => (
                <li key={c.id}>
                  <button type="button" className="row row-button" data-testid={`carry-${c.ticket_id}`}
                    onClick={() => navigate(`/events/${c.event_id}/tickets/${c.ticket_id}`)}>
                    <span className="row-title"><Id>{c.ticket}</Id> <span className="muted">{c.event}</span></span>
                    <StatusPill tone={c.status === "PROPOSED" ? "warning" : "info"} icon="key"
                      label={t(`carry_${c.status}` as StringKey)} />
                    <span className="row-meta">{t("location")}: <Id>{c.location || "—"}</Id> · {t("key")}: <Id>{c.hook ?? "—"}</Id></span>
                    <span className="row-meta">{t("custodian")}: {c.custodian}</span>
                    <span className="row-meta">{t("proposedAt")}: <Id>{venueTime(c.proposed_at, lang)}</Id></span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </PageData>
      </section>
    </main>
  );
}
