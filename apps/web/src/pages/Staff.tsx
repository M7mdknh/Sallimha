import { type FormEvent, useState } from "react";

import { api, type Me, type Role, type Schemas } from "../api/client";
import { Icon } from "../components/Icon";
import { Empty, Id, StatusPill } from "../components/States";
import { useT, type StringKey } from "../strings";
import { useCommand } from "../useCommand";

const ROLES: Role[] = ["VALET", "SUPERVISOR", "ADMIN"];
type Person = Schemas["StaffRow"];

/** Add a person: name, mobile and role. No password — they choose their own with a one-time setup code. */
function AddPerson({ eventId, disabled, onDone }: { eventId?: number; disabled: boolean; onDone: (id: number) => void }) {
  const { t } = useT();
  const empty = { full_name: "", phone: "", role: "VALET" as Role, team: true };
  const [form, setForm] = useState(empty);
  const { run, busy, problem, done } = useCommand();
  async function submit(e: FormEvent) {
    e.preventDefault();
    const body = { full_name: form.full_name.trim(), phone: form.phone.trim(), role: form.role,
      ...(eventId && form.team ? { event_id: eventId } : {}) };
    await run((key) => api.createStaff(body, key), (r) => { setForm(empty); onDone(r.id); });
  }
  return (
    <details className="card disclosure" data-testid="add-person">
      <summary><Icon name="user" /> {t("addPerson")}</summary>
      <form className="form-grid" onSubmit={submit} noValidate>
        <label className="field"><span>{t("fullName")}</span>
          <input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} autoComplete="off" /></label>
        <label className="field"><span>{t("mobile")}</span>
          <input dir="ltr" type="tel" inputMode="tel" value={form.phone} autoComplete="off"
            onChange={(e) => setForm({ ...form, phone: e.target.value })} /></label>
        <fieldset className="choices choices-inline span-all">
          <legend>{t("role")}</legend>
          {ROLES.map((r) => (
            <label key={r} className={`choice ${form.role === r ? "is-on" : ""}`}>
              <input type="radio" name="new-role" checked={form.role === r} onChange={() => setForm({ ...form, role: r })} />
              <span>{t(`role_${r}` as StringKey)}</span>
            </label>
          ))}
        </fieldset>
        {eventId ? (
          <label className="check span-all">
            <input type="checkbox" checked={form.team} onChange={(e) => setForm({ ...form, team: e.target.checked })} />
            <span>{t("addToThisTeam")}</span>
          </label>
        ) : null}
        {problem ? <p className="form-error span-all" role="alert">{problem}</p> : null}
        {done && !problem ? <p className="notice notice-success span-all" role="status">{t("personAdded")}</p> : null}
        <div className="span-all">
          <button type="submit" className="btn btn-primary" data-mutation disabled={disabled || busy}>{t("add")}</button>
        </div>
      </form>
    </details>
  );
}

/** The one-time setup code: kept in component memory only and shown once. Issuing a new one cancels the old one. */
function SetupCode({ person, disabled, autoOpen }: { person: Person; disabled: boolean; autoOpen?: boolean }) {
  const { t, lang, error } = useT();
  const [issued, setIssued] = useState<Schemas["SetupCodeResponse"] | null>(null);
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  if (issued) {
    return (
      <div className="secret-once span-all" role="status" data-testid="setup-code">
        <p><strong>{t("setupCodeFor")}</strong></p>
        <p className="setup-code"><Id>{issued.setup_code}</Id></p>
        <p className="muted">{t("signInName")}: <Id>{issued.sign_in_name}</Id> · <Id>{new Date(issued.expires_at)
          .toLocaleString(lang === "ar" ? "ar-SA-u-nu-latn" : "en-GB", { dateStyle: "short", timeStyle: "short" })}</Id></p>
        <p className="muted">{t("setupCodeHint")}</p>
        <button type="button" className="btn btn-quiet" onClick={() => setIssued(null)}>{t("close")}</button>
      </div>
    );
  }
  return (
    <>
      <button type="button" className={`btn ${autoOpen ? "btn-primary" : "btn-secondary"}`} data-mutation
        disabled={disabled || busy} onClick={async () => {
          setBusy(true);
          setProblem("");
          try {
            setIssued(await api.issueSetupCode(person.id));
          } catch (err) {
            setProblem(error((err as { code?: string }).code ?? "generic"));
          } finally {
            setBusy(false);
          }
        }}>
        <Icon name="key" /> {t("issueSetup")}
      </button>
      {problem ? <p className="form-error span-all" role="alert">{problem}</p> : null}
    </>
  );
}

