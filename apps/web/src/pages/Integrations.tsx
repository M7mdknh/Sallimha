import { api, type Me } from "../api/client";
import { PageData, StatusPill } from "../components/States";
import { useT } from "../strings";
import { usePoll } from "../usePoll";
import { SettingsTabs } from "./SettingsTabs";

/** Readiness flags only. Credential values are never sent to the browser and are never entered here. */
export function Integrations({ me }: { me: Me }) {
  const { t } = useT();
  const poll = usePoll(api.whatsapp, 30_000, []);
  const flag = (on: boolean) => (
    <StatusPill tone={on ? "success" : "warning"} icon={on ? "check" : "alert"} label={on ? t("isSet") : t("notSet")} />
  );
  return (
    <main className="page">
      <h1>{t("integrationsTitle")}</h1>
      <SettingsTabs me={me} />
      <PageData poll={poll}>
        {(w) => (
          <section className="card" aria-labelledby="wa-h">
            <h2 id="wa-h" className="visually-hidden">{t("integrationsTitle")}</h2>
            {w.status === "simulated" ? <p className="sim-banner">{t("simLabel")}</p> : null}
            <dl className="facts">
              <div><dt>{t("status")}</dt><dd>{t(`health_${w.status}` as never)}</dd></div>
              <div><dt>{t("transport")}</dt><dd><bdi dir="ltr">{w.transport}</bdi></dd></div>
              <div><dt>{t("senderReady")}</dt><dd>{flag(w.sender_ready)}</dd></div>
              <div><dt>{t("signatureSecret")}</dt><dd>{flag(w.signature_secret_set)}</dd></div>
              <div><dt>{t("verifyToken")}</dt><dd>{flag(w.webhook_verification_set)}</dd></div>
            </dl>
            <p className="muted">{t("integrationsHint")}</p>
          </section>
        )}
      </PageData>
    </main>
  );
}
