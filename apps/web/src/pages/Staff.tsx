import { type FormEvent, useState } from "react";

import { ROLE_RANK, api, atLeast, type Me, type Role, type Schemas } from "../api/client";
import { Icon } from "../components/Icon";
import { Empty, Id, PageData, StaleBanner, StatusPill } from "../components/States";
import { useT, type StringKey } from "../strings";
import { useCommand } from "../useCommand";
import { usePoll } from "../usePoll";

// Highest role each role may grant (mirrors ops.services.staffdir.MAX_GRANT; the server is the authority).
const MAX_GRANT: Partial<Record<Role, Role>> = { MANAGER: "SUPERVISOR", ADMIN: "MANAGER", SUPER_ADMIN: "SUPER_ADMIN" };
const ROLES = Object.keys(ROLE_RANK) as Role[];
const grantable = (me: Me) => ROLES.filter((r) => ROLE_RANK[r] <= ROLE_RANK[MAX_GRANT[me.role] ?? "VALET"]);

function CreateStaff({ me, disabled, onDone }: { me: Me; disabled: boolean; onDone: () => void }) {
  const { t } = useT();
  const empty = { full_name: "", phone: "", role: "VALET" as Role, username: "", password: "" };
  const [form, setForm] = useState(empty);
  const { run, busy, problem } = useCommand();
  const needsLogin = ROLE_RANK[form.role] >= ROLE_RANK.SUPERVISOR;
  const set = (k: keyof typeof empty, v: string) => setForm((f) => ({ ...f, [k]: v }));

  async function submit(e: FormEvent) {
    e.preventDefault();
    const body = { ...form, username: needsLogin ? form.username.trim() : "", password: needsLogin ? form.password : "",
      full_name: form.full_name.trim(), phone: form.phone.trim() };
    if (await run((key) => api.createStaff(body, key))) {
      setForm(empty);
      onDone();
    }
  }
  return (
    <details className="card disclosure">
      <summary><Icon name="user" /> {t("addStaff")}</summary>
      <form className="form-grid" onSubmit={submit} noValidate>
        <label className="field"><span>{t("fullName")}</span>
          <input value={form.full_name} onChange={(e) => set("full_name", e.target.value)} autoComplete="off" /></label>
        <label className="field"><span>{t("phone")}</span>
          <input dir="ltr" inputMode="tel" value={form.phone} onChange={(e) => set("phone", e.target.value)} autoComplete="off" /></label>
        <label className="field"><span>{t("role")}</span>
          <select value={form.role} onChange={(e) => set("role", e.target.value)}>
            {grantable(me).map((r) => <option key={r} value={r}>{t(`role_${r}` as StringKey)}</option>)}
          </select></label>
        {needsLogin ? (
          <>
            <p className="muted span-all">{t("loginOptional")}</p>
            <label className="field"><span>{t("username")}</span>
              <input dir="ltr" value={form.username} onChange={(e) => set("username", e.target.value)} autoComplete="off" /></label>
            <label className="field"><span>{t("password")}</span>
              <input dir="ltr" type="password" value={form.password} onChange={(e) => set("password", e.target.value)}
                autoComplete="new-password" /></label>
          </>
        ) : null}
        {problem ? <p className="form-error span-all" role="alert">{problem}</p> : null}
        <div className="span-all">
          <button type="submit" className="btn btn-primary" data-mutation disabled={disabled || busy}>{t("create")}</button>
        </div>
      </form>
    </details>
  );
}

/** The provisioning URI is a secret: kept in component state only, shown once, never logged or stored. */
function MfaIssue({ person, disabled }: { person: Schemas["StaffRow"]; disabled: boolean }) {
  const { t } = useT();
  const [uri, setUri] = useState("");
  const [copied, setCopied] = useState(false);
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
      <button type="button" className="btn btn-quiet" data-mutation disabled={disabled || busy}
        onClick={() => run(() => api.issueMfa(person.id), (r) => setUri(r.otpauth_uri))}>
        <Icon name="shield" /> {t("issueMfa")}
      </button>
      {problem ? <p className="form-error span-all" role="alert">{problem}</p> : null}
    </>
  );
}

