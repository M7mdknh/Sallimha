import { type FormEvent, useRef, useState } from "react";

import { ApiError, api, newKey, type ValetTask, type ValetWork } from "../api/client";
import { Icon } from "../components/Icon";
import { Id } from "../components/States";
import { navigate } from "../router";
import { useT } from "../strings";
import { clearDraft, readDraft, saveDraft, type Draft } from "./draft";
import { preparePhoto } from "./photo";
import { LocationForm } from "./TaskCard";
import { useAction } from "./useAction";

const STEPS = 6;
const SERVER_STEP: Record<string, number> = { photos: 3, receipt: 4, start_parking: 5, park: 6 };

function Progress({ step }: { step: number }) {
  const { t } = useT();
  return (
    <div className="progress" aria-label={`${step} ${t("stepOf")} ${STEPS}`}>
      <span className="progress-text"><Id>{step}</Id> {t("stepOf")} <Id>{STEPS}</Id></span>
      <ol className="progress-bar" aria-hidden="true">
        {Array.from({ length: STEPS }, (_, i) => <li key={i} className={i < step ? "is-done" : ""} />)}
      </ol>
    </div>
  );
}

/** Steps 1–2: entered on this device, sent to the server together once the valet confirms the number. */
function DetailsStep({ onNext }: { onNext: (d: Draft) => void }) {
  const { t, verror } = useT();
  const [d, setD] = useState<Draft>(readDraft);
  const [problem, setProblem] = useState("");
  const set = (patch: Partial<Draft>) => setD((prev) => { const next = { ...prev, ...patch }; saveDraft(next); return next; });
  function submit(e: FormEvent) {
    e.preventDefault();
    const digits = d.phone.replace(/[^\d+٠-٩]/g, "");
    if (digits.replace(/\D/g, "").length < 9 && !/[٠-٩]{9,}/.test(digits)) return setProblem(verror("phone_invalid"));
    if (d.vehicle.trim().length < 2) return setProblem(verror("vehicle_unidentified"));
    setProblem("");
    onNext(d);
  }
  return (
    <form className="task-form" onSubmit={submit} noValidate>
      <label className="field"><span>{t("customerPhone")}</span>
        <input dir="ltr" type="tel" inputMode="tel" autoComplete="off" value={d.phone} placeholder="05x xxx xxxx"
          onChange={(e) => set({ phone: e.target.value })} enterKeyHint="next" /></label>
      <label className="field"><span>{t("vehicleField")}</span>
        <input value={d.vehicle} autoComplete="off" maxLength={200} onChange={(e) => set({ vehicle: e.target.value })}
          enterKeyHint="next" aria-describedby="vehicle-hint" />
        <small id="vehicle-hint" className="muted">{t("vehicleHint")}</small></label>
      <fieldset className="choices choices-inline">
        <legend>{t("messageLanguage")}</legend>
        {(["ar", "en"] as const).map((l) => (
          <label key={l} className={`choice ${d.language === l ? "is-on" : ""}`} lang={l}>
            <input type="radio" name="lang" checked={d.language === l} onChange={() => set({ language: l })} />
            <span>{l === "ar" ? t("langAr") : t("langEn")}</span>
          </label>
        ))}
      </fieldset>
      {problem ? <p className="form-error" role="alert">{problem}</p> : null}
      <button type="submit" className="btn btn-primary btn-big"><Icon name="chevron" /> {t("next")}</button>
    </form>
  );
}

function ConfirmStep({ draft, onBack, onSent }: { draft: Draft; onBack: () => void; onSent: () => Promise<void> }) {
  const { t } = useT();
  const { run, busy, problem } = useAction(onSent);
  return (
    <div className="task-form">
      <p className="task-say"><Icon name="user" /> {t("confirmNumber")}</p>
      <p className="phone-confirm"><Id>{draft.phone.trim()}</Id></p>
      <p className="task-vehicle">{draft.vehicle.trim()}</p>
      {problem ? <p className="form-error" role="alert">{problem}</p> : null}
      <button type="button" className="btn btn-primary btn-big" disabled={busy !== null}
        onClick={() => run(`intake:${draft.phone}:${draft.vehicle}:${draft.language}`,
          (key) => api.valet.intake({ guest_phone: draft.phone.trim(), vehicle: draft.vehicle.trim(),
            language: draft.language }, key),
          () => clearDraft())}>
        <Icon name="send" /> {busy ? t("sending") : t("sendTicket")}
      </button>
      <button type="button" className="btn btn-secondary" onClick={onBack} disabled={busy !== null}>{t("editNumber")}</button>
    </div>
  );
}

