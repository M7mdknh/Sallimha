import { type FormEvent, useState } from "react";

import { api, atLeast, type Me, type Schemas } from "../api/client";
import { Icon } from "../components/Icon";
import { Empty, Id, PageData, StaleBanner, StatusPill } from "../components/States";
import { useT, type StringKey } from "../strings";
import { useCommand } from "../useCommand";
import { usePoll } from "../usePoll";
import { currentZone, venueTime } from "../venueTime";

type Field = { name: string; label: StringKey; kind?: "text" | "number" | "datetime" | "textarea" | "valet" | "via";
  required?: boolean; ltr?: boolean };

/** A small form whose fields map 1:1 to a command body. Local times are the venue's (labelled with the zone). */
function CommandForm({ fields, submitLabel, valets, zone, disabled, destructive, send, onDone }: {
  fields: Field[]; submitLabel: StringKey; valets: Schemas["PersonRow"][]; zone: string; disabled: boolean;
  destructive?: boolean; send: (body: Record<string, unknown>, key: string) => Promise<unknown>; onDone: () => void }) {
  const { t, error } = useT();
  const [values, setValues] = useState<Record<string, string>>({});
  const { run, busy, problem, done, setProblem } = useCommand();
  const set = (name: string, value: string) => setValues((v) => ({ ...v, [name]: value }));

  async function submit(e: FormEvent) {
    e.preventDefault();
    const missing = fields.find((f) => f.required !== false && !String(values[f.name] ?? "").trim());
    if (missing) return setProblem(error("invalid_input"));
    const body: Record<string, unknown> = {};
    for (const f of fields) {
      const v = (values[f.name] ?? "").trim();
      body[f.name] = f.kind === "number" || f.kind === "valet" ? Number(v) : v;
    }
    if (await run((key) => send(body, key), onDone)) setValues({});
  }

  return (
    <form className="form-grid" onSubmit={submit} noValidate>
      {fields.map((f) => (
        <label key={f.name} className={`field ${f.kind === "textarea" ? "span-all" : ""}`}>
          <span>{t(f.label)}{f.kind === "datetime" ? ` (${zone})` : ""}</span>
          {f.kind === "textarea" ? (
            <textarea rows={2} maxLength={2000} value={values[f.name] ?? ""} onChange={(e) => set(f.name, e.target.value)} />
          ) : f.kind === "valet" ? (
            <select value={values[f.name] ?? ""} onChange={(e) => set(f.name, e.target.value)}>
              <option value="">—</option>
              {valets.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          ) : f.kind === "via" ? (
            <select value={values[f.name] ?? ""} onChange={(e) => set(f.name, e.target.value)}>
              <option value="">—</option>
              <option value="in_person">{t("via_in_person")}</option>
              <option value="radio">{t("via_radio")}</option>
            </select>
          ) : (
            <input type={f.kind === "datetime" ? "datetime-local" : "text"} dir={f.ltr || f.kind === "datetime" ||
              f.kind === "number" ? "ltr" : undefined} inputMode={f.kind === "number" ? "numeric" : undefined}
              value={values[f.name] ?? ""} onChange={(e) => set(f.name, e.target.value)} />
          )}
        </label>
      ))}
      {problem ? <p className="form-error span-all" role="alert">{problem}</p> : null}
      {done && !problem ? <p className="muted span-all" role="status">{t("saved")}</p> : null}
      <div className="span-all">
        <button type="submit" className={`btn ${destructive ? "btn-danger" : "btn-primary"}`} data-mutation
          disabled={disabled || busy}>{t(submitLabel)}</button>
      </div>
    </form>
  );
}

const INTAKE: Field[] = [
  { name: "valet_id", label: "valetLabel", kind: "valet" }, { name: "guest_phone", label: "phone", ltr: true },
  { name: "plate", label: "plateLabel", ltr: true }, { name: "description", label: "vehicle", required: false },
  { name: "zone_code", label: "zone", ltr: true }, { name: "detail", label: "spot", required: false },
  { name: "hook_number", label: "hook", kind: "number" }];

export function Outages({ me, eventId }: { me: Me; eventId?: number }) {
  const { t, lang } = useT();
  const poll = usePoll(api.outages, 15_000, []);
  const people = usePoll(() => (eventId ? api.people(eventId) : Promise.resolve([])), 60_000, [eventId]);
  const valets = (people.data ?? []).filter((p) => p.role === "VALET");
  const manager = atLeast(me, "MANAGER");
  const zone = currentZone(); // the event being worked; the server reads entered times in its venue's zone
  return (
    <main className="page">
      <h1>{t("outagesTitle")}</h1>
      <StaleBanner show={poll.stale} />
      <PageData poll={poll}>
        {(o) => (
          <>
            <section className={`card ${o.whatsapp ? "outage-active" : ""}`} aria-labelledby="wa-out-h">
              <h2 id="wa-out-h"><Icon name="message" /> {t("whatsappOutage")}</h2>
              {o.whatsapp ? (
                <>
                  <StatusPill tone="danger" icon="alert" label={t("outageActive")} />
                  <p className="prose">{t("outageActiveBody")}</p>
                  <p className="muted">{o.whatsapp.declared_by} · <Id>{venueTime(o.whatsapp.since, lang)}</Id> · {o.whatsapp.reason}</p>
                  {manager ? (
                    <CommandForm fields={[{ name: "reason", label: "endReason", kind: "textarea" }]} submitLabel="endOutage"
                      valets={valets} zone={zone} disabled={poll.stale}
                      send={(b, k) => api.endOutage(String(b.reason), k)} onDone={poll.refresh} />
                  ) : <p className="muted">{t("outageEndManagers")}</p>}
                </>
              ) : manager ? (
                <>
                  <p className="prose">{t("declareOutageBody")}</p>
                  <CommandForm fields={[{ name: "reason", label: "reason", kind: "textarea" }]} submitLabel="declareOutage"
                    valets={valets} zone={zone} disabled={poll.stale} destructive
                    send={(b, k) => api.declareOutage(String(b.reason), k)} onDone={poll.refresh} />
                </>
              ) : eventId ? (
                <>
                  <p className="prose">{t("reportOutageBody")}</p>
                  <CommandForm fields={[{ name: "reason", label: "reportWhat", kind: "textarea" }]} submitLabel="reportOutage"
                    valets={valets} zone={zone} disabled={poll.stale} destructive
                    send={(b, k) => api.reportOutage(eventId, String(b.reason), k)} onDone={poll.refresh} />
                </>
              ) : null}
            </section>

            {o.whatsapp && eventId ? (
              <section className="card" aria-labelledby="intake-h">
                <h2 id="intake-h"><Icon name="car" /> {t("intakeOnBehalf")}</h2>
                <p className="muted">{t("intakeOnBehalfHint")}</p>
                <CommandForm fields={[...INTAKE, { name: "confirmed_via", label: "confirmedVia", kind: "via" },
                  { name: "reason", label: "reason", kind: "textarea" }]} submitLabel="recordIntake" valets={valets}
                  zone={zone} disabled={poll.stale}
                  send={(b, k) => api.intakeOnBehalf(eventId, b as Schemas["IntakeOnBehalfRequestRequest"], k)}
                  onDone={poll.refresh} />
              </section>
            ) : null}

            {manager && eventId ? (
              <section className="card" aria-labelledby="sys-h">
                <h2 id="sys-h"><Icon name="alert" /> {t("systemOutage")}</h2>
                <p className="muted">{t("systemOutageHint")}</p>
                <CommandForm fields={[{ name: "started_at_local", label: "outageStart", kind: "datetime" },
                  { name: "ended_at_local", label: "outageEnd", kind: "datetime" },
                  { name: "reason", label: "reason", kind: "textarea" }]} submitLabel="recordOutage" valets={valets}
                  zone={zone} disabled={poll.stale}
                  send={(b, k) => api.recordSystemOutage(eventId, b as Schemas["SystemOutageRequestRequest"], k)}
                  onDone={poll.refresh} />
                <h3>{t("reconcileIntake")}</h3>
                <p className="muted">{t("reconcileIntakeHint")}</p>
                <CommandForm fields={[...INTAKE, { name: "received_at_local", label: "receivedAt", kind: "datetime" },
                  { name: "parked_at_local", label: "parkedAt", kind: "datetime" },
                  { name: "evidence", label: "evidence", kind: "textarea" }, { name: "reason", label: "reason", kind: "textarea" }]}
                  submitLabel="recordIntake" valets={valets} zone={zone} disabled={poll.stale}
                  send={(b, k) => api.reconcileIntake(eventId, b as Schemas["ReconcileIntakeRequestRequest"], k)}
                  onDone={poll.refresh} />
              </section>
            ) : null}

            {!eventId ? <Empty text={t("outageNeedsEvent")} /> : null}

            <section className="card" aria-labelledby="windows-h">
              <h2 id="windows-h">{t("outageHistory")}</h2>
              {o.windows.length === 0 ? <Empty text={t("noneYet")} /> : (
                <ul className="rows">
                  {o.windows.map((w) => (
                    <li key={w.id} className="row">
                      <StatusPill tone={w.ended_at ? "neutral" : "danger"} icon="alert"
                        label={w.kind === "WHATSAPP" ? t("whatsappOutage") : t("systemOutage")} />
                      <span className="row-meta"><Id>{venueTime(w.started_at, lang)}</Id> – <Id>{w.ended_at ? venueTime(w.ended_at, lang) : "…"}</Id></span>
                      <span className="row-meta">{w.declared_by}</span>
                      <span className="row-meta">{w.reason}</span>
                      {w.kind === "SYSTEM" ? <span className="row-meta">{t("reconciledCount")}: <Id>{w.reconciliations}</Id></span> : null}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </>
        )}
      </PageData>
    </main>
  );
}
