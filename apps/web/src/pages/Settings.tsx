import { type FormEvent, useState } from "react";

import { api, type Schemas } from "../api/client";
import { Icon } from "../components/Icon";
import { PageData, StaleBanner, StatusPill } from "../components/States";
import { useT, type StringKey } from "../strings";
import { useCommand } from "../useCommand";
import { usePoll } from "../usePoll";

type Config = Schemas["ConfigResponse"];

function NumberGroup({ title, hint, prefix, values, extra, disabled, save, children }: { title: StringKey; hint?: StringKey; prefix: string;
  values: Record<string, number>; extra?: (key: string) => React.ReactNode; disabled: boolean;
  save: (values: Record<string, number>, key: string) => Promise<unknown>; children?: React.ReactNode }) {
  const { t } = useT();
  const [draft, setDraft] = useState<Record<string, string>>(() =>
    Object.fromEntries(Object.entries(values).map(([k, v]) => [k, String(v)])));
  const { run, busy, problem, done, setProblem } = useCommand();
  async function submit(e: FormEvent) {
    e.preventDefault();
    const parsed = Object.entries(draft).map(([k, v]) => [k, Number(v)] as const);
    if (parsed.some(([, v]) => !Number.isInteger(v) || v < 0)) return setProblem(t("error_invalid_setting"));
    const changed = Object.fromEntries(parsed.filter(([k, v]) => values[k] !== v));
    if (Object.keys(changed).length) await run((key) => save(changed, key));
  }
  return (
    <section className="card" aria-labelledby={`${prefix}-h`}>
      <h2 id={`${prefix}-h`}><Icon name="clock" /> {t(title)}</h2>
      {hint ? <p className="muted">{t(hint)}</p> : null}
      <form className="form-grid" onSubmit={submit} noValidate>
        {Object.keys(values).map((k) => (
          <label key={k} className="field">
            <span>{t(`${prefix}_${k}` as StringKey)}</span>
            <input dir="ltr" inputMode="numeric" value={draft[k] ?? ""} aria-describedby={extra ? `${prefix}-${k}-x` : undefined}
              onChange={(e) => setDraft((d) => ({ ...d, [k]: e.target.value }))} />
            {extra ? <span id={`${prefix}-${k}-x`} className="muted">{extra(k)}</span> : null}
          </label>
        ))}
        {problem ? <p className="form-error span-all" role="alert">{problem}</p> : null}
        {done && !problem ? <p className="muted span-all" role="status">{t("saved")}</p> : null}
        <div className="span-all">
          <button type="submit" className="btn btn-primary" data-mutation disabled={disabled || busy}>{t("save")}</button>
        </div>
      </form>
      {children}
    </section>
  );
}

function ApplyRetention({ disabled, onDone }: { disabled: boolean; onDone: () => void }) {
  const { t } = useT();
  const [confirming, setConfirming] = useState(false);
  const [result, setResult] = useState<Schemas["RetentionResult"] | null>(null);
  const { run, busy, problem } = useCommand();
  return (
    <div className="action-form">
      <p className="muted">{t("applyRetentionHint")}</p>
      {confirming ? (
        <span className="confirm-inline">
          <button type="button" className="btn btn-danger" data-mutation disabled={disabled || busy}
            onClick={() => run((key) => api.applyRetention(key), (r) => { setResult(r); setConfirming(false); onDone(); })}>
            {t("confirm")}
          </button>
          <button type="button" className="btn btn-quiet" onClick={() => setConfirming(false)}>{t("cancel")}</button>
        </span>
      ) : (
        <span><button type="button" className="btn btn-secondary" onClick={() => setConfirming(true)}>{t("applyRetention")}</button></span>
      )}
      {result ? (
        <p role="status" className="muted">
          {t("applied")}: {(Object.keys(result) as (keyof typeof result)[]).map((k) => `${t(`ret_${k}` as StringKey)} ${result[k]}`).join(" · ")}
        </p>
      ) : null}
      {problem ? <p className="form-error" role="alert">{problem}</p> : null}
    </div>
  );
}

