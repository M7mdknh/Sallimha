import { type FormEvent, useRef, useState } from "react";

import { ApiError, api, newKey, type Schemas } from "../api/client";
import { useT, type StringKey } from "../strings";
import { usePoll } from "../usePoll";
import { Icon } from "./Icon";
import { Id, LoadFailed, SkeletonRows, StatusPill } from "./States";

type Field = { name: string; label: StringKey; kind: "text" | "textarea" | "number" | "staff" | "check" | "select";
  options?: [string, StringKey][]; required?: boolean };

// Each action maps to a console command; the server re-checks permission, scope and state.
const ACTIONS: Record<string, { endpoint: string; hint?: StringKey; fields: Field[]; destructive?: boolean }> = {
  cancel: { endpoint: "cancel", hint: "action_cancel_hint", destructive: true, fields: [
    { name: "guest_has_vehicle_and_keys", label: "guestHasCar", kind: "check", required: true },
    { name: "reason", label: "reason", kind: "textarea", required: true }] },
  withdraw: { endpoint: "withdraw", hint: "action_withdraw_hint", destructive: true, fields: [
    { name: "reason", label: "reason", kind: "textarea", required: true }] },
  withdraw_with_custody: { endpoint: "withdraw-with-custody", hint: "action_withdraw_with_custody_hint", destructive: true,
    fields: [{ name: "zone_code", label: "zone", kind: "text", required: true },
      { name: "detail", label: "spot", kind: "text" }, { name: "hook_number", label: "hook", kind: "number", required: true },
      { name: "reason", label: "reason", kind: "textarea", required: true }] },
  custody_transfer: { endpoint: "custody-transfer", hint: "action_custody_transfer_hint", fields: [
    { name: "to_staff_id", label: "toStaff", kind: "staff", required: true },
    { name: "vehicle_location", label: "vehicleWhere", kind: "text", required: true },
    { name: "key_location", label: "keyWhere", kind: "text", required: true },
    { name: "reason", label: "reason", kind: "textarea", required: true }] },
  intake_transfer: { endpoint: "intake-transfer", fields: [
    { name: "to_staff_id", label: "toStaff", kind: "staff", required: true },
    { name: "reason", label: "reason", kind: "textarea", required: true }] },
  correct_phone: { endpoint: "correct-phone", hint: "action_correct_phone_hint", fields: [
    { name: "phone", label: "newPhone", kind: "text", required: true },
    { name: "reason", label: "reason", kind: "textarea", required: true }] },
  confirm_receipt: { endpoint: "confirm-receipt", fields: [
    { name: "received", label: "received", kind: "check" }] },
  except_intake: { endpoint: "except-intake", fields: [
    { name: "kind", label: "kind", kind: "select", options: [["photos", "kind_photos"], ["vehicle", "kind_vehicle"]], required: true },
    { name: "reason", label: "reason", kind: "textarea", required: true }] },
};

function ActionForm({ action, ticketId, team, disabled, onDone }: { action: string; ticketId: number;
  team: Schemas["TeamMember"][]; disabled: boolean; onDone: () => void }) {
  const { t, error } = useT();
  const spec = ACTIONS[action];
  const [values, setValues] = useState<Record<string, string | boolean>>({});
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  const key = useRef(newKey()); // stable across retries of this form (idempotent resubmit)

  async function submit(e: FormEvent) {
    e.preventDefault();
    const missing = spec.fields.find((f) => f.required && f.kind !== "check" && !String(values[f.name] ?? "").trim());
    if (missing) {
      setProblem(missing.name === "reason" ? t("reasonRequired") : error("invalid_input"));
      return;
    }
    setBusy(true);
    setProblem("");
    const body: Record<string, unknown> = {};
    for (const f of spec.fields) {
      const v = values[f.name];
      body[f.name] = f.kind === "check" ? Boolean(v) : f.kind === "number" || f.kind === "staff" ? Number(v) : String(v ?? "").trim();
    }
    try {
      await api.ticketAction(ticketId, spec.endpoint, body, key.current);
      key.current = newKey();
      onDone();
    } catch (err) {
      setProblem(error(err instanceof ApiError ? err.code : "generic"));
    } finally {
      setBusy(false);
    }
  }

  const set = (name: string, value: string | boolean) => setValues((v) => ({ ...v, [name]: value }));
  const available = team.filter((m) => m.status === "available");
  return (
    <form className="action-form" onSubmit={submit} noValidate>
      {spec.hint ? <p className="muted">{t(spec.hint)}</p> : null}
      {spec.fields.map((f) => (
        <label key={f.name} className={f.kind === "check" ? "check" : "field"}>
          {f.kind === "check" ? (
            <>
              <input type="checkbox" checked={Boolean(values[f.name])} onChange={(e) => set(f.name, e.target.checked)} />
              <span>{t(f.label)}</span>
            </>
          ) : (
            <>
              <span>{t(f.label)}</span>
              {f.kind === "textarea" ? (
                <textarea rows={2} maxLength={200} value={String(values[f.name] ?? "")} onChange={(e) => set(f.name, e.target.value)} />
              ) : f.kind === "staff" ? (
                <select value={String(values[f.name] ?? "")} onChange={(e) => set(f.name, e.target.value)}>
                  <option value="">—</option>
                  {available.map((m) => <option key={m.staff_id} value={m.staff_id}>{m.name}</option>)}
                </select>
              ) : f.kind === "select" ? (
                <select value={String(values[f.name] ?? "")} onChange={(e) => set(f.name, e.target.value)}>
                  <option value="">—</option>
                  {f.options!.map(([v, label]) => <option key={v} value={v}>{t(label)}</option>)}
                </select>
              ) : (
                <input dir={f.kind === "number" || f.name === "phone" ? "ltr" : undefined}
                  inputMode={f.kind === "number" ? "numeric" : f.name === "phone" ? "tel" : undefined}
                  value={String(values[f.name] ?? "")} onChange={(e) => set(f.name, e.target.value)} />
              )}
            </>
          )}
        </label>
      ))}
      {problem ? <p className="form-error" role="alert">{problem}</p> : null}
      <button type="submit" data-mutation className={`btn ${spec.destructive ? "btn-danger" : "btn-primary"}`} disabled={disabled || busy}>
        {t(`action_${action}` as StringKey)}
      </button>
    </form>
  );
}

