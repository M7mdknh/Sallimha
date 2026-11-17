import { type FormEvent, useRef, useState } from "react";

import { ApiError, api, newKey, type LiveSnapshot, type Me, type Schemas } from "../api/client";
import { Icon } from "../components/Icon";
import { Empty, Id, LoadFailed, SkeletonRows, StaleBanner, StatusPill } from "../components/States";
import { TicketPanel } from "../components/TicketPanel";
import { navigate } from "../router";
import { useT } from "../strings";
import { usePoll } from "../usePoll";
import { OpsTabs } from "./Ops";
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

type Row = Schemas["LiveRequest"];

/** One car in a list: what a supervisor scans for — ticket, car, how long the customer has waited, who has it. */
function CarRow({ r, current, onOpen }: { r: Row; current?: number; onOpen: (id: number) => void }) {
  const { t, state } = useT();
  const [tone, icon] = TONE[r.state] ?? ["neutral", "clock"];
  const late = r.elapsed_s >= 240;
  return (
    <li>
      <button type="button" className="row row-button car-row" onClick={() => onOpen(r.ticket_id)}
        aria-current={current === r.ticket_id ? "true" : undefined}>
        <span className="row-title"><Id>{r.ticket}</Id> <span className="muted">{r.vehicle}</span></span>
        <span className={`elapsed ${late ? "is-late" : ""}`} title={t("waited")}>
          <Icon name="clock" size={16} /> <Id>{formatElapsed(r.elapsed_s)}</Id>
        </span>
        {r.ticket_state === "READY" ? null : <StatusPill tone={tone} icon={icon} label={state(r.state)} />}
        <span className="row-meta"><Icon name="user" size={16} /> {r.assignee ?? t("unassigned")}</span>
        <span className="row-meta"><Icon name="pin" size={16} /> <Id>{r.location || "—"}</Id> · <Icon name="key" size={16} /> <Id>{r.hook ?? "—"}</Id></span>
      </button>
    </li>
  );
}

function CarList({ id, title, icon, empty, rows, current, onOpen }: { id: string; title: string; icon: string;
  empty: string; rows: Row[]; current?: number; onOpen: (id: number) => void }) {
  return (
    <section className="card car-list" aria-labelledby={`${id}-h`} data-testid={`list-${id}`}>
      <h2 id={`${id}-h`}><Icon name={icon} /> {title} <span className="count-badge"><Id>{rows.length}</Id></span></h2>
      {rows.length === 0 ? <Empty text={empty} /> : <ul className="rows">{rows.map((r) => (
        <CarRow key={r.request_id} r={r} current={current} onOpen={onOpen} />))}</ul>}
    </section>
  );
}

/** Operations → Cars (ADR-0011): problems first, then cars waiting, on the way and ready with their waiting time,
 *  and a search for any car. Ticket actions live in the ticket detail beside the lists (tablet) or over them (phone). */
export function Live({ me, eventId, ticketId }: { me: Me; eventId: number; ticketId?: number }) {
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
  const waiting = snapshot.requests.filter((r) => ["WAITING_FOR_PARKING", "QUEUED", "OFFERED"].includes(r.state));
  const onTheWay = snapshot.requests.filter((r) => r.state === "ACCEPTED" && r.ticket_state !== "READY");
  const ready = snapshot.requests.filter((r) => r.ticket_state === "READY");
  const tally = (status: string) => snapshot.team.filter((m) => m.status === status).length;
  const degraded = snapshot.health.whatsapp === "degraded";

  return (
    <main className={`page live ${ticketId ? "has-panel" : ""}`}>
      <div className="live-head">
        <h1>{snapshot.event.name}</h1>
        <p className="freshness">
          <span>{snapshot.event.venue}</span>
          <span>{t("lastUpdate")} <Id>{lastSuccess ? time(lastSuccess) : "—"}</Id></span>
          {snapshot.health.worker !== "ok" ? <span className="is-bad">{t("worker")}: {t(`health_${snapshot.health.worker}` as never)}</span> : null}
        </p>
      </div>
      <OpsTabs me={me} eventId={eventId} />
      <StaleBanner show={stale} />
      {snapshot.outage || degraded ? (
        <div className="outage-banner" role="status">
          <Icon name="message" />
          <span>{snapshot.outage ? t("customerOutage") : t("customerDegraded")}</span>
          <a href="/outages" onClick={(e) => { e.preventDefault(); navigate("/outages"); }}>{t("navOutages")}</a>
        </div>
      ) : null}
      {problem ? <p className="form-error" role="alert">{problem}</p> : null}

      <div className="live-grid">
        <div className="live-main">
          <section className="card" aria-labelledby="attention-h" data-testid="problems">
            <h2 id="attention-h"><Icon name="alert" /> {t("problems")}
              {snapshot.attention.length ? <span className="count-badge is-alert"><Id>{snapshot.attention.length}</Id></span> : null}</h2>
            {snapshot.attention.length === 0 ? <Empty text={t("problemsEmpty")} /> : null}
            <ul className="rows">
              {snapshot.attention.map((a) => (
                <li key={a.id} className={`row attention-${a.severity}`}>
                  <StatusPill tone={a.severity === "critical" ? "danger" : "warning"} icon={a.severity === "critical" ? "alert" : "clock"} label={alert(a.kind)} />
                  {a.ticket ? <span className="row-meta">{t("ticket")} <Id>{a.ticket}</Id></span> : null}
                  <span className="row-meta"><Id>{time(a.created_at)}</Id></span>
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

          <TicketFinder eventId={eventId} current={ticketId} onOpen={openTicket} />

          <div className="car-lists">
            <CarList id="waiting" title={t("waitingCars")} icon="clock" empty={t("noneWaiting")} rows={waiting}
              current={ticketId} onOpen={openTicket} />
            <CarList id="retrieving" title={t("retrievingCars")} icon="car" empty={t("noneRetrieving")} rows={onTheWay}
              current={ticketId} onOpen={openTicket} />
            <CarList id="ready" title={t("readyCars")} icon="check" empty={t("noneReady")} rows={ready}
              current={ticketId} onOpen={openTicket} />
          </div>

          <ul className="counts" aria-label={t("opsCars")}>
            {["RECEIVED", "PARKED", "RETRIEVING", "READY", "DELIVERED"].map((s) => (
              <li key={s} className="count" data-testid={`count-${s}`}>
                <span className="count-n">{snapshot.counts[s] ?? 0}</span>
                <span className="count-label">{state(s)}</span>
              </li>
            ))}
          </ul>

          <a className="row-link team-line" href="/team" onClick={(e) => { e.preventDefault(); navigate("/team"); }}>
            <Icon name="users" /> <span className="row-title">{t("navTeam")}</span>
            <StatusPill tone="success" icon="check" label={`${state("available")} ${tally("available")}`} />
            <StatusPill tone="info" icon="car" label={`${state("busy")} ${tally("busy")}`} />
            <StatusPill tone="neutral" icon="clock" label={`${state("unavailable")} ${tally("unavailable")}`} />
          </a>
          <OpeningCheck eventId={eventId} />
        </div>

        <aside className="live-side">
          {ticketId ? (
            <TicketPanel ticketId={ticketId} eventId={eventId} team={snapshot.team} disabled={disabled}
              onClose={() => navigate(`/events/${eventId}`)} onChanged={refresh} />
          ) : <p className="select-hint muted">{t("selectCar")}</p>}
        </aside>
      </div>
    </main>
  );
}
