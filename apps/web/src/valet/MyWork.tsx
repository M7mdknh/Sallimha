import { api, type ValetWork } from "../api/client";
import { Icon } from "../components/Icon";
import { Id } from "../components/States";
import { navigate } from "../router";
import { useT, type StringKey } from "../strings";
import { venueHM } from "../venueTime";
import { TaskCard } from "./TaskCard";
import { useAction } from "./useAction";

function Availability({ work, refresh }: { work: ValetWork; refresh: () => Promise<void> }) {
  const { t } = useT();
  const shift = work.shift!;
  const { run, busy, problem } = useAction(refresh);
  const available = shift.availability === "available";
  return (
    <section className="card availability" aria-labelledby="avail-h">
      <h2 id="avail-h" className="visually-hidden">{t("availability")}</h2>
      <div className="segmented" role="group" aria-label={t("availability")}>
        <button type="button" aria-pressed={available} disabled={busy !== null}
          onClick={() => !available && run("available", (key) => api.valet.availability(true, key))}>
          <Icon name="check" size={18} /> {t("availableNow")}
        </button>
        <button type="button" aria-pressed={!available} disabled={busy !== null}
          onClick={() => available && run("break", (key) => api.valet.availability(false, key))}>
          <Icon name="clock" size={18} /> {t("onBreak")}
        </button>
      </div>
      {shift.availability === "break_pending" ? <p className="muted">{t("breakPending")}</p> : null}
      {shift.availability === "unavailable" ? <p className="muted">{t("unavailableHint")}</p> : null}
      {problem ? <p className="form-error" role="alert">{problem}</p> : null}
    </section>
  );
}

export function MyWork({ work, refresh, serverNow }: { work: ValetWork; refresh: () => Promise<void>;
  serverNow: () => number }) {
  const { t, lang } = useT();
  if (!work.shift && !work.task) {
    return (
      <main className="valet-page">
        <section className="state-block" data-testid="no-shift">
          <Icon name="clock" />
          <h2>{t("noShiftTitle")}</h2>
          <p className="muted">{t("noShiftBody")}</p>
          {work.assigned ? <p>{t("noShiftAssigned")} <strong>{work.assigned.event}</strong> — {work.assigned.venue}</p> : null}
          <button type="button" className="btn btn-secondary" onClick={() => void refresh()}>
            <Icon name="refresh" /> {t("retry")}
          </button>
        </section>
      </main>
    );
  }
  return (
    <main className="valet-page">
      {work.shift ? <p className="valet-event"><strong>{work.shift.event.name}</strong> · {work.shift.event.venue}</p> : null}
      {work.shift?.assisted ? <p className="notice notice-warning" role="status">{t("assistedNote")}</p> : null}
      {work.customer_messages === "delayed" ? (
        <p className="notice notice-warning" role="status"><Icon name="message" /> {t("customerDelayed")}</p>
      ) : null}
      {work.task ? (
        <TaskCard task={work.task} work={work} refresh={refresh} serverNow={serverNow} />
      ) : (
        <section className="card task-card is-idle" data-testid="task-card" data-step="none">
          <h2>{t("noTask")}</h2>
          <p className="muted">{t("noTaskHint")}</p>
          <button type="button" className="btn btn-primary btn-big" onClick={() => navigate("/register")}
            disabled={work.shift?.availability !== "available"}>
            <Icon name="car" /> {t("registerCar")}
          </button>
        </section>
      )}
      {work.shift ? <Availability work={work} refresh={refresh} /> : null}
      {work.recent.length ? (
        <section className="card" aria-labelledby="recent-h">
          <h2 id="recent-h">{t("recentWork")}</h2>
          <ul className="recent">
            {work.recent.map((r) => (
              <li key={`${r.type}-${r.ticket}-${r.at}`}>
                <Id>{r.ticket}</Id>
                <span>{t(`done_${r.type}` as StringKey)}</span>
                <span className="muted"><Id>{venueHM(r.at, lang)}</Id></span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </main>
  );
}
