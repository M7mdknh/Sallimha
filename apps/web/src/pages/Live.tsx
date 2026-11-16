import { type FormEvent, useRef, useState } from "react";

import { ApiError, api, newKey, type LiveSnapshot, type Schemas } from "../api/client";
import { Icon } from "../components/Icon";
import { Empty, Id, LoadFailed, SkeletonRows, StaleBanner, StatusPill } from "../components/States";
import { TicketPanel } from "../components/TicketPanel";
import { navigate } from "../router";
import { useT } from "../strings";
import { usePoll } from "../usePoll";
import { rememberZone, venueClock } from "../venueTime";

const CHECK_FIELDS = [["zones", "zones"], ["key_hooks", "keyHooks"], ["assigned_not_started", "assignedNotStarted"],
  ["carryover_unresolved", "carryoverUnresolved"], ["dead_letters", "deadLetters"]] as const;

/** Find any ticket (parked cars have no open request, so they are not in the lists below). */
function TicketFinder({ eventId, current, onOpen }: { eventId: number; current?: number; onOpen: (id: number) => void }) {
  const { t, state, error } = useT();
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<Schemas["TicketSearchRow"][] | null>(null);
  const [problem, setProblem] = useState("");
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!q.trim()) return;
    setProblem("");
    try {
      setRows(await api.searchTickets(eventId, q.trim()));
    } catch (err) {
      setProblem(error(err instanceof ApiError ? err.code : "generic"));
    }
  }
  return (
    <section className="card" aria-labelledby="find-h">
      <h2 id="find-h"><Icon name="key" /> {t("findTicket")}</h2>
      <form className="inline-form" role="search" onSubmit={submit}>
        <label className="field grow">
          <span>{t("findTicketHint")}</span>
          <input type="search" dir="ltr" value={q} onChange={(e) => setQ(e.target.value)} autoComplete="off" />
        </label>
        <button type="submit" className="btn btn-secondary">{t("find")}</button>
      </form>
      {problem ? <p className="form-error" role="alert">{problem}</p> : null}
      {rows && rows.length === 0 ? <Empty text={t("findNone")} /> : null}
      {rows && rows.length ? (
        <ul className="rows">
          {rows.map((r) => (
            <li key={r.id}>
              <button type="button" className="row row-button" aria-current={current === r.id ? "true" : undefined}
                onClick={() => onOpen(r.id)}>
                <span className="row-title"><Id>{r.ticket}</Id> <span className="muted">{r.vehicle}</span></span>
                <StatusPill tone="info" icon="car" label={state(r.state)} />
                <span className="row-meta"><Icon name="pin" size={16} /> <Id>{r.location || "—"}</Id> · <Icon name="key" size={16} /> <Id>{r.hook ?? "—"}</Id></span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

/** Puts an organisation valet who is not yet on this event on tonight's team (starts their shift). */
function AddToTeam({ people, disabled, onStart }: { people: Schemas["StaffBrief"][]; disabled: boolean;
  onStart: (staffId: number) => void }) {
  const { t } = useT();
  const [choice, setChoice] = useState("");
  return (
    <form className="inline-form" onSubmit={(e) => { e.preventDefault(); if (choice) { onStart(Number(choice)); setChoice(""); } }}>
      <label className="field grow">
        <span>{t("addToTeam")}</span>
        <select value={choice} onChange={(e) => setChoice(e.target.value)}>
          <option value="">—</option>
          {people.map((p) => <option key={p.staff_id} value={p.staff_id}>{p.name}</option>)}
        </select>
      </label>
      <button type="submit" className="btn btn-secondary" data-mutation disabled={disabled || !choice}>{t("startShift")}</button>
    </form>
  );
}

/** Readiness before opening (worker, WhatsApp, zones, hooks, team, carryover, dead letters). */
function OpeningCheck({ eventId }: { eventId: number }) {
  const { t } = useT();
  const { data } = usePoll(() => api.openingCheck(eventId), 30_000, [eventId]);
  if (!data) return null;
  return (
    <details className="card disclosure" open={!data.ok} data-testid="opening-check">
      <summary>
        <span>{t("openingCheck")}</span>
        <StatusPill tone={data.ok ? "success" : "warning"} icon={data.ok ? "check" : "alert"}
          label={data.ok ? t("openingOk") : t("openingNotOk")} />
      </summary>
      {data.causes.length ? (
        <ul className="causes">{data.causes.map((c) => <li key={c}>{t(`cause_${c}` as never) ?? c}</li>)}</ul>
      ) : null}
      <dl className="facts">
        {CHECK_FIELDS.map(([field, label]) => (
          <div key={field}><dt>{t(label)}</dt><dd><Id>{data[field]}</Id></dd></div>
        ))}
      </dl>
    </details>
  );
}

const TONE: Record<string, [string, string]> = {
  WAITING_FOR_PARKING: ["info", "clock"], QUEUED: ["warning", "clock"], OFFERED: ["warning", "user"],
  ACCEPTED: ["info", "car"], available: ["success", "check"], busy: ["info", "car"], unavailable: ["neutral", "x"],
};

/** Elapsed wait as m:ss (or h:mm:ss), rendered LTR with tabular numerals. */
export function formatElapsed(seconds: number) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = String(seconds % 60).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`;
}

function useMutation() {
  const { error } = useT();
  const [problem, setProblem] = useState("");
  const pending = useRef(new Map<string, string>());
  async function run(id: string, fn: (key: string) => Promise<unknown>, after: () => void) {
    const key = pending.current.get(id) ?? newKey();
    pending.current.set(id, key); // reused if the same action is retried after a lost connection
    setProblem("");
    try {
      await fn(key);
      pending.current.delete(id);
      after();
    } catch (err) {
      if (err instanceof ApiError && err.code === "idempotency_mismatch") pending.current.delete(id);
      setProblem(error(err instanceof ApiError ? err.code : "generic"));
    }
  }
  return { run, problem };
}

export function Live({ eventId, ticketId }: { eventId: number; ticketId?: number }) {
  const { t, state, alert, lang } = useT();
  const { data, error, stale, lastSuccess, refresh } = usePoll(() => api.live(eventId), 3_000, [eventId]);
  const { run, problem } = useMutation();
  const openTicket = (id: number) => navigate(`/events/${eventId}/tickets/${id}`);
  const disabled = stale || data === null;

  if (data === null) {
    return (
      <main className="page">
        {error ? <LoadFailed onRetry={refresh} /> : <SkeletonRows rows={6} />}
      </main>
    );
  }
  const snapshot: LiveSnapshot = data;
  rememberZone(snapshot.event.time_zone);
  const time = (iso: string | number) => venueClock(iso, lang, snapshot.event.time_zone);

  return (
    <main className={`page live ${ticketId ? "has-panel" : ""}`}>
      <div className="live-head">
        <h1>{snapshot.event.name}</h1>
        <p className="freshness">
          <span>{t("lastUpdate")} {lastSuccess ? time(lastSuccess) : "—"}</span>
          <span>{t("worker")}: {t(`health_${snapshot.health.worker}` as never)}</span>
          <span>{t("whatsapp")}: {t(`health_${snapshot.health.whatsapp}` as never)}</span>
        </p>
      </div>
      <StaleBanner show={stale} />
      {snapshot.outage ? (
        <div className="outage-banner" role="status">
          <Icon name="alert" />
          <span>{t("outageBanner")} — {snapshot.outage.declared_by}, {time(snapshot.outage.since)}.</span>
          <a href="/outages" onClick={(e) => { e.preventDefault(); navigate("/outages"); }}>{t("navOutages")}</a>
        </div>
      ) : null}
      {problem ? <p className="form-error" role="alert">{problem}</p> : null}

      <div className="live-grid">
        <div className="live-main">
          <section className="card" aria-labelledby="attention-h">
            <h2 id="attention-h">
              <Icon name="alert" /> {t("attention")}
            </h2>
            {snapshot.attention.length === 0 ? <Empty text={t("attentionEmpty")} /> : null}
            <ul className="rows">
              {snapshot.attention.map((a) => (
                <li key={a.id} className={`row attention-${a.severity}`}>
                  <StatusPill tone={a.severity === "critical" ? "danger" : "warning"} icon={a.severity === "critical" ? "alert" : "clock"} label={alert(a.kind)} />
                  {a.ticket ? <span className="row-meta">{t("ticket")} <Id>{a.ticket}</Id></span> : null}
                  <span className="row-meta">{time(a.created_at)}</span>
                  <span className="row-actions">
                    {a.ticket_id ? (
                      <button type="button" className="btn btn-secondary" onClick={() => openTicket(a.ticket_id!)}>{t("open")}</button>
                    ) : null}
                    <button type="button" className="btn btn-quiet" data-mutation disabled={disabled}
                      onClick={() => run(`ack-${a.id}`, (k) => api.ackAlert(a.id, k), refresh)}>
                      <Icon name="check" /> {t("acknowledge")}
                    </button>
                  </span>
                </li>
              ))}
            </ul>
          </section>

          <ul className="counts" aria-label={t("live")}>
            {["RECEIVED", "PARKED", "RETRIEVING", "READY", "DELIVERED"].map((s) => (
              <li key={s} className="count" data-testid={`count-${s}`}>
                <span className="count-n">{snapshot.counts[s] ?? 0}</span>
                <span className="count-label">{state(s)}</span>
              </li>
            ))}
          </ul>

          <TicketFinder eventId={eventId} current={ticketId} onOpen={openTicket} />

          <section className="card" aria-labelledby="requests-h" role="region">
            <h2 id="requests-h"><Icon name="car" /> {t("requests")}</h2>
            {snapshot.requests.length === 0 ? <Empty text={t("requestsEmpty")} /> : null}
            <ul className="rows">
              {snapshot.requests.map((r) => {
                const [tone, icon] = TONE[r.state] ?? ["neutral", "clock"];
                return (
                  <li key={r.request_id}>
                    <button type="button" className="row row-button" onClick={() => openTicket(r.ticket_id)}
                      aria-current={ticketId === r.ticket_id ? "true" : undefined}>
                      <span className="row-title"><Id>{r.ticket}</Id> <span className="muted">{r.vehicle}</span></span>
                      <StatusPill tone={tone} icon={icon} label={state(r.state)} />
                      <span className="row-meta"><Icon name="clock" size={16} /> <Id>{formatElapsed(r.elapsed_s)}</Id></span>
                      <span className="row-meta"><Icon name="user" size={16} /> {r.assignee ?? t("unassigned")}</span>
                      <span className="row-meta"><Icon name="pin" size={16} /> <Id>{r.location || "—"}</Id> · <Icon name="key" size={16} /> <Id>{r.hook ?? "—"}</Id></span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>
        </div>

        <aside className="live-side">
          {ticketId ? (
            <TicketPanel ticketId={ticketId} eventId={eventId} team={snapshot.team} disabled={disabled}
              onClose={() => navigate(`/events/${eventId}`)} onChanged={refresh} />
          ) : null}
          <OpeningCheck eventId={eventId} />
          <section className="card" aria-labelledby="team-h" role="region">
            <h2 id="team-h"><Icon name="users" /> {t("team")}</h2>
            {snapshot.addable.length ? (
              <AddToTeam people={snapshot.addable} disabled={disabled}
                onStart={(id) => run(`start-${id}`, (k) => api.startShift(eventId, id, k), refresh)} />
            ) : null}
            {snapshot.team.length === 0 ? <Empty text={t("teamEmpty")} /> : null}
            <ul className="rows">
              {snapshot.team.map((m) => {
                const [tone, icon] = TONE[m.status];
                return (
                  <li key={m.shift_id} className="row">
                    <span className="row-title">{m.name}</span>
                    <StatusPill tone={tone} icon={icon} label={state(m.status)} />
                    {m.task ? <span className="row-meta">{state(m.task.type)} <Id>{m.task.ticket}</Id></span> : null}
                    {!m.task ? (
                      <span className="row-actions">
                        <button type="button" className="btn btn-quiet" data-mutation disabled={disabled}
                          onClick={() => run(`end-${m.shift_id}`, (k) => api.endShift(m.shift_id, k), refresh)}>
                          {t("endShift")}
                        </button>
                      </span>
                    ) : null}
                  </li>
                );
              })}
              {snapshot.not_started.map((p) => (
                <li key={`ns-${p.staff_id}`} className="row">
                  <span className="row-title">{p.name}</span>
                  <StatusPill tone="neutral" icon="clock" label={t("notStarted")} />
                  <span className="row-actions">
                    <button type="button" className="btn btn-secondary" data-mutation disabled={disabled}
                      onClick={() => run(`start-${p.staff_id}`, (k) => api.startShift(eventId, p.staff_id, k), refresh)}>
                      {t("startShift")}
                    </button>
                  </span>
                </li>
              ))}
            </ul>
          </section>
        </aside>
      </div>
    </main>
  );
}