/** The provisioning URI is a secret: kept in component state only, shown once, never logged or stored.
 *  Issuing replaces the person's current authenticator and signs them out, so it is confirmed first. */
function MfaIssue({ person, disabled }: { person: Person; disabled: boolean }) {
  const { t } = useT();
  const [uri, setUri] = useState("");
  const [copied, setCopied] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const { run, busy, problem } = useCommand();
  if (uri) {
    return (
      <div className="secret-once span-all" role="status">
        <p className="muted">{t("mfaOnce")}</p>
        <code className="otp-uri" dir="ltr">{uri}</code>
        <span className="row-actions">
          <button type="button" className="btn btn-secondary" onClick={async () => {
            try { await navigator.clipboard.writeText(uri); setCopied(true); } catch { setCopied(false); }
          }}>{copied ? t("copied") : t("copy")}</button>
          <button type="button" className="btn btn-quiet" onClick={() => { setUri(""); setCopied(false); }}>{t("close")}</button>
        </span>
      </div>
    );
  }
  return (
    <>
      {confirming ? (
        <span className="confirm-inline span-all" role="group" aria-label={t("issueMfa")}>
          <span className="muted">{t("issueMfaConfirm")}</span>
          <button type="button" className="btn btn-primary" data-mutation disabled={disabled || busy}
            onClick={() => run(() => api.issueMfa(person.id), (r) => { setConfirming(false); setUri(r.otpauth_uri); })}>
            {t("confirm")}
          </button>
          <button type="button" className="btn btn-quiet" onClick={() => setConfirming(false)}>{t("cancel")}</button>
        </span>
      ) : (
        <button type="button" className="btn btn-quiet" onClick={() => setConfirming(true)}>
          <Icon name="shield" /> {t("issueMfa")}
        </button>
      )}
      {problem ? <p className="form-error span-all" role="alert">{problem}</p> : null}
    </>
  );
}

/** Choosing a role only stages it; the grant (which also signs the person out) needs a confirm. */
function RoleChange({ person, disabled, onDone }: { person: Person; disabled: boolean; onDone: () => void }) {
  const { t } = useT();
  const [role, setRole] = useState<Role>(person.role);
  const { run, busy, problem } = useCommand();
  const staged = role !== person.role;
  return (
    <>
      <label className="field inline-field">
        <span className="visually-hidden">{t("changeRole")}</span>
        <select value={role} disabled={disabled || busy} aria-label={`${t("changeRole")}: ${person.full_name}`}
          onChange={(e) => setRole(e.target.value as Role)}>
          {ROLES.map((r) => <option key={r} value={r}>{t(`role_${r}` as StringKey)}</option>)}
        </select>
      </label>
      {staged ? (
        <span className="confirm-inline">
          <button type="button" className="btn btn-primary" data-mutation disabled={disabled || busy}
            onClick={() => run((key) => api.staffAction(person.id, "role", { role }, key), onDone)}>
            {t("changeRole")}
          </button>
          <button type="button" className="btn btn-quiet" onClick={() => setRole(person.role)}>{t("cancel")}</button>
        </span>
      ) : null}
      {problem ? <p className="form-error span-all" role="alert">{problem}</p> : null}
    </>
  );
}

function Deactivate({ person, disabled, onDone }: { person: Person; disabled: boolean; onDone: () => void }) {
  const { t } = useT();
  const [reason, setReason] = useState("");
  const [open, setOpen] = useState(false);
  const { run, busy, problem, setProblem } = useCommand();
  return (
    <>
      <button type="button" className="btn btn-quiet" aria-expanded={open} onClick={() => setOpen(!open)}>
        {t("deactivate")}
      </button>
      {open ? (
        <form className="action-form span-all" noValidate onSubmit={(e) => {
          e.preventDefault();
          if (!reason.trim()) return setProblem(t("reasonRequired"));
          void run((key) => api.staffAction(person.id, "deactivate", { reason: reason.trim() }, key), () => {
            setOpen(false); setReason(""); onDone();
          });
        }}>
          <label className="field"><span>{t("reason")}</span>
            <textarea rows={2} maxLength={200} value={reason} onChange={(e) => setReason(e.target.value)} /></label>
          {problem ? <p className="form-error" role="alert">{problem}</p> : null}
          <button type="submit" className="btn btn-danger" data-mutation disabled={disabled || busy}>{t("deactivate")}</button>
        </form>
      ) : null}
    </>
  );
}

