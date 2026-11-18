import { type FormEvent, useState } from "react";

import { api, type Me } from "../api/client";
import { Icon } from "../components/Icon";
import { Empty, PageData, StaleBanner, StatusPill } from "../components/States";
import { navigate } from "../router";
import { useT } from "../strings";
import { useCommand } from "../useCommand";
import { usePoll } from "../usePoll";
import { DEFAULT_ZONE, venueTime } from "../venueTime";
import { SettingsTabs } from "./SettingsTabs";

function NewEvent({ disabled, onDone }: { disabled: boolean; onDone: () => void }) {
  const { t } = useT();
  const venues = usePoll(api.venues, 60_000, []);
  const [form, setForm] = useState({ venue_id: "", name: "", starts_at: "" });
  const zone = venues.data?.find((v) => String(v.id) === form.venue_id)?.time_zone ?? DEFAULT_ZONE;
  const { run, busy, problem, setProblem } = useCommand();
  const set = (k: keyof typeof form, v: string) => setForm((f) => ({ ...f, [k]: v }));

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!form.venue_id || !form.name.trim() || !form.starts_at) return setProblem(t("error_invalid_input"));
    // The wall-clock time is sent as typed; the server reads it in the venue's zone (never the browser's).
    const body = { venue_id: Number(form.venue_id), name: form.name.trim(), starts_at_local: form.starts_at };
    await run((key) => api.createEvent(body, key), () => { setForm({ venue_id: "", name: "", starts_at: "" }); onDone(); });
  }
  return (
    <details className="card disclosure">
      <summary><Icon name="pin" /> {t("newEvent")}</summary>
      <PageData poll={venues} rows={1}>
        {(rows) => (
          <form className="form-grid" onSubmit={submit} noValidate>
            <label className="field"><span>{t("venue")}</span>
              <select value={form.venue_id} onChange={(e) => set("venue_id", e.target.value)}>
                <option value="">—</option>
                {rows.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
              </select></label>
            <label className="field"><span>{t("name")}</span>
              <input value={form.name} maxLength={160} onChange={(e) => set("name", e.target.value)} /></label>
            <label className="field"><span>{t("startsAt")} ({zone})</span>
              <input type="datetime-local" dir="ltr" value={form.starts_at} onChange={(e) => set("starts_at", e.target.value)} /></label>
            {problem ? <p className="form-error span-all" role="alert">{problem}</p> : null}
            <div className="span-all">
              <button type="submit" className="btn btn-primary" data-mutation disabled={disabled || busy}>{t("create")}</button>
            </div>
          </form>
        )}
      </PageData>
    </details>
  );
}

/** Where the parking map opens for each venue (ADR-0013): shown as "venue centre — not the car", never saved as a car's
 *  position. Decimal degrees, e.g. 24.7646 and 46.6402. */
function VenueCentres({ disabled }: { disabled: boolean }) {
  const { t } = useT();
  const venues = usePoll(api.venues, 60_000, []);
  const [form, setForm] = useState<Record<number, { lat: string; lng: string }>>({});
  const { run, busy, problem, done } = useCommand();
  return (
    <details className="card disclosure" data-testid="venue-centres">
      <summary><Icon name="pin" /> {t("venueCentreTitle")}</summary>
      <p className="muted">{t("venueCentreHint")}</p>
      <PageData poll={venues} rows={1}>
        {(list) => (
          <ul className="rows">
            {list.map((v) => {
              const value = form[v.id] ?? { lat: v.centre ? String(v.centre.lat) : "", lng: v.centre ? String(v.centre.lng) : "" };
              const set = (patch: Partial<typeof value>) => setForm((f) => ({ ...f, [v.id]: { ...value, ...patch } }));
              return (
                <li key={v.id} className="row">
                  <form className="inline-form" onSubmit={(e) => {
                    e.preventDefault();
                    void run((key) => api.venueCentre(v.id, { lat: Number(value.lat), lng: Number(value.lng) }, key),
                      () => void venues.refresh());
                  }}>
                    <span className="row-title">{v.name}</span>
                    <label className="field"><span>{t("latitude")}</span>
                      <input dir="ltr" inputMode="decimal" value={value.lat} onChange={(e) => set({ lat: e.target.value })} /></label>
                    <label className="field"><span>{t("longitude")}</span>
                      <input dir="ltr" inputMode="decimal" value={value.lng} onChange={(e) => set({ lng: e.target.value })} /></label>
                    <button type="submit" className="btn btn-secondary" data-mutation disabled={disabled || busy}>{t("save")}</button>
                  </form>
                </li>
              );
            })}
          </ul>
        )}
      </PageData>
      {problem ? <p className="form-error" role="alert">{problem}</p> : null}
      {done && !problem ? <p className="muted" role="status">{t("saved")}</p> : null}
    </details>
  );
}