type Upload = { id: string; url: string; status: "uploading" | "done" | "failed"; file: File; key: string };

/** Each photo is uploaded on its own with its own key; a photo counts only once the server has stored it. */
function PhotosStep({ task, refresh }: { task: ValetTask; refresh: () => Promise<void> }) {
  const { t, verror } = useT();
  const [uploads, setUploads] = useState<Upload[]>([]);
  const [problem, setProblem] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const stored = task.ticket.photos;
  const required = task.ticket.photos_required;

  async function send(u: Upload) {
    setUploads((all) => all.map((x) => (x.id === u.id ? { ...x, status: "uploading" } : x)));
    try {
      await api.valet.photo(task.ticket.id, await preparePhoto(u.file), u.key);
      setUploads((all) => all.map((x) => (x.id === u.id ? { ...x, status: "done" } : x)));
      setProblem("");
      await refresh();
    } catch (err) {
      setUploads((all) => all.map((x) => (x.id === u.id ? { ...x, status: "failed" } : x)));
      setProblem(err instanceof ApiError && err.status !== 0 ? verror(err.code) : t("photoFailed"));
    }
  }
  async function picked(files: FileList | null) {
    const list = Array.from(files ?? []);
    if (input.current) input.current.value = "";
    for (const file of list) {
      const u: Upload = { id: newKey(), url: URL.createObjectURL(file), status: "uploading", file, key: newKey() };
      setUploads((all) => [...all, u]);
      await send(u); // one at a time: the counter always matches what the server holds
    }
  }
  return (
    <div className="task-form">
      <p className="task-say"><Icon name="camera" /> {t("photosTitle")}</p>
      <p className="muted">{t("photosHint")}</p>
      <p className="photo-count" aria-live="polite"><Id>{Math.min(stored, required)}</Id> / <Id>{required}</Id></p>
      <ul className="thumbs">
        {uploads.map((u) => (
          <li key={u.id} className={`thumb is-${u.status}`}>
            <img src={u.url} alt="" />
            {u.status === "uploading" ? <span className="thumb-state">{t("uploading")}</span> : null}
            {u.status === "failed" ? (
              <button type="button" className="thumb-state" onClick={() => void send(u)}>
                <Icon name="refresh" size={16} /> {t("retry")}
              </button>
            ) : null}
            {u.status === "done" ? <span className="thumb-ok"><Icon name="check" size={16} /></span> : null}
          </li>
        ))}
      </ul>
      {problem ? <p className="form-error" role="alert">{problem}</p> : null}
      <label className="btn btn-primary btn-big file-button">
        <Icon name="camera" /> {t("takePhoto")}
        <input ref={input} type="file" accept="image/*" capture="environment" multiple
          onChange={(e) => void picked(e.target.files)} />
      </label>
    </div>
  );
}

function ReceiptStep({ task, refresh }: { task: ValetTask; refresh: () => Promise<void> }) {
  const { t } = useT();
  const { run, busy, problem } = useAction(refresh);
  return (
    <div className="task-form">
      <p className="task-say"><Icon name="message" /> {t("receiptTitle")}</p>
      {task.ticket.phone_masked ? <p className="muted"><Id>{task.ticket.phone_masked}</Id></p> : null}
      {problem ? <p className="form-error" role="alert">{problem}</p> : null}
      <button type="button" className="btn btn-primary btn-big" disabled={busy !== null}
        onClick={() => run("receipt-yes", (key) => api.valet.receipt(task.ticket.id, true, key))}>
        <Icon name="check" /> {t("receiptYes")}
      </button>
      <button type="button" className="btn btn-secondary" disabled={busy !== null}
        onClick={() => run("receipt-no", (key) => api.valet.receipt(task.ticket.id, false, key))}>
        {t("receiptNo")}
      </button>
      <p className="muted">{t("receiptNoHint")}</p>
    </div>
  );
}

function StartParkingStep({ task, refresh }: { task: ValetTask; refresh: () => Promise<void> }) {
  const { t } = useT();
  const { run, busy, problem } = useAction(refresh);
  return (
    <div className="task-form">
      <p className="task-say"><Icon name="car" /> {t("startParkingTitle")}</p>
      <p className="muted">{t("startParkingHint")}</p>
      {problem ? <p className="form-error" role="alert">{problem}</p> : null}
      <button type="button" className="btn btn-primary btn-big" disabled={busy !== null}
        onClick={() => run("start-parking", (key) => api.valet.startParking(task.ticket.id, key))}>
        <Icon name="car" /> {t("startParking")}
      </button>
    </div>
  );
}

