import { api, type Schemas } from "../api/client";
import { Icon } from "../components/Icon";
import { Empty, Id, PageData, StaleBanner } from "../components/States";
import { useT } from "../strings";
import { useCommand } from "../useCommand";
import { usePoll } from "../usePoll";
import { riyadhTime } from "./Incidents";

function Replay({ row, disabled, onDone }: { row: Schemas["DeadLetter"]; disabled: boolean; onDone: () => void }) {
  const { t } = useT();
  const { run, busy, problem } = useCommand();
  return (
    <span className="row-actions">
      <button type="button" className="btn btn-secondary" data-mutation disabled={disabled || busy}
        onClick={() => run((key) => api.replay(row.id, key), onDone)}>
        <Icon name="refresh" /> {t("replay")}
      </button>
      {problem ? <span className="form-error" role="alert">{problem}</span> : null}
    </span>
  );
}

/** Messages the worker gave up on (never delivered). Replay re-queues the same row once; a second replay is a no-op. */
export function Operations() {
  const { t, lang } = useT();
  const poll = usePoll(api.deadLetters, 15_000, []);
  return (
    <main className="page">
      <h1>{t("operationsTitle")}</h1>
      <StaleBanner show={poll.stale} />
      <section className="card" aria-labelledby="dead-h">
        <h2 id="dead-h"><Icon name="message" /> {t("deadLetters")}</h2>
        <PageData poll={poll}>
          {(rows) => rows.length === 0 ? <Empty text={t("deadLettersEmpty")} /> : (
            <ul className="rows">
              {rows.map((r) => (
                <li key={r.id} className="row" data-testid={`dead-${r.id}`}>
                  <span className="row-title"><Id>{r.kind}</Id> {r.ticket ? <Id>{r.ticket}</Id> : null}</span>
                  <span className="row-meta">{t("recipient")}: {r.recipient}</span>
                  <span className="row-meta">{t("failure")}: <Id>{r.failure_class || r.last_error || "—"}</Id></span>
                  <span className="row-meta"><Id>{riyadhTime(r.created_at, lang)}</Id></span>
                  <Replay row={r} disabled={poll.stale} onDone={poll.refresh} />
                </li>
              ))}
            </ul>
          )}
        </PageData>
      </section>
    </main>
  );
}
