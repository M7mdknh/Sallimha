import { useState } from "react";

import { api, type Schemas } from "../api/client";
import { Icon } from "../components/Icon";
import { Empty, Id, PageData, StaleBanner, StatusPill } from "../components/States";
import { useT } from "../strings";
import { useCommand } from "../useCommand";
import { usePoll } from "../usePoll";
import { venueTime } from "../venueTime";

function Replay({ row, disabled, onDone }: { row: Schemas["DeadLetter"]; disabled: boolean; onDone: () => void }) {
  const { t } = useT();
  const { run, busy, problem } = useCommand();
  // An unknown outcome may already have reached the recipient: resending is a deliberate, confirmed choice.
  const [confirming, setConfirming] = useState(false);
  const unknown = row.status === "DELIVERY_UNKNOWN";
  const send = () => run((key) => api.replay(row.id, key), onDone);
  return (
    <span className="row-actions">
      {unknown && confirming ? (
        <span className="confirm-inline" role="group" aria-label={t("replay")}>
          <span className="muted">{t("unknownConfirm")}</span>
          <button type="button" className="btn btn-danger" data-mutation disabled={disabled || busy} onClick={send}>
            {t("replayAnyway")}
          </button>
          <button type="button" className="btn btn-quiet" onClick={() => setConfirming(false)}>{t("cancel")}</button>
        </span>
      ) : (
        <button type="button" className="btn btn-secondary" data-mutation disabled={disabled || busy}
          onClick={() => (unknown ? setConfirming(true) : void send())}>
          <Icon name="refresh" /> {t("replay")}
        </button>
      )}
      {problem ? <span className="form-error" role="alert">{problem}</span> : null}
    </span>
  );
}

/** Messages needing an operator: never delivered (DEAD), or possibly delivered with the response lost
 *  (DELIVERY_UNKNOWN, never resent automatically). Replay re-queues the same row once. */
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
                  <StatusPill tone={r.status === "DEAD" ? "danger" : "warning"} icon="alert"
                    label={r.status === "DEAD" ? t("statusDead") : t("statusUnknown")} />
                  <span className="row-meta">{t("recipient")}: {r.recipient}</span>
                  <span className="row-meta">{t("failure")}: <Id>{r.failure_class || r.last_error || "—"}</Id></span>
                  <span className="row-meta"><Id>{venueTime(r.created_at, lang)}</Id></span>
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