function StaffRowActions({ me, person, disabled, onDone }: { me: Me; person: Schemas["StaffRow"]; disabled: boolean;
  onDone: () => void }) {
  const { t } = useT();
  const [reason, setReason] = useState("");
  const [open, setOpen] = useState(false);
  const { run, busy, problem, setProblem } = useCommand();
  const canGrant = grantable(me);
  const manageable = ROLE_RANK[person.role] <= ROLE_RANK[MAX_GRANT[me.role] ?? "VALET"] && person.id !== me.id;
  if (!manageable) return null;
  return (
    <div className="row-actions">
      {person.enabled ? (
        <>
          <label className="field inline-field">
            <span className="visually-hidden">{t("changeRole")}</span>
            <select value={person.role} disabled={disabled || busy} aria-label={`${t("changeRole")}: ${person.full_name}`}
              onChange={(e) => run((key) => api.staffAction(person.id, "role", { role: e.target.value }, key), onDone)}>
              {canGrant.map((r) => <option key={r} value={r}>{t(`role_${r}` as StringKey)}</option>)}
            </select>
          </label>
          {atLeast(me, "ADMIN") && ROLE_RANK[person.role] >= ROLE_RANK.MANAGER ? <MfaIssue person={person} disabled={disabled} /> : null}
          <button type="button" className="btn btn-quiet" aria-expanded={open} onClick={() => setOpen(!open)}>
            {t("deactivate")}
          </button>
        </>
      ) : (
        <button type="button" className="btn btn-secondary" data-mutation disabled={disabled || busy}
          onClick={() => run((key) => api.staffAction(person.id, "reactivate", {}, key), onDone)}>
          {t("reactivate")}
        </button>
      )}
      {open && person.enabled ? (
        <form className="action-form span-all" noValidate onSubmit={(e) => {
          e.preventDefault();
          if (!reason.trim()) return setProblem(t("reasonRequired"));
          void run((key) => api.staffAction(person.id, "deactivate", { reason: reason.trim() }, key), () => {
            setOpen(false); setReason(""); onDone();
          });
        }}>
          <label className="field"><span>{t("reason")}</span>
            <textarea rows={2} maxLength={200} value={reason} onChange={(e) => setReason(e.target.value)} /></label>
          <button type="submit" className="btn btn-danger" data-mutation disabled={disabled || busy}>{t("deactivate")}</button>
        </form>
      ) : null}
      {problem ? <p className="form-error span-all" role="alert">{problem}</p> : null}
    </div>
  );
}

export function Staff({ me }: { me: Me }) {
  const { t } = useT();
  const poll = usePoll(api.staff, 30_000, []);
  return (
    <main className="page">
      <h1>{t("staffTitle")}</h1>
      <StaleBanner show={poll.stale} />
      <PageData poll={poll}>
        {(rows) => (
          <>
            <CreateStaff me={me} disabled={poll.stale} onDone={poll.refresh} />
            <section className="card" aria-labelledby="staff-h">
              <h2 id="staff-h" className="visually-hidden">{t("staffTitle")}</h2>
              {rows.length === 0 ? <Empty text={t("staffEmpty")} /> : null}
              <ul className="rows">
                {rows.map((p) => (
                  <li key={p.id} className={`row staff-row ${p.enabled ? "" : "is-disabled"}`} data-testid={`staff-${p.id}`}>
                    <span className="row-title">{p.full_name}</span>
                    <StatusPill tone={p.enabled ? "info" : "neutral"} icon={p.enabled ? "user" : "x"}
                      label={p.enabled ? t(`role_${p.role}` as StringKey) : t("disabled")} />
                    <span className="row-meta"><Id>{p.phone_masked}</Id></span>
                    {p.username ? <span className="row-meta"><Id>{p.username}</Id></span> : null}
                    {ROLE_RANK[p.role] >= ROLE_RANK.MANAGER ? (
                      <StatusPill tone={p.mfa_locked ? "danger" : p.mfa_enrolled ? "success" : "warning"} icon="shield"
                        label={p.mfa_locked ? t("mfaLockedLabel") : p.mfa_enrolled ? t("mfaOn") : t("mfaOff")} />
                    ) : null}
                    <StaffRowActions me={me} person={p} disabled={poll.stale} onDone={poll.refresh} />
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
