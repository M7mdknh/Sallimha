import { type FormEvent, useRef, useState } from "react";

import { ApiError, api, newKey, type ValetTask, type ValetWork } from "../api/client";
import { Icon } from "../components/Icon";
import { PhoneField, readablePhone } from "../components/PhoneField";
import { PlateField, plateBody } from "../components/PlateField";
import { Id } from "../components/States";
import { navigate } from "../router";
import { useT, type StringKey } from "../strings";
import { clearDraft, readDraft, saveDraft, type Draft } from "./draft";
import { LocationPicker } from "./Location";
import { preparePhoto } from "./photo";
import { useAction } from "./useAction";

const STAGES: StringKey[] = ["stageCustomer", "stagePhotos", "stagePark"];
const SERVER_STAGE: Record<string, number> = { photos: 2, start_parking: 2, park: 3, custody_ack: 2 };

function Stages({ stage }: { stage: number }) {
  const { t } = useT();
  return (
    <ol className="stages" aria-label={`${stage} ${t("stepOf")} ${STAGES.length}`}>
      {STAGES.map((key, i) => (
        <li key={key} className={i + 1 < stage ? "is-done" : i + 1 === stage ? "is-current" : ""}
          aria-current={i + 1 === stage ? "step" : undefined}>
          <span className="stage-n"><Id>{i + 1}</Id></span> <span className="stage-label">{t(key)}</span>
        </li>
      ))}
    </ol>
  );
}

const PHONE_CODES = /^phone_/;
const PLATE_CODES = /^(plate_|vehicle_unidentified|reason_required)/;
type Duplicate = { ticket: string; state: string; mine: boolean };

/** Stage 1: the customer's number and the car, then the ticket is sent at once. The number as it will be read sits
 *  beside the Send button, so the valet reads it back to the customer; nothing else asks for confirmation. */