function SimpleCommand({ label, disabled, send, onDone, primary }: { label: string; disabled: boolean;
  send: (key: string) => Promise<unknown>; onDone: () => void; primary?: boolean }) {
  const { run, busy, problem } = useCommand();
  return (
    <>
      <button type="button" className={`btn ${primary ? "btn-secondary" : "btn-quiet"}`} data-mutation
        disabled={disabled || busy} onClick={() => run(send, onDone)}>{label}</button>
      {problem ? <p className="form-error span-all" role="alert">{problem}</p> : null}
    </>
  );
}

/** Admins: everyone in the organisation, their sign-in status, this operation's team, and what they may do. */
export function People({ me, rows, eventId, disabled, onChanged }: { me: Me; rows: Person[]; eventId?: number;
  disabled: boolean; onChanged: () => void }) {
  const { t } = useT();
  const [justAdded, setJustAdded] = useState<number | null>(null);
  return (
    <>
      <AddPerson eventId={eventId} disabled={disabled} onDone={(id) => { setJustAdded(id); onChanged(); }} />
      <section className="card" aria-labelledby="people-h">
        <h2 id="people-h"><Icon name="users" /> {t("people")}</h2>
        {rows.length === 0 ? <Empty text={t("staffEmpty")} /> : null}
        <ul className="rows">
          {rows.map((p) => {
            const onTeam = eventId ? p.event_ids.includes(eventId) : false;
            const self = p.id === me.id;
            return (
              <li key={p.id} className={`row staff-row ${p.enabled ? "" : "is-disabled"}`} data-testid={`staff-${p.id}`}>
                <span className="row-title">{p.full_name}</span>
                <StatusPill tone={p.enabled ? "info" : "neutral"} icon={p.enabled ? "user" : "x"}
                  label={p.enabled ? t(`role_${p.role}` as StringKey) : t("disabled")} />
                <span className="row-meta"><Id>{p.phone_masked}</Id></span>
                {p.enabled ? (
                  <StatusPill tone={p.can_sign_in ? "success" : p.setup_pending ? "warning" : "neutral"}
                    icon={p.can_sign_in ? "check" : "key"}
                    label={p.can_sign_in ? t("canSignIn") : p.setup_pending ? t("setupPending") : t("notSetUp")} />
                ) : null}
                {eventId && onTeam ? <StatusPill tone="info" icon="users" label={t("onTeam")} /> : null}
                {p.role === "ADMIN" && p.enabled ? (
                  <StatusPill tone={p.mfa_locked ? "danger" : p.mfa_enrolled ? "success" : "warning"} icon="shield"
                    label={p.mfa_locked ? t("mfaLockedLabel") : p.mfa_enrolled ? t("mfaOn") : t("mfaOff")} />
                ) : null}
                {!self ? (
                  <div className="row-actions">
                    {p.enabled ? (
                      <>
                        <SetupCode key={`${p.id}-${justAdded === p.id}`} person={p} disabled={disabled}
                          autoOpen={justAdded === p.id || !p.can_sign_in} />
                        {eventId ? (
                          <SimpleCommand label={onTeam ? t("takeOffTeam") : t("putOnTeam")} disabled={disabled}
                            send={(key) => api.setTeam(p.id, eventId, !onTeam, key)} onDone={onChanged} />
                        ) : null}
                        <RoleChange key={p.role} person={p} disabled={disabled} onDone={onChanged} />
                        {p.role === "ADMIN" ? <MfaIssue person={p} disabled={disabled} /> : null}
                        <Deactivate person={p} disabled={disabled} onDone={onChanged} />
                      </>
                    ) : (
                      <SimpleCommand label={t("reactivate")} disabled={disabled} primary onDone={onChanged}
                        send={(key) => api.staffAction(p.id, "reactivate", {}, key)} />
                    )}
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      </section>
    </>
  );
}