export function TicketPanel({ ticketId, team, disabled, onClose, onChanged }: { ticketId: number; eventId: number;
  team: Schemas["TeamMember"][]; disabled: boolean; onClose: () => void; onChanged: () => void }) {
  const { t, state } = useT();
  const { data, error, refresh } = usePoll(() => api.ticket(ticketId), 5_000, [ticketId]);
  const [open, setOpen] = useState<string | null>(null);

  return (
    <section className="card ticket-panel" aria-labelledby="ticket-h">
      <div className="panel-head">
        <h2 id="ticket-h">{t("ticket")} {data ? <Id>{data.ticket}</Id> : null}</h2>
        <button type="button" className="btn btn-quiet" onClick={onClose} aria-label={t("close")}>
          <Icon name="x" />
        </button>
      </div>
      {data === null ? (error ? <LoadFailed onRetry={refresh} /> : <SkeletonRows rows={4} />) : (
        <>
          <div className="pills">
            <StatusPill tone="info" icon="car" label={state(data.state)} />
            <StatusPill tone={data.contact_state === "CONFIRMED_IN_PERSON" ? "success" : "warning"}
              icon={data.contact_state === "CONFIRMED_IN_PERSON" ? "check" : "alert"} label={state(data.contact_state)} />
            {data.request ? <StatusPill tone="neutral" icon="clock" label={state(data.request.state)} /> : null}
          </div>
          <dl className="facts">
            <div><dt>{t("vehicle")}</dt><dd>{data.vehicle}</dd></div>
            <div><dt>{t("phone")}</dt><dd><Id>{data.phone_masked ?? "—"}</Id></dd></div>
            <div><dt>{t("location")}</dt><dd><Id>{data.location || "—"}</Id></dd></div>
            <div><dt>{t("key")}</dt><dd><Id>{data.hook ?? "—"}</Id></dd></div>
            <div><dt>{t("registeredBy")}</dt><dd>{data.registered_by}</dd></div>
            <div><dt>{t("parkedBy")}</dt><dd>{data.parked_by ?? "—"}</dd></div>
            <div><dt>{t("owner")}</dt><dd>{data.assignee ?? t("unassigned")}</dd></div>
            <div><dt>{t("photos")}</dt><dd>{data.media.length}</dd></div>
          </dl>
          {data.holds.length ? (
            <ul className="rows">{data.holds.map((h) => (
              <li key={h.id} className="row"><StatusPill tone="danger" icon="shield" label={t("holds")} /> {h.reason}</li>
            ))}</ul>
          ) : null}
          <div className="actions">
            {data.allowed_actions.length === 0 ? <p className="muted">{t("noActions")}</p> : null}
            {data.allowed_actions.filter((a) => ACTIONS[a]).map((a) => (
              <div key={a} className="action">
                <button type="button" className="btn btn-secondary btn-block" aria-expanded={open === a}
                  onClick={() => setOpen(open === a ? null : a)}>
                  {t(`action_${a}` as StringKey)}
                </button>
                {open === a ? (
                  <ActionForm action={a} ticketId={ticketId} team={team} disabled={disabled}
                    onDone={() => { setOpen(null); void refresh(); onChanged(); }} />
                ) : null}
              </div>
            ))}
          </div>
          <details className="timeline">
            <summary>{t("timeline")} ({data.timeline.length})</summary>
            <ol>{data.timeline.map((e, i) => <li key={i}><Id>{new Date(e.at).toLocaleTimeString("en-GB", { timeZone: "Asia/Riyadh" })}</Id> {e.action}</li>)}</ol>
          </details>
        </>
      )}
    </section>
  );
}