function CustomerStage({ refresh }: { refresh: () => Promise<void> }) {
  const { t, verror, state } = useT();
  const [d, setD] = useState<Draft>(readDraft);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<{ phone?: string; plate?: string; other?: string }>({});
  const [duplicate, setDuplicate] = useState<Duplicate | null>(null);
  const phoneInput = useRef<HTMLDivElement>(null);
  // One key per exact request: a double tap repeats nothing; a corrected request is a new action.
  const sent = useRef<{ body: string; key: string } | null>(null);
  const set = (patch: Partial<Draft>) => setD((prev) => {
    const next = { ...prev, ...patch };
    saveDraft(next);
    return next;
  });
  const readable = readablePhone(d.phone);

  async function send(confirmDuplicate = false) {
    if (busy) return;
    const body = { guest_phone: d.phone.raw, guest_region: d.phone.region, language: d.language,
      ...plateBody(d.plate, d.description), confirm_duplicate: confirmDuplicate };
    const fingerprint = JSON.stringify(body);
    if (sent.current?.body !== fingerprint) sent.current = { body: fingerprint, key: newKey() };
    setBusy(true);
    setErrors({});
    try {
      await api.valet.intake(body, sent.current.key);
      sent.current = null;
      clearDraft();
      setDuplicate(null);
      await refresh();
    } catch (err) {
      const code = err instanceof ApiError ? err.code : "generic";
      if (code === "possible_duplicate" && err instanceof ApiError) {
        setDuplicate({ ticket: String(err.detail.ticket ?? ""), state: String(err.detail.ticket_state ?? ""),
          mine: Boolean(err.detail.mine) });
      } else if (PHONE_CODES.test(code)) setErrors({ phone: verror(code) });
      else if (PLATE_CODES.test(code)) setErrors({ plate: verror(code) });
      else setErrors({ other: verror(code) });
      if (err instanceof ApiError && err.status >= 400 && err.status < 500) sent.current = null;
    } finally {
      setBusy(false);
    }
  }
  function submit(e: FormEvent) {
    e.preventDefault();
    void send(false);
  }

  return (
    <form className="task-form" onSubmit={submit} noValidate data-stage="customer">
      <div ref={phoneInput}>
        <PhoneField value={d.phone} onChange={(phone) => set({ phone })} error={errors.phone} autoFocus />
      </div>
      <fieldset className="choices choices-inline">
        <legend>{t("messageLanguage")}</legend>
        {(["ar", "en"] as const).map((l) => (
          <label key={l} className={`choice ${d.language === l ? "is-on" : ""}`} lang={l}>
            <input type="radio" name="lang" checked={d.language === l} onChange={() => set({ language: l })} />
            <span>{l === "ar" ? t("langAr") : t("langEn")}</span>
          </label>
        ))}
      </fieldset>
      <PlateField value={d.plate} onChange={(plate) => set({ plate })} error={errors.plate} />
      <label className="field"><span>{t("vehicleDescription")}</span>
        <input value={d.description} onChange={(e) => set({ description: e.target.value })} autoComplete="off"
          maxLength={200} enterKeyHint="done" aria-describedby="desc-hint" />
        <small id="desc-hint" className="muted">{t("vehicleDescriptionHint")}</small></label>

      {duplicate ? (
        <div className="notice notice-warning duplicate" role="alert" data-testid="possible-duplicate">
          <p><strong>{t("duplicateTitle")}</strong> <Id>{duplicate.ticket}</Id> · {state(duplicate.state)}</p>
          <p>{duplicate.mine ? t("duplicateMine") : t("duplicateAsk")}</p>
          {duplicate.mine ? (
            <button type="button" className="btn btn-primary" onClick={() => navigate("/work")}>{t("navMyWork")}</button>
          ) : (
            <button type="button" className="btn btn-secondary" disabled={busy} onClick={() => void send(true)}>
              {t("duplicateAnyway")}
            </button>
          )}
        </div>
      ) : null}
      {errors.other ? <p className="form-error" role="alert">{errors.other}</p> : null}

      <div className="send-row">
        <p className="send-to" aria-live="polite">
          <span className="muted">{readable ? t("ticketGoesTo") : t("ticketGoesToNone")}</span>
          {readable ? <bdi dir="ltr" className="phone-confirm">{readable}</bdi> : null}
          {readable ? (
            <button type="button" className="btn btn-quiet"
              onClick={() => phoneInput.current?.querySelector("input")?.focus()}>{t("editPhone")}</button>
          ) : null}
        </p>
        <button type="submit" className="btn btn-primary btn-big" disabled={busy}>
          <Icon name="send" /> {busy ? t("sending") : t("sendTicket")}
        </button>
      </div>
    </form>
  );
}

type Upload = { id: string; url: string; status: "uploading" | "done" | "failed"; file: File; key: string };

/** Stage 2: four photos, then Start parking (the car may move only after this). The customer's ticket message is
 *  shown as the provider reports it; there is no question about it. */
function PhotosStage({ task, refresh }: { task: ValetTask; refresh: () => Promise<void> }) {
  const { t, verror } = useT();
  const [uploads, setUploads] = useState<Upload[]>([]);
  const [problem, setProblem] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const { run, busy, problem: startProblem } = useAction(refresh);
  const stored = task.ticket.photos;
  const required = task.ticket.photos_required;
  const ready = task.step === "start_parking";

  async function upload(u: Upload) {
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
      await upload(u); // one at a time: the counter always matches what the server holds
    }
  }
  return (
    <div className="task-form" data-stage="photos">
      <p className="task-say"><Icon name="camera" /> {t("photosTitle")} <span className="photo-count" aria-live="polite">
        <Id>{Math.min(stored, required)}</Id> / <Id>{required}</Id></span></p>
      {!ready ? <p className="muted">{t("photosHint")}</p> : null}
      {uploads.length ? (
        <ul className="thumbs">
          {uploads.map((u) => (
            <li key={u.id} className={`thumb is-${u.status}`}>
              <img src={u.url} alt="" />
              {u.status === "uploading" ? <span className="thumb-state">{t("uploading")}</span> : null}
              {u.status === "failed" ? (
                <button type="button" className="thumb-state" onClick={() => void upload(u)}>
                  <Icon name="refresh" size={16} /> {t("retry")}
                </button>
              ) : null}
              {u.status === "done" ? <span className="thumb-ok"><Icon name="check" size={16} /></span> : null}
            </li>
          ))}
        </ul>
      ) : null}
      {problem ? <p className="form-error" role="alert">{problem}</p> : null}
      {!ready ? (
        <label className="btn btn-primary btn-big file-button">
          <Icon name="camera" /> {t("takePhoto")}
          <input ref={input} type="file" accept="image/*" capture="environment" multiple
            onChange={(e) => void picked(e.target.files)} />
        </label>
      ) : (
        <>
          <p className="muted">{t("photosThenPark")}</p>
          {startProblem ? <p className="form-error" role="alert">{startProblem}</p> : null}
          <button type="button" className="btn btn-primary btn-big" disabled={busy !== null}
            onClick={() => run("start-parking", (key) => api.valet.startParking(task.ticket.id, key))}>
            <Icon name="car" /> {t("startParking")}
          </button>
        </>
      )}
    </div>
  );
}

