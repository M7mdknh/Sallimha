import { useState } from "react";

import { api, isAdmin, type Me, type Schemas } from "../api/client";
import { Icon } from "../components/Icon";
import { Empty, Id, LoadFailed, SkeletonRows, StaleBanner, StatusPill } from "../components/States";
import { navigate } from "../router";
import { useT } from "../strings";
import { useCommand } from "../useCommand";
import { usePoll } from "../usePoll";
import { useActiveEvent } from "./Ops";
import { CommandForm, LIVE_INTAKE } from "./Outages";
import { People } from "./Staff";
import { currentZone } from "../venueTime";

const STATUS: Record<string, [string, string]> = {
  available: ["success", "check"], busy: ["info", "car"], unavailable: ["neutral", "clock"],
};

/** Staff connectivity loss: mark that this valet's device is not working (reason required) or that it is back. */
function DeviceDown({ member, disabled, onDone }: { member: Schemas["TeamMember"]; disabled: boolean; onDone: () => void }) {
  const { t } = useT();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const { run, busy, problem, setProblem } = useCommand();
  if (member.assisted) {
    return (
      <>
        <button type="button" className="btn btn-secondary" data-mutation disabled={disabled || busy}
          onClick={() => run((key) => api.assistShift(member.shift_id, false, "", key), onDone)}>
          <Icon name="check" /> {t("deviceBack")}
        </button>
        {problem ? <p className="form-error span-all" role="alert">{problem}</p> : null}
      </>
    );
  }
  return (
    <>
      <button type="button" className="btn btn-quiet" aria-expanded={open} onClick={() => setOpen(!open)}>
        <Icon name="wifiOff" /> {t("deviceDown")}
      </button>
      {open ? (
        <form className="action-form span-all" noValidate onSubmit={(e) => {
          e.preventDefault();
          if (!reason.trim()) return setProblem(t("reasonRequired"));
          void run((key) => api.assistShift(member.shift_id, true, reason.trim(), key), () => {
            setOpen(false); setReason(""); onDone();
          });
        }}>
          <p className="muted">{t("deviceDownHint")}</p>
          <label className="field"><span>{t("deviceDownReason")}</span>
            <textarea rows={2} maxLength={200} value={reason} onChange={(e) => setReason(e.target.value)} /></label>
          {problem ? <p className="form-error" role="alert">{problem}</p> : null}
          <button type="submit" className="btn btn-primary" data-mutation disabled={disabled || busy}>{t("deviceDown")}</button>
        </form>
      ) : null}
    </>
  );
}

function ShiftButton({ label, send, disabled, onDone, primary }: { label: string; send: (key: string) => Promise<unknown>;
  disabled: boolean; onDone: () => void; primary?: boolean }) {
  const { run, busy, problem } = useCommand();
  return (
    <>
      <button type="button" className={`btn ${primary ? "btn-secondary" : "btn-quiet"}`} data-mutation
        disabled={disabled || busy} onClick={() => run(send, onDone)}>{label}</button>
      {problem ? <p className="form-error span-all" role="alert">{problem}</p> : null}
    </>
  );
}

