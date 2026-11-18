import { type FormEvent, useRef, useState } from "react";

import { ApiError, api, newKey, type LiveSnapshot, type Me, type Schemas } from "../api/client";
import { Icon } from "../components/Icon";
import { Id, LoadFailed, SkeletonRows, StaleBanner, StatusPill } from "../components/States";
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
    <div className="ops-search">
      <form className="inline-form" role="search" onSubmit={submit}>
        <label className="field grow">
          <span className="visually-hidden">{t("findTicketHint")}</span>
          <input type="search" dir="auto" value={q} onChange={(e) => setQ(e.target.value)} autoComplete="off"
            aria-label={t("findTicketHint")} placeholder={t("findShort")} />
        </label>
        <button type="submit" className="btn btn-secondary"><Icon name="key" /> {t("find")}</button>
      </form>
      {problem ? <p className="form-error" role="alert">{problem}</p> : null}
      {rows && rows.length === 0 ? <p className="muted">{t("findNone")}</p> : null}
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
    </div>
  );
}

/** Readiness before opening (worker, WhatsApp, zones, hooks, team, carryover, dead letters). */
function OpeningCheck({ eventId }: { eventId: number }) {
  const { t } = useT();
  const { data } = usePoll(() => api.openingCheck(eventId), 30_000, [eventId]);
  if (!data || data.ok) return null; // all clear: nothing technical on the operational view
  return (
    <details className="notice notice-warning opening-line" data-testid="opening-check">
      <summary><Icon name="alert" /> {t("openingNotOk")}: {data.causes.map((c) => t(`cause_${c}` as never) ?? c).join(" · ")}</summary>
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
type Stage = "waiting" | "retrieving" | "ready";
const stageOf = (r: Row): Stage => r.ticket_state === "READY" ? "ready"
  : r.state === "ACCEPTED" ? "retrieving" : "waiting";

/** One car in the queue, read at a glance: how long the customer has waited (with a word when late, not colour
 *  alone), the ticket and plate, the stage and who has it, and where the car and key are. */
function QueueRow({ r, warn, critical, current, onOpen }: { r: Row; warn: number; critical: number; current?: number;
  onOpen: (id: number) => void }) {
  const { t, state } = useT();
  const stage = stageOf(r);
  const late = r.elapsed_s >= critical ? "critical" : r.elapsed_s >= warn ? "late" : "";
  const [tone, icon] = stage === "ready" ? ["success", "check"] : TONE[r.state] ?? ["neutral", "clock"];
  return (
    <li>
      <button type="button" className={`queue-row ${late ? `is-${late}` : ""}`} onClick={() => onOpen(r.ticket_id)}
        aria-current={current === r.ticket_id ? "true" : undefined} data-stage={stage}>
        <span className="q-wait" title={t("waited")}>
          <Id>{formatElapsed(r.elapsed_s)}</Id>
          {late ? <span className="q-late">{t(late === "critical" ? "waitCritical" : "waitLate")}</span> : null}
        </span>
        <span className="q-car">
          <span className="q-id"><Id>{r.ticket}</Id> {r.plate ? <bdi className="q-plate" dir="auto">{r.plate}</bdi> : null}</span>
          <span className="q-desc">{r.description || (r.plate ? "" : r.vehicle)}</span>
        </span>
        <span className="q-who">
          <StatusPill tone={tone} icon={icon} label={stage === "ready" ? state("READY") : state(r.state)} />
          <span className="q-valet"><Icon name="user" size={16} /> {r.assignee ?? t("unassigned")}</span>
          <span className="q-where"><Icon name="pin" size={14} /> <Id>{r.location || "—"}</Id> · <Icon name="key" size={14} /> <Id>{r.hook ?? "—"}</Id></span>
        </span>
      </button>
    </li>
  );
}

function Queue({ rows, warn, critical, current, onOpen }: { rows: Row[]; warn: number; critical: number;
  current?: number; onOpen: (id: number) => void }) {
  const { t } = useT();
  const [filter, setFilter] = useState<Stage | "all">("all");
  const sorted = [...rows].sort((a, b) => b.elapsed_s - a.elapsed_s); // the longest wait first
  const count = (s: Stage) => rows.filter((r) => stageOf(r) === s).length;
  const shown = filter === "all" ? sorted : sorted.filter((r) => stageOf(r) === filter);
  const FILTERS: [Stage | "all", string][] = [["all", t("queueAll")], ["waiting", t("queueWaiting")],
    ["retrieving", t("queueOnTheWay")], ["ready", t("queueReady")]];
  return (
    <section className="queue" aria-labelledby="queue-h" data-testid="queue">
      <div className="queue-head">
        <h2 id="queue-h">{t("queueTitle")} <span className="count-badge"><Id>{rows.length}</Id></span></h2>
        <div className="filters" role="group" aria-label={t("queueFilter")}>
          {FILTERS.map(([key, label]) => (
            <button key={key} type="button" className="filter" aria-pressed={filter === key}
              data-testid={key === "all" ? "filter-all" : `list-${key}`} onClick={() => setFilter(key)}>
              {label} <Id>{key === "all" ? rows.length : count(key)}</Id>
            </button>
          ))}
        </div>
      </div>
      {shown.length === 0 ? <p className="quiet-ok">{rows.length ? t("queueNoneHere") : t("queueEmpty")}</p> : (
        <ol className="queue-rows">{shown.map((r) => (
          <QueueRow key={r.request_id} r={r} warn={warn} critical={critical} current={current} onOpen={onOpen} />))}</ol>
      )}
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
  const tally = (status: string) => snapshot.team.filter((m) => m.status === status).length;
  const degraded = snapshot.health.whatsapp === "degraded";

  return (
    <main className={`page live ${ticketId ? "has-panel" : ""}`}>
      <header className="live-head">
        <div>
          <h1>{snapshot.event.name}</h1>
          <p className="freshness">
            <span>{snapshot.event.venue}</span>
            <span>{t("lastUpdate")} <Id>{lastSuccess ? time(lastSuccess) : "—"}</Id></span>
            {snapshot.health.worker !== "ok" ? <span className="is-bad">{t("worker")}: {t(`health_${snapshot.health.worker}` as never)}</span> : null}
          </p>
        </div>
        <a className="team-glance" href="/team" data-testid="team-glance"
          onClick={(e) => { e.preventDefault(); navigate("/team"); }} aria-label={t("navTeam")}>
          <StatusPill tone="success" icon="check" label={`${state("available")} ${tally("available")}`} />
          <StatusPill tone="info" icon="car" label={`${state("busy")} ${tally("busy")}`} />
          <StatusPill tone="neutral" icon="clock" label={`${state("unavailable")} ${tally("unavailable")}`} />
        </a>
      </header>
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
          <TicketFinder eventId={eventId} current={ticketId} onOpen={openTicket} />

          <section className="needs-you" aria-labelledby="attention-h" data-testid="problems">
            <h2 id="attention-h">{t("problems")}
              {snapshot.attention.length ? <span className="count-badge is-alert"><Id>{snapshot.attention.length}</Id></span> : null}</h2>
            {snapshot.attention.length === 0 ? <p className="quiet-ok"><Icon name="check" size={18} /> {t("problemsEmpty")}</p> : (
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
            )}
          </section>

          <Queue rows={snapshot.requests} warn={snapshot.wait_warning_s} critical={snapshot.wait_critical_s}
            current={ticketId} onOpen={openTicket} />

          <dl className="state-strip" aria-label={t("opsCars")}>
            {["RECEIVED", "PARKED", "RETRIEVING", "READY", "DELIVERED"].map((s) => (
              <div key={s} data-testid={`count-${s}`}><dt>{state(s)}</dt><dd><Id>{snapshot.counts[s] ?? 0}</Id></dd></div>
            ))}
          </dl>
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