function MessageLine({ task }: { task: ValetTask }) {
  const { t } = useT();
  const status = task.ticket.message;
  if (!status) return null;
  const tone = status === "failed" || status === "unknown" ? "warning" : status === "delivered" || status === "read"
    ? "success" : "neutral";
  return (
    <p className={`message-line is-${tone}`} data-testid="message-status" data-status={status}>
      <Icon name="message" size={16} /> {t("msgLabel")}: {t(`msg_${status}` as StringKey)}
    </p>
  );
}

/** Register car in three stages. Stage 1 lives on this screen; from stage 2 the server's record decides, so a reload,
 *  a second tab or a supervisor's intervention always resumes at the right place. */
export function Register({ work, refresh }: { work: ValetWork; refresh: () => Promise<void> }) {
  const { t } = useT();
  const [parked, setParked] = useState<string | null>(null);
  const { run, busy, problem } = useAction(refresh);
  const task = work.task;

  if (parked) {
    return (
      <main className="valet-page">
        <section className="card task-card is-done" data-testid="parked-done">
          <p className="done-mark"><Icon name="check" size={32} /></p>
          <h2>{t("parkedDone")} <Id>{parked}</Id></h2>
          <button type="button" className="btn btn-primary btn-big" onClick={() => navigate("/work")}>{t("navMyWork")}</button>
          <button type="button" className="btn btn-secondary" onClick={() => setParked(null)}>{t("registerCar")}</button>
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

  const stage = task ? SERVER_STAGE[task.step] ?? 2 : 1;
  return (
    <main className="valet-page">
      <section className="card task-card flow" aria-labelledby="reg-h" data-testid="register" data-step={task?.step ?? "customer"}>
        <header className="task-head">
          <h2 id="reg-h">{t("registerCar")}</h2>
          {task ? <span className="ticket-no"><Id>{task.ticket.number}</Id></span> : null}
        </header>
        <Stages stage={stage} />
        {task ? <p className="task-vehicle">{task.ticket.vehicle}</p> : null}
        {task ? <MessageLine task={task} /> : null}
        {task?.ticket.early_request ? <p className="notice notice-warning"><Icon name="clock" /> {t("earlyRequest")}</p> : null}

        {!task ? <CustomerStage refresh={refresh} /> : null}
        {task?.step === "photos" || task?.step === "start_parking" ? <PhotosStage task={task} refresh={refresh} /> : null}
        {task?.step === "park" ? (
          <>
            <p className="task-say"><Icon name="pin" /> {t("parkTitle")}</p>
            {problem ? <p className="form-error" role="alert">{problem}</p> : null}
            <LocationPicker work={work} submitLabel={t("confirmParked")} busy={busy !== null}
              onSubmit={(body) => run(`park:${JSON.stringify(body)}`, (key) => api.valet.park(task.ticket.id, body, key),
                () => setParked(task.ticket.number))} />
          </>
        ) : null}
        {task?.step === "custody_ack" ? (
          <button type="button" className="btn btn-primary btn-big" onClick={() => navigate("/work")}>{t("navMyWork")}</button>
        ) : null}
        {task && task.ticket.state === "RECEIVED" && stage < 3 ? <p className="muted small">{t("wrongCar")}</p> : null}
      </section>
    </main>
  );
}
