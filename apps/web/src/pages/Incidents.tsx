import { type FormEvent, useState } from "react";

import { api, atLeast, type Me } from "../api/client";
import { Icon } from "../components/Icon";
import { Empty, Id, PageData, StaleBanner, StatusPill } from "../components/States";
import { navigate } from "../router";
import { useT, type StringKey } from "../strings";
import { useCommand } from "../useCommand";
import { usePoll } from "../usePoll";
import { venueTime } from "../venueTime";

function TextCommand({ label, field, empty, disabled, submit }: { label: StringKey; field: StringKey; empty: string;
  disabled: boolean; submit: (text: string, key: string) => Promise<unknown> }) {
  const { t, error } = useT();
  const [text, setText] = useState("");
  const { run, busy, problem, setProblem } = useCommand();
  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!text.trim()) return setProblem(error(empty));
    if (await run((key) => submit(text.trim(), key))) setText("");
  }
  return (
    <form className="action-form" onSubmit={onSubmit} noValidate>
      <label className="field">
        <span>{t(field)}</span>
        <textarea rows={2} maxLength={2000} value={text} onChange={(e) => setText(e.target.value)} />
      </label>
      {problem ? <p className="form-error" role="alert">{problem}</p> : null}
      <button type="submit" className="btn btn-primary" data-mutation disabled={disabled || busy}>{t(label)}</button>
    </form>
  );
}

function IncidentDetail({ incidentId, eventId, me, disabled, onChanged }: { incidentId: number; eventId: number;
  me: Me; disabled: boolean; onChanged: () => void }) {
  const { t, state, lang } = useT();
  const poll = usePoll(() => api.incident(incidentId), 10_000, [incidentId]);
  const changed = () => { void poll.refresh(); onChanged(); };
  return (
    <section className="card ticket-panel" aria-labelledby="incident-h">
      <div className="panel-head">
        <h2 id="incident-h">{t("incidentsTitle")} <Id>#{incidentId}</Id></h2>
        <button type="button" className="btn btn-quiet" aria-label={t("close")}
          onClick={() => navigate(`/events/${eventId}/incidents`)}>
          <Icon name="x" />
        </button>
      </div>
      <PageData poll={poll}>
        {(i) => (
          <>
            <div className="pills">
              <StatusPill tone={i.status === "RESOLVED" ? "neutral" : "warning"} icon="alert"
                label={t(`cat_${i.category}` as StringKey)} />
              <StatusPill tone={i.status === "RESOLVED" ? "success" : "info"} icon={i.status === "RESOLVED" ? "check" : "clock"}
                label={state(i.status)} />
            </div>
            <p className="prose">{i.description}</p>
            <dl className="facts">
              <div><dt>{t("openedAt")}</dt><dd><Id>{venueTime(i.created_at, lang)}</Id></dd></div>
              <div><dt>{t("ticket")}</dt><dd>{i.ticket && i.ticket_id ? (
                <a href={`/events/${eventId}/tickets/${i.ticket_id}`}
                  onClick={(e) => { e.preventDefault(); navigate(`/events/${eventId}/tickets/${i.ticket_id}`); }}>
                  <Id>{i.ticket}</Id>
                </a>
              ) : "—"}</dd></div>
              {i.resolved_by ? <div><dt>{t("resolvedBy")}</dt><dd>{i.resolved_by}</dd></div> : null}
            </dl>
            {i.resolution ? <p className="prose"><strong>{t("outcome")}:</strong> {i.resolution}</p> : null}
            <h3>{t("incidentNotes")}</h3>
            {i.notes.length === 0 ? <Empty text={t("noneYet")} /> : (
              <ol className="notes">
                {i.notes.map((n, idx) => (
                  <li key={idx}>
                    <span className="row-meta">{n.author} · <Id>{venueTime(n.created_at, lang)}</Id></span>
                    <p>{n.text}</p>
                  </li>
                ))}
              </ol>
            )}
            {i.status !== "RESOLVED" ? (
              <TextCommand label="addNote" field="note" empty="description_required" disabled={disabled}
                submit={(text, key) => api.incidentNote(incidentId, text, key).then(changed)} />
            ) : null}
            {i.status !== "RESOLVED" && atLeast(me, "MANAGER") ? (
              <>
                <p className="muted">{t("resolveHint")}</p>
                <TextCommand label="resolve" field="outcome" empty="outcome_required" disabled={disabled}
                  submit={(text, key) => api.incidentResolve(incidentId, text, key).then(changed)} />
              </>
            ) : null}
          </>
        )}
      </PageData>
    </section>
  );
}

export function Incidents({ eventId, incidentId, me }: { eventId: number; incidentId?: number; me: Me }) {
  const { t, state, lang } = useT();
  const poll = usePoll(() => api.incidents(eventId), 10_000, [eventId]);
  return (
    <main className="page">
      <h1>{t("incidentsTitle")}</h1>
      <StaleBanner show={poll.stale} />
      <div className="live-grid">
        <div className="live-main">
          <section className="card" aria-labelledby="incidents-h">
            <h2 id="incidents-h" className="visually-hidden">{t("incidentsTitle")}</h2>
            <PageData poll={poll}>
              {(rows) => rows.length === 0 ? <Empty text={t("incidentsEmpty")} /> : (
                <ul className="rows">
                  {rows.map((i) => (
                    <li key={i.id}>
                      <button type="button" className="row row-button" aria-current={incidentId === i.id ? "true" : undefined}
                        onClick={() => navigate(`/events/${eventId}/incidents/${i.id}`)}>
                        <span className="row-title">
                          {t(`cat_${i.category}` as StringKey)} {i.ticket ? <Id>{i.ticket}</Id> : null}
                        </span>
                        <StatusPill tone={i.status === "RESOLVED" ? "success" : i.status === "OPEN" ? "warning" : "info"}
                          icon={i.status === "RESOLVED" ? "check" : "clock"} label={state(i.status)} />
                        <span className="row-meta"><Id>{venueTime(i.created_at, lang)}</Id></span>
                        <span className="row-meta clamp">{i.description}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </PageData>
          </section>
        </div>
        <aside className="live-side">
          {incidentId ? (
            <IncidentDetail incidentId={incidentId} eventId={eventId} me={me} disabled={poll.stale}
              onChanged={poll.refresh} />
          ) : null}
        </aside>
      </div>
    </main>
  );
}