function CloseEvent({ eventId, disabled, onDone }: { eventId: number; disabled: boolean; onDone: () => void }) {
  const { t } = useT();
  const [confirming, setConfirming] = useState(false);
  const { run, busy, problem } = useCommand();
  return (
    <>
      {confirming ? (
        <span className="confirm-inline" role="group" aria-label={t("closeEvent")}>
          <span className="muted">{t("closeEventHint")}</span>
          <button type="button" className="btn btn-danger" data-mutation disabled={disabled || busy}
            onClick={() => run((key) => api.closeEvent(eventId, key), () => { setConfirming(false); onDone(); })}>
            {t("confirm")}
          </button>
          <button type="button" className="btn btn-quiet" onClick={() => setConfirming(false)}>{t("cancel")}</button>
        </span>
      ) : (
        <button type="button" className="btn btn-quiet" onClick={() => setConfirming(true)}>{t("closeEvent")}</button>
      )}
      {problem ? <p className="form-error span-all" role="alert">{problem}</p> : null}
    </>
  );
}

export function Manage({ me }: { me: Me }) {
  const { t, state, lang } = useT();
  const poll = usePoll(api.events, 30_000, []);
  const go = (href: string) => (e: React.MouseEvent) => { e.preventDefault(); navigate(href); };
  return (
    <main className="page">
      <h1>{t("eventsManage")}</h1>
      <SettingsTabs me={me} />
      <StaleBanner show={poll.stale} />
      <PageData poll={poll}>
        {(rows) => (
          <>
            <NewEvent disabled={poll.stale} onDone={poll.refresh} />
            <VenueCentres disabled={poll.stale} />
            <section className="card" aria-labelledby="events-h">
              <h2 id="events-h" className="visually-hidden">{t("events")}</h2>
              {rows.length === 0 ? <Empty text={t("noEvents")} /> : null}
              <ul className="rows">
                {rows.map((e) => (
                  <li key={e.id} className="row" data-testid={`event-${e.id}`}>
                    <span className="row-title">{e.name}</span>
                    <span className="row-meta">{e.venue}</span>
                    <span className="row-meta">{venueTime(e.starts_at, lang, e.time_zone)}</span>
                    <StatusPill tone={e.status === "OPEN" ? "success" : "neutral"} icon={e.status === "OPEN" ? "check" : "clock"}
                      label={state(e.status)} />
                    <span className="row-actions">
                      {e.status === "OPEN" ? (
                        <a className="btn btn-secondary" href={`/events/${e.id}`} onClick={go(`/events/${e.id}`)}>{t("live")}</a>
                      ) : null}
                      <a className="btn btn-secondary" href={`/events/${e.id}/report`} onClick={go(`/events/${e.id}/report`)}>
                        {t("report")}
                      </a>
                      {e.status === "OPEN" ? <CloseEvent eventId={e.id} disabled={poll.stale} onDone={poll.refresh} /> : null}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          </>
        )}
      </PageData>
    </main>
  );
}
