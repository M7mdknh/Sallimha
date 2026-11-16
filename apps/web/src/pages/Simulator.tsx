import { type FormEvent, useEffect, useRef, useState } from "react";

import { ApiError, api } from "../api/client";
import { Icon } from "../components/Icon";
import { Empty, Id, LoadFailed } from "../components/States";
import { useT } from "../strings";
import { usePoll } from "../usePoll";

// Development-only WhatsApp simulator. Messages go through the real webhook signature check, inbox and
// worker, but nothing reaches a real phone. Everything on this page is SIMULATED.
/** SIMULATED provider outage: every outgoing message fails and incoming messages stop until it is switched off. */
function SimOutageSwitch() {
  const { t } = useT();
  const state = usePoll(api.simOutage, 5_000, []);
  const down = state.data?.down ?? false;
  return (
    <div className={`sim-outage ${down ? "is-down" : ""}`} role="status">
      <span>{down ? t("simOutageOn") : t("simOutageOff")}</span>
      <button type="button" className={`btn ${down ? "btn-primary" : "btn-secondary"}`}
        onClick={async () => { await api.setSimOutage(!down).catch(() => undefined); void state.refresh(); }}>
        {down ? t("simOutageEnd") : t("simOutageStart")}
      </button>
    </div>
  );
}

export function Simulator() {
  const { t, error } = useT();
  const phones = usePoll(api.simPhones, 3_000, []);
  const [phone, setPhone] = useState("");
  const [extra, setExtra] = useState("");
  const [text, setText] = useState("");
  const [problem, setProblem] = useState("");
  const thread = usePoll(() => (phone ? api.simMessages(phone) : Promise.resolve([])), 1_500, [phone]);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [thread.data?.length]);

  async function send(body: Parameters<typeof api.simSend>[0]): Promise<boolean> {
    setProblem("");
    try {
      await api.simSend(body);
      await thread.refresh();
      return true;
    } catch (err) {
      setProblem(error(err instanceof ApiError ? err.code : "generic"));
      return false;
    }
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    const value = text;
    if (!value.trim() || !phone) return;
    setText(""); // clear what was sent now, so a reply arriving later never erases newer typing
    const ok = await send({ phone, text: value });
    if (!ok) setText(value);
  }

  if (phones.error && phones.data === null) {
    return <main className="page"><LoadFailed onRetry={phones.refresh} /></main>;
  }
  const list = [...(phones.data ?? [])];
  if (extra && !list.some((p) => p.phone === extra)) list.push({ phone: extra, label: t("simAddGuest"), role: "GUEST" });

  return (
    <main className="page sim">
      <h1>{t("simulator")}</h1>
      <p className="sim-banner" role="note"><Icon name="shield" /> {t("simLabel")}</p>
      <SimOutageSwitch />
      <div className="sim-grid">
        <section className="card" aria-labelledby="phones-h">
          <h2 id="phones-h">{t("simPhones")}</h2>
          <ul className="rows">
            {list.map((p) => (
              <li key={p.phone}>
                <button type="button" className="row row-button" aria-current={phone === p.phone ? "true" : undefined}
                  onClick={() => setPhone(p.phone)}>
                  <span className="row-title">{p.label}</span>
                  <span className="row-meta"><Id>{p.phone}</Id></span>
                </button>
              </li>
            ))}
          </ul>
          <form className="inline-form" onSubmit={(e) => { e.preventDefault(); if (/^\+\d{8,15}$/.test(extra)) setPhone(extra); }}>
            <label className="field">
              <span>{t("simAddGuest")}</span>
              <input dir="ltr" inputMode="tel" value={extra} onChange={(e) => setExtra(e.target.value.trim())} placeholder="+9665…" />
            </label>
            <button type="submit" className="btn btn-secondary">{t("simOpen")}</button>
          </form>
        </section>
        <section className="card chat" aria-labelledby="chat-h">
          <h2 id="chat-h">{phone ? <Id>{phone}</Id> : t("simPickPhone")}</h2>
          <div className="chat-log" role="log" aria-live="polite" ref={logRef}>
            {phone && (thread.data ?? []).length === 0 ? <Empty text={t("simEmpty")} /> : null}
            {(thread.data ?? []).map((m) => (
              <div key={m.id} className={`bubble bubble-${m.direction}`}>
                <p>{m.body}</p>
                {m.buttons.length ? (
                  <div className="bubble-buttons">
                    {m.buttons.map(([payload, title]) => (
                      <button key={payload} type="button" className="btn btn-secondary"
                        onClick={() => send({ phone, button_payload: payload, button_title: title, context_id: m.provider_message_id || undefined })}>
                        {title}
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
          {problem ? <p className="form-error" role="alert">{problem}</p> : null}
          <form className="composer" onSubmit={submit}>
            <label className="field grow">
              <span className="visually-hidden">{t("simMessage")}</span>
              <input aria-label={t("simMessage")} value={text} onChange={(e) => setText(e.target.value)} disabled={!phone} />
            </label>
            <button type="button" className="btn btn-secondary" disabled={!phone} onClick={() => send({ phone, photo: true })}>
              <Icon name="camera" /> {t("simPhoto")}
            </button>
            <button type="submit" className="btn btn-primary" disabled={!phone}>
              <Icon name="send" /> {t("simSend")}
            </button>
          </form>
        </section>
      </div>
    </main>
  );
}
