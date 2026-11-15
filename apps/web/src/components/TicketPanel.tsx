import { type FormEvent, useRef, useState } from "react";

import { ApiError, api, newKey, type Schemas } from "../api/client";
import { navigate } from "../router";
import { useT, type StringKey } from "../strings";
import { usePoll } from "../usePoll";
import { Icon } from "./Icon";
import { Id, LoadFailed, SkeletonRows, StatusPill } from "./States";

type Field = { name: string; label: StringKey; kind: "text" | "textarea" | "number" | "staff" | "check" | "select" | "hold";
  options?: [string, StringKey][]; required?: boolean; initial?: boolean; max?: number };

export const INCIDENT_CATEGORIES = ["missing_vehicle", "key_issue", "damage", "identity_dispute", "notification_failure",
  "operational_delay", "complaint"] as const;
const REASON: Field = { name: "reason", label: "reason", kind: "textarea", required: true };

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
  open_incident: { endpoint: "open-incident", hint: "action_open_incident_hint", fields: [
    { name: "category", label: "category", kind: "select", required: true,
      options: INCIDENT_CATEGORIES.map((c) => [c, `cat_${c}` as StringKey]) },
    { name: "description", label: "description", kind: "textarea", required: true, max: 2000 }] },
  place_hold: { endpoint: "place-hold", hint: "action_place_hold_hint", destructive: true, fields: [
    { name: "blocks_dispatch", label: "blocksDispatch", kind: "check", initial: true },
    { name: "blocks_handover", label: "blocksHandover", kind: "check", initial: true }, REASON] },
  clear_hold: { endpoint: "clear-hold", hint: "action_clear_hold_hint", fields: [
    { name: "hold_id", label: "hold", kind: "hold", required: true }, REASON] },
  assisted_request: { endpoint: "assisted-request", hint: "action_assisted_request_hint", fields: [REASON] },
  assisted_handover: { endpoint: "assisted-handover", hint: "action_assisted_handover_hint", fields: [
    { name: "method", label: "verification", kind: "select", required: true, options: [
      ["in_person_check", "method_in_person_check"], ["known_guest", "method_known_guest"], ["other", "method_other"]] },
    REASON] },
  relocate_start: { endpoint: "relocate-start", hint: "action_relocate_start_hint", fields: [
    { name: "to_staff_id", label: "toStaff", kind: "staff", required: true }, REASON] },
  relocate_complete: { endpoint: "relocate-complete", fields: [
    { name: "zone_code", label: "zone", kind: "text", required: true }, { name: "detail", label: "spot", kind: "text" },
    { name: "hook_number", label: "hook", kind: "number", required: true }] },
  propose_unclaimed: { endpoint: "propose-unclaimed", hint: "action_propose_unclaimed_hint", fields: [
    { name: "custodian", label: "custodian", kind: "text", required: true },
    { name: "plan", label: "plan", kind: "textarea", required: true, max: 2000 }] },
  approve_unclaimed: { endpoint: "approve-unclaimed", hint: "action_approve_unclaimed_hint", fields: [] },
  release_carryover: { endpoint: "release-carryover", hint: "action_release_carryover_hint", fields: [
    { name: "method", label: "method", kind: "select", required: true, options: [
      ["collected_verified", "release_collected_verified"], ["moved_to_storage", "release_moved_to_storage"],
      ["other", "release_other"]] },
    { name: "note", label: "note", kind: "textarea", required: true, max: 2000 }] },
};

function ActionForm({ action, ticketId, team, holds, disabled, onDone }: { action: string; ticketId: number;
  team: Schemas["TeamMember"][]; holds: Schemas["HoldBrief"][]; disabled: boolean; onDone: () => void }) {
  const { t, error } = useT();
  const spec = ACTIONS[action];
  const [values, setValues] = useState<Record<string, string | boolean>>(() =>
    Object.fromEntries(spec.fields.filter((f) => f.initial !== undefined).map((f) => [f.name, f.initial!])));
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
      body[f.name] = f.kind === "check" ? Boolean(v)
        : f.kind === "number" || f.kind === "staff" || f.kind === "hold" ? Number(v) : String(v ?? "").trim();
    }
    try {
      await api.ticketAction(ticketId, spec.endpoint, body, key.current);
      key.current = newKey();
      onDone();
    } catch (err) {
      if (err instanceof ApiError && err.code === "idempotency_mismatch") key.current = newKey();
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
                <textarea rows={2} maxLength={f.max ?? 200} value={String(values[f.name] ?? "")} onChange={(e) => set(f.name, e.target.value)} />
              ) : f.kind === "staff" ? (
                <select value={String(values[f.name] ?? "")} onChange={(e) => set(f.name, e.target.value)}>
                  <option value="">—</option>
                  {available.map((m) => <option key={m.staff_id} value={m.staff_id}>{m.name}</option>)}
                </select>
              ) : f.kind === "hold" ? (
                <select value={String(values[f.name] ?? "")} onChange={(e) => set(f.name, e.target.value)}>
                  <option value="">—</option>
                  {holds.map((h) => <option key={h.id} value={h.id}>{h.reason}</option>)}
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

export function TicketPanel({ ticketId, eventId, team, disabled, onClose, onChanged }: { ticketId: number; eventId: number;
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
            <ul className="rows" aria-label={t("holds")}>{data.holds.map((h) => (
              <li key={h.id} className="row attention-critical">
                <StatusPill tone="danger" icon="shield" label={t("hold")} />
                <span>{h.reason}</span>
                <span className="row-meta">
                  {[h.blocks_dispatch ? t("blocksDispatch") : "", h.blocks_handover ? t("blocksHandover") : ""].filter(Boolean).join(" · ")}
                </span>
              </li>
            ))}</ul>
          ) : null}
          {data.incidents.length ? (
            <ul className="rows" aria-label={t("incidents")}>{data.incidents.map((i) => (
              <li key={i.id}>
                <a className="row row-link-plain" href={`/events/${eventId}/incidents/${i.id}`}
                  onClick={(e) => { e.preventDefault(); navigate(`/events/${eventId}/incidents/${i.id}`); }}>
                  <StatusPill tone={i.status === "RESOLVED" ? "neutral" : "warning"} icon="alert" label={t(`cat_${i.category}` as StringKey)} />
                  <span className="row-meta">{state(i.status)}</span>
                </a>
              </li>
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
                  <ActionForm action={a} ticketId={ticketId} team={team} holds={data.holds} disabled={disabled}
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