function TonightsTeam({ eventId, snapshot, disabled, refresh }: { eventId: number; snapshot: Schemas["LiveSnapshot"];
  disabled: boolean; refresh: () => void }) {
  const { t, state } = useT();
  const [adding, setAdding] = useState("");
  const assisted = snapshot.team.filter((m) => m.assisted && m.role === "VALET");
  return (
    <>
      <section className="card" aria-labelledby="team-h" data-testid="tonights-team">
        <h2 id="team-h"><Icon name="users" /> {t("teamTonight")} <span className="muted">— {snapshot.event.name}</span></h2>
        {snapshot.team.length === 0 && snapshot.not_started.length === 0 ? <Empty text={t("teamEmpty")} /> : null}
        <ul className="rows">
          {snapshot.team.map((m) => {
            const [tone, icon] = STATUS[m.status];
            return (
              <li key={m.shift_id} className={`row ${m.assisted ? "attention-warning" : ""}`} data-testid={`member-${m.staff_id}`}>
                <span className="row-title">{m.name}</span>
                <StatusPill tone={tone} icon={icon} label={state(m.status)} />
                {m.assisted ? <StatusPill tone="warning" icon="wifiOff" label={t("recordsForThem")} /> : null}
                {m.task ? (
                  <a className="row-meta" href={`/events/${eventId}/tickets/${m.task.ticket_id}`}
                    onClick={(e) => { e.preventDefault(); navigate(`/events/${eventId}/tickets/${m.task!.ticket_id}`); }}>
                    {state(m.task.type)} <Id>{m.task.ticket}</Id>
                  </a>
                ) : null}
                <span className="row-meta">{t("doneThisShift")} <Id>{m.done}</Id></span>
                <span className="row-actions">
                  {m.role === "VALET" ? <DeviceDown member={m} disabled={disabled} onDone={refresh} /> : null}
                  {!m.task ? (
                    <ShiftButton label={t("endShift")} disabled={disabled} onDone={refresh}
                      send={(key) => api.endShift(m.shift_id, key)} />
                  ) : null}
                </span>
              </li>
            );
          })}
          {snapshot.not_started.map((p) => (
            <li key={`ns-${p.staff_id}`} className="row">
              <span className="row-title">{p.name}</span>
              <StatusPill tone="neutral" icon="clock" label={t("notStarted")} />
              <span className="row-actions">
                <ShiftButton label={t("startShift")} primary disabled={disabled} onDone={refresh}
                  send={(key) => api.startShift(eventId, p.staff_id, key)} />
              </span>
            </li>
          ))}
        </ul>
        {snapshot.addable.length ? (
          <form className="inline-form" onSubmit={(e) => e.preventDefault()}>
            <label className="field grow">
              <span>{t("addToTeam")}</span>
              <select value={adding} onChange={(e) => setAdding(e.target.value)}>
                <option value="">—</option>
                {snapshot.addable.map((p) => <option key={p.staff_id} value={p.staff_id}>{p.name}</option>)}
              </select>
            </label>
            <ShiftButton label={t("startShift")} primary disabled={disabled || !adding}
              onDone={() => { setAdding(""); refresh(); }} send={(key) => api.startShift(eventId, Number(adding), key)} />
          </form>
        ) : null}
      </section>
      {assisted.length ? (
        <section className="card" aria-labelledby="for-them-h">
          <h2 id="for-them-h"><Icon name="car" /> {t("intakeOnBehalf")}</h2>
          <p className="muted">{t("intakeOnBehalfHint")}</p>
          <CommandForm fields={[...LIVE_INTAKE, { name: "confirmed_via", label: "confirmedVia", kind: "via" },
            { name: "reason", label: "reason", kind: "textarea" }]} submitLabel="recordIntake"
            valets={assisted.map((m) => ({ id: m.staff_id, name: m.name, role: "VALET" }))} zone={currentZone()}
            disabled={disabled}
            send={(b, k) => api.intakeOnBehalf(eventId, b as Schemas["IntakeOnBehalfRequestRequest"], k)
              .then((r) => navigate(`/events/${eventId}/tickets/${r.id}`))}
            openTicket={(id) => navigate(`/events/${eventId}/tickets/${id}`)}
            onDone={refresh} />
        </section>
      ) : null}
    </>
  );
}

/** Team: tonight's shifts for supervisors and admins; admins also manage people (ADR-0011). */
export function Team({ me, eventHint }: { me: Me; eventHint?: number }) {
  const { t } = useT();
  const { eventId, loading } = useActiveEvent(eventHint);
  const live = usePoll(() => (eventId ? api.live(eventId) : Promise.resolve(null)), 5_000, [eventId]);
  const staff = usePoll(() => (isAdmin(me) ? api.staff() : Promise.resolve(null)), 30_000, [me.id]);
  const refresh = () => { live.refresh(); staff.refresh(); };
  return (
    <main className="page">
      <h1>{t("navTeam")}</h1>
      <StaleBanner show={live.stale} />
      {loading || (eventId && live.data === null && !live.error) ? <SkeletonRows rows={4} /> : null}
      {eventId && live.error && live.data === null ? <LoadFailed onRetry={live.refresh} /> : null}
      {!loading && !eventId ? <Empty text={isAdmin(me) ? t("opsNoOperationBody") : t("opsNoOperationSupervisor")} /> : null}
      {eventId && live.data ? (
        <TonightsTeam eventId={eventId} snapshot={live.data} disabled={live.stale} refresh={refresh} />
      ) : null}
      {isAdmin(me) && staff.data ? (
        <People me={me} rows={staff.data} eventId={eventId} disabled={staff.stale} onChanged={refresh} />
      ) : null}
      {isAdmin(me) && staff.error && !staff.data ? <LoadFailed onRetry={staff.refresh} /> : null}
    </main>
  );
}