function ParkStep({ task, work, refresh, onParked }: { task: ValetTask; work: ValetWork;
  refresh: () => Promise<void>; onParked: (ticket: string) => void }) {
  const { t } = useT();
  const { run, busy, problem } = useAction(refresh);
  return (
    <>
      <p className="task-say"><Icon name="pin" /> {t("parkTitle")}</p>
      {problem ? <p className="form-error" role="alert">{problem}</p> : null}
      <LocationForm work={work} submitLabel={t("confirmParked")} busy={busy !== null}
        onSubmit={(body) => run(`park:${JSON.stringify(body)}`, (key) => api.valet.park(task.ticket.id, body, key),
          () => onParked(task.ticket.number))} />
    </>
  );
}

/** Register car: a short guided flow. Steps 1–2 live on this screen; from step 3 the server's record decides the
 *  step, so a reload, a second tab or a supervisor's intervention always resumes at the right place. */
export function Register({ work, refresh }: { work: ValetWork; refresh: () => Promise<void> }) {
  const { t } = useT();
  const [local, setLocal] = useState<"details" | "confirm">("details");
  const [draft, setDraft] = useState<Draft>(readDraft);
  const [parked, setParked] = useState<string | null>(null);
  const task = work.task;

  if (parked) {
    return (
      <main className="valet-page">
        <section className="card task-card is-done" data-testid="parked-done">
          <p className="done-mark"><Icon name="check" size={32} /></p>
          <h2>{t("parkedDone")} <Id>{parked}</Id></h2>
          <button type="button" className="btn btn-primary btn-big" onClick={() => navigate("/work")}>{t("navMyWork")}</button>
          <button type="button" className="btn btn-secondary" onClick={() => { setParked(null); setLocal("details"); }}>
            {t("registerCar")}
          </button>
        </section>
      </main>
    );
  }
  if (task && task.type !== "INTAKE") {
    return (
      <main className="valet-page">
        <section className="state-block"><Icon name="alert" /><p>{t("finishTaskFirst")}</p>
          <button type="button" className="btn btn-primary" onClick={() => navigate("/work")}>{t("navMyWork")}</button>
        </section>
      </main>
    );
  }
  if (!task && !work.shift) return <main className="valet-page"><p className="state-block">{t("noShiftBody")}</p></main>;

  const step = task ? (task.step === "custody_ack" ? 3 : SERVER_STEP[task.step] ?? 3) : local === "details" ? 1 : 2;
  return (
    <main className="valet-page">
      <section className="card task-card flow" aria-labelledby="reg-h" data-testid="register" data-step={task?.step ?? local}>
        <header className="task-head">
          <h2 id="reg-h">{t("registerCar")}</h2>
          {task ? <span className="ticket-no"><Id>{task.ticket.number}</Id></span> : null}
        </header>
        <Progress step={step} />
        {task ? <p className="task-vehicle">{task.ticket.vehicle}</p> : null}
        {task?.ticket.early_request ? <p className="notice notice-warning"><Icon name="clock" /> {t("earlyRequest")}</p> : null}
        {step >= 3 && task?.step === "photos" ? <p className="notice notice-success"><Icon name="send" /> {t("ticketSent")}</p> : null}

        {!task && local === "details" ? <DetailsStep onNext={(d) => { setDraft(d); setLocal("confirm"); }} /> : null}
        {!task && local === "confirm" ? (
          <ConfirmStep draft={draft} onBack={() => setLocal("details")} onSent={refresh} />
        ) : null}
        {task?.step === "photos" ? <PhotosStep task={task} refresh={refresh} /> : null}
        {task?.step === "receipt" ? <ReceiptStep task={task} refresh={refresh} /> : null}
        {task?.step === "start_parking" ? <StartParkingStep task={task} refresh={refresh} /> : null}
        {task?.step === "park" ? <ParkStep task={task} work={work} refresh={refresh} onParked={setParked} /> : null}
        {task?.step === "custody_ack" ? (
          <button type="button" className="btn btn-primary btn-big" onClick={() => navigate("/work")}>{t("navMyWork")}</button>
        ) : null}
        {task && task.ticket.state === "RECEIVED" && step < 6 ? <p className="muted small">{t("wrongCar")}</p> : null}
      </section>
    </main>
  );
}