function Templates({ config, disabled, onDone }: { config: Config; disabled: boolean; onDone: () => void }) {
  const { t } = useT();
  const keys = Object.keys(config.catalogue).sort();
  const [selected, setSelected] = useState(keys[0] ?? "");
  const current = config.template_overrides[selected] ?? config.catalogue[selected];
  const [draft, setDraft] = useState({ ar: current?.ar ?? "", en: current?.en ?? "" });
  const { run, busy, problem, done } = useCommand();
  const pick = (key: string) => {
    setSelected(key);
    const copy = config.template_overrides[key] ?? config.catalogue[key];
    setDraft({ ar: copy.ar, en: copy.en });
  };
  const customised = selected in config.template_overrides;
  return (
    <section className="card" aria-labelledby="tpl-h">
      <h2 id="tpl-h"><Icon name="message" /> {t("templates")}</h2>
      <p className="muted">{t("templatesHint")}</p>
      <form className="form-grid wording" noValidate onSubmit={(e) => {
        e.preventDefault();
        void run((key) => api.saveTemplates({ [selected]: { ar: draft.ar, en: draft.en } }, key), onDone);
      }}>
        <label className="field span-all"><span>{t("chooseTemplate")}</span>
          <select value={selected} dir="ltr" onChange={(e) => pick(e.target.value)}>
            {keys.map((k) => <option key={k} value={k}>{k}{k in config.template_overrides ? " •" : ""}</option>)}
          </select></label>
        {customised ? <span className="span-all"><StatusPill tone="info" icon="check" label={t("customised")} /></span> : null}
        <label className="field"><span>{t("arabic")}</span>
          <textarea dir="rtl" lang="ar" rows={5} maxLength={1000} value={draft.ar}
            onChange={(e) => setDraft((d) => ({ ...d, ar: e.target.value }))} /></label>
        <label className="field"><span>{t("english")}</span>
          <textarea dir="ltr" lang="en" rows={5} maxLength={1000} value={draft.en}
            onChange={(e) => setDraft((d) => ({ ...d, en: e.target.value }))} /></label>
        {problem ? <p className="form-error span-all" role="alert">{problem}</p> : null}
        {done && !problem ? <p className="muted span-all" role="status">{t("saved")}</p> : null}
        <div className="span-all row-actions start">
          <button type="submit" className="btn btn-primary" data-mutation disabled={disabled || busy}>{t("save")}</button>
          {customised ? (
            <button type="button" className="btn btn-quiet" data-mutation disabled={disabled || busy}
              onClick={() => run((key) => api.saveTemplates({ [selected]: null }, key), () => {
                setDraft({ ar: config.catalogue[selected].ar, en: config.catalogue[selected].en }); onDone();
              })}>
              {t("resetWording")}
            </button>
          ) : null}
        </div>
      </form>
    </section>
  );
}

export function Settings() {
  const { t } = useT();
  const poll = usePoll(api.config, 60_000, []);
  return (
    <main className="page">
      <h1>{t("settingsTitle")}</h1>
      <StaleBanner show={poll.stale} />
      <PageData poll={poll}>
        {(c) => (
          <>
            <NumberGroup title="timings" prefix="timing" values={c.timings} disabled={poll.stale}
              save={(v, key) => api.saveTimings(v, key).then(poll.refresh)} />
            <NumberGroup title="retention" hint="retentionHint" prefix="ret" values={c.retention_days} disabled={poll.stale}
              extra={(k) => `${t("eligible")}: ${c.retention_preview[k as keyof typeof c.retention_preview]?.eligible ?? 0}`}
              save={(v, key) => api.saveRetention(v, key).then(poll.refresh)}>
              <ApplyRetention disabled={poll.stale} onDone={poll.refresh} />
            </NumberGroup>
            <Templates config={c} disabled={poll.stale} onDone={poll.refresh} />
          </>
        )}
      </PageData>
    </main>
  );
}
