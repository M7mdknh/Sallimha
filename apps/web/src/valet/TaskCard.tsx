import { type FormEvent, useEffect, useRef, useState } from "react";

import { api, newKey, type ValetTask, type ValetWork } from "../api/client";
import { Icon } from "../components/Icon";
import { Id } from "../components/States";
import { navigate } from "../router";
import { useT } from "../strings";
import { useAction } from "./useAction";

type Refresh = () => Promise<void>;

/** Zone, spot and key hook as the valet reads them while walking: large, left-to-right identifiers. */
export function WhereBlock({ location, hook }: { location: string; hook: number | null }) {
  const { t } = useT();
  return (
    <dl className="where">
      <div><dt><Icon name="pin" size={18} /> {t("location")}</dt><dd><Id>{location || "—"}</Id></dd></div>
      <div><dt><Icon name="key" size={18} /> {t("key")}</dt><dd><Id>{hook ?? "—"}</Id></dd></div>
    </dl>
  );
}

function Countdown({ deadline, serverNow }: { deadline: string; serverNow: () => number }) {
  const { t } = useT();
  const [, tick] = useState(0);
  useEffect(() => {
    const timer = window.setInterval(() => tick((n) => n + 1), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const left = Math.max(0, Math.round((new Date(deadline).getTime() - serverNow()) / 1000));
  return (
    <p className="countdown" role="timer" aria-live="off">
      <Icon name="clock" size={18} /> {t("offerEndsIn")} <Id>{`${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`}</Id>
    </p>
  );
}

/** Zone as large choices (no typing), spot as short text, hook with the number keypad. */
export function LocationForm({ work, submitLabel, busy, onSubmit }: { work: ValetWork; submitLabel: string; busy: boolean;
  onSubmit: (body: { zone_code: string; detail: string; hook_number: number }) => void }) {
  const { t, verror } = useT();
  const zones = work.venue?.zones ?? [];
  const [zone, setZone] = useState(zones.length === 1 ? zones[0].code : "");
  const [spot, setSpot] = useState("");
  const [hook, setHook] = useState("");
  const [problem, setProblem] = useState("");
  const { lang } = useT();
  function submit(e: FormEvent) {
    e.preventDefault();
    const digits = hook.replace(/[٠-٩]/g, (d) => String("٠١٢٣٤٥٦٧٨٩".indexOf(d))).trim();
    if (!zone) return setProblem(verror("zone_invalid"));
    if (!/^\d+$/.test(digits) || Number(digits) < 1) return setProblem(verror("hook_invalid"));
    setProblem("");
    onSubmit({ zone_code: zone, detail: spot.trim(), hook_number: Number(digits) });
  }
  return (
    <form className="task-form" onSubmit={submit} noValidate>
      <fieldset className="choices">
        <legend>{t("zoneField")}</legend>
        {zones.map((z) => (
          <label key={z.code} className={`choice ${zone === z.code ? "is-on" : ""}`}>
            <input type="radio" name="zone" value={z.code} checked={zone === z.code} onChange={() => setZone(z.code)} />
            <span className="choice-code"><Id>{z.code}</Id></span>
            <span className="choice-label">{lang === "ar" ? z.label_ar : z.label_en}</span>
          </label>
        ))}
      </fieldset>
      <div className="pair">
        <label className="field"><span>{t("spotField")}</span>
          <input dir="ltr" value={spot} onChange={(e) => setSpot(e.target.value)} autoComplete="off" maxLength={80}
            enterKeyHint="next" /></label>
        <label className="field"><span>{t("hookField")}</span>
          <input dir="ltr" inputMode="numeric" pattern="[0-9]*" value={hook} onChange={(e) => setHook(e.target.value)}
            autoComplete="off" maxLength={4} enterKeyHint="done" /></label>
      </div>
      {problem ? <p className="form-error" role="alert">{problem}</p> : null}
      <button type="submit" className="btn btn-primary btn-big" disabled={busy}>
        <Icon name="check" /> {submitLabel}
      </button>
    </form>
  );
}

function CodeForm({ task, refresh }: { task: ValetTask; refresh: Refresh }) {
  const { t } = useT();
  const [code, setCode] = useState("");
  const [result, setResult] = useState<{ outcome: string; remaining: number } | null>(null);
  const { run, busy, problem } = useAction(refresh);
  const locked = task.code?.locked || result?.outcome === "locked";
  return (
    <form className="task-form" noValidate onSubmit={(e) => {
      e.preventDefault();
      const digits = code.replace(/[٠-٩]/g, (d) => String("٠١٢٣٤٥٦٧٨٩".indexOf(d))).replace(/\D/g, "");
      void run(`code:${digits}`, (key) => api.valet.code(task.id, digits, key), (r) => { setResult(r); setCode(""); });
    }}>
      <p className="task-say"><Icon name="message" /> {t("askCode")}</p>
      {locked ? <p className="notice notice-danger" role="alert"><Icon name="shield" /> {t("codeLocked")}</p> : (
        <>
          <label className="field"><span>{t("codeLabel")}</span>
            <input className="code-input" dir="ltr" inputMode="numeric" pattern="[0-9]*" autoComplete="one-time-code"
              maxLength={6} value={code} onChange={(e) => setCode(e.target.value)} /></label>
          {result?.outcome === "wrong" ? (
            <p className="form-error" role="alert">{t("codeWrong")} <Id>{result.remaining}</Id></p>
          ) : null}
          {problem ? <p className="form-error" role="alert">{problem}</p> : null}
          <button type="submit" className="btn btn-primary btn-big" disabled={busy !== null || code.trim().length < 6}>
            {t("verify")}
          </button>
        </>
      )}
      <p className="muted">{t("noCodeHint")}</p>
    </form>
  );
}

function OfferButtons({ task, refresh }: { task: ValetTask; refresh: Refresh }) {
  const { t } = useT();
  const { run, busy, problem } = useAction(refresh);
  return (
    <>
      {problem ? <p className="form-error" role="alert">{problem}</p> : null}
      <div className="offer-actions">
        <button type="button" className="btn btn-primary btn-big" disabled={busy !== null}
          onClick={() => run("accept", (key) => api.valet.accept(task.id, key))}>
          <Icon name="check" /> {t("accept")}
        </button>
        <button type="button" className="btn btn-secondary" disabled={busy !== null}
          onClick={() => run("decline", (key) => api.valet.decline(task.id, key))}>
          {t("decline")}
        </button>
      </div>
    </>
  );
}

function OneButton({ name, label, icon, fn, refresh, disabled = false }: { name: string; label: string; icon: string;
  fn: (key: string) => Promise<unknown>; refresh: Refresh; disabled?: boolean }) {
  const { run, busy, problem } = useAction(refresh);
  return (
    <>
      {problem ? <p className="form-error" role="alert">{problem}</p> : null}
      <button type="button" className="btn btn-primary btn-big" disabled={disabled || busy !== null}
        onClick={() => run(name, fn)}>
        <Icon name={icon} /> {label}
      </button>
    </>
  );
}

function Custody({ task, refresh }: { task: ValetTask; refresh: Refresh }) {
  const { t } = useT();
  const c = task.custody;
  return (
    <>
      <p className="task-say"><Icon name="key" /> {t("custodyTitle")}</p>
      {c ? (
        <dl className="facts">
          <div><dt>{t("custodyCar")}</dt><dd>{c.vehicle_location}</dd></div>
          <div><dt>{t("custodyKey")}</dt><dd>{c.key_location}</dd></div>
          {c.from_name ? <div><dt>{t("custodyFrom")}</dt><dd>{c.from_name}</dd></div> : null}
        </dl>
      ) : null}
      <OneButton name="ack" label={t("ackCustody")} icon="check" refresh={refresh}
        fn={(key) => api.valet.custodyAck(task.id, key)} />
    </>
  );
}

function MoveForm({ task, work, refresh }: { task: ValetTask; work: ValetWork; refresh: Refresh }) {
  const { t } = useT();
  const { run, busy, problem } = useAction(refresh);
  return (
    <>
      <p className="task-say"><Icon name="car" /> {t("moveNow")}</p>
      {problem ? <p className="form-error" role="alert">{problem}</p> : null}
      <LocationForm work={work} submitLabel={t("moved")} busy={busy !== null}
        onSubmit={(body) => run(`moved:${JSON.stringify(body)}`, (key) => api.valet.moved(task.id, body, key))} />
    </>
  );
}

/** Tells the server that a retrieval offer is on screen, which starts its response window once (ADR-0012). Only while
 *  the page is visible; if the acknowledgement is lost it is sent again after the next poll. Repeats (a refresh,
 *  another tab) never move the deadline, and the hard limit from the reservation applies whatever happens here. */
function useAcknowledgeOffer(task: ValetTask, refresh: Refresh) {
  const sending = useRef(false);
  const pending = task.type === "RETRIEVAL" && task.step === "offer" && !task.shown;
  useEffect(() => {
    if (!pending || sending.current || document.visibilityState !== "visible") return;
    sending.current = true;
    api.valet.offerShown(task.id, newKey())
      .then(() => refresh()) // the countdown now shows the response window, not the hard limit
      .catch(() => undefined) // accepted elsewhere, lapsed or offline: the next poll shows the real state
      .finally(() => { sending.current = false; });
  }, [pending, task, refresh]);
}

/** The one current task, shown as what to do next. Everything comes from the server's step for this task. */
export function TaskCard({ task, work, refresh, serverNow }: { task: ValetTask; work: ValetWork; refresh: Refresh;
  serverNow: () => number }) {
  const { t } = useT();
  useAcknowledgeOffer(task, refresh);
  const ticket = task.ticket;
  const isOffer = task.step === "offer";
  const title = task.type === "INTAKE" ? t("intakeInProgress")
    : isOffer ? (task.type === "RELOCATION" ? t("offerMove") : t("offerRetrieval"))
      : task.type === "RELOCATION" ? t("offerMove") : t("currentTask");
  return (
    <section className={`card task-card ${isOffer ? "is-offer" : ""}`} aria-labelledby="task-h" data-testid="task-card"
      data-step={task.step}>
      <header className="task-head">
        <h2 id="task-h">{title}</h2>
        <span className="ticket-no"><Id>{ticket.number}</Id></span>
      </header>
      <p className="task-vehicle">{ticket.vehicle}</p>
      {task.type !== "INTAKE" ? <WhereBlock location={ticket.location} hook={ticket.hook} /> : null}
      {task.reason ? <p className="muted">{t("moveReason")}: {task.reason}</p> : null}
      {ticket.early_request ? <p className="notice notice-warning"><Icon name="clock" /> {t("earlyRequest")}</p> : null}
      {ticket.handover_blocked ? (
        <p className="notice notice-danger" role="alert"><Icon name="shield" /> {t("handoverBlocked")}</p>
      ) : null}

      {isOffer && task.deadline ? <Countdown deadline={task.deadline} serverNow={serverNow} /> : null}
      {isOffer ? <OfferButtons task={task} refresh={refresh} /> : null}
      {task.step === "custody_ack" ? <Custody task={task} refresh={refresh} /> : null}
      {task.step === "bring" ? (
        <>
          <p className="task-say"><Icon name="car" /> {t("bringCar")}</p>
          <OneButton name="ready" label={t("carReady")} icon="check" refresh={refresh}
            fn={(key) => api.valet.ready(task.id, key)} />
        </>
      ) : null}
      {task.step === "code" ? <CodeForm task={task} refresh={refresh} /> : null}
      {task.step === "deliver" ? (
        <>
          <p className="notice notice-success"><Icon name="check" /> {t("codeOk")}</p>
          <OneButton name="deliver" label={t("delivered")} icon="check" refresh={refresh}
            disabled={ticket.handover_blocked} fn={(key) => api.valet.deliver(task.id, key)} />
        </>
      ) : null}
      {task.step === "move" ? <MoveForm task={task} work={work} refresh={refresh} /> : null}
      {task.type === "INTAKE" && task.step !== "custody_ack" ? (
        <button type="button" className="btn btn-primary btn-big" onClick={() => navigate("/register")}>
          <Icon name="chevron" /> {t("continueIntake")}
        </button>
      ) : null}
    </section>
  );
}
