import { useEffect, useRef, useState } from "react";

import { api, type Me } from "../api/client";
import { Icon } from "../components/Icon";
import { LoadFailed, SkeletonRows } from "../components/States";
import { setLang } from "../i18n";
import { navigate, usePath } from "../router";
import { useT } from "../strings";
import { clearDraft } from "./draft";
import { MyWork } from "./MyWork";
import { Register } from "./Register";
import { chime, setSound, soundEnabled } from "./sound";
import { useWork } from "./useWork";

/** The valet's app: My work and Register car, a connection indicator that never hides a lost connection, and an
 *  optional alert sound for new offers. Phones get a bottom tab bar within thumb reach. */
export function ValetApp({ me }: { me: Me }) {
  const { t, lang } = useT();
  const path = usePath();
  const { work, error, connection, refresh, serverNow } = useWork();
  const [sound, setSoundState] = useState(soundEnabled);
  const lastOffer = useRef<number | null>(null);

  useEffect(() => {
    if (path !== "/work" && path !== "/register") navigate("/work", true);
  }, [path]);

  const offerId = work?.task?.step === "offer" ? work.task.id : null;
  useEffect(() => {
    if (offerId !== null && offerId !== lastOffer.current) chime();
    lastOffer.current = offerId;
  }, [offerId]);

  const tabs: [string, "navMyWork" | "navRegister", string][] = [["/work", "navMyWork", "check"], ["/register", "navRegister", "car"]];
  return (
    <div className="valet-app">
      <header className="valet-bar">
        <span className="brand">
          <img src="/brand/assets/mark-on-plum.svg" alt="" width={28} height={28} />
          <span className="brand-name">{me.name}</span>
        </span>
        <span className={`conn conn-${connection}`} role="status" data-testid="connection">
          <span className="conn-dot" aria-hidden="true" />{connection === "ok" ? t("connected") : t("disconnected")}
        </span>
        <details className="valet-menu">
          <summary aria-label={t("menu")}><Icon name="user" /></summary>
          <div className="valet-menu-panel">
            <button type="button" className="btn btn-quiet" aria-pressed={sound}
              onClick={() => { setSound(!sound); setSoundState(!sound); }}>
              {sound ? t("soundOn") : t("soundOff")}
            </button>
            <button type="button" className="btn btn-quiet" onClick={() => setLang(lang === "ar" ? "en" : "ar")}>
              {lang === "ar" ? "English" : "العربية"}
            </button>
            <button type="button" className="btn btn-quiet" onClick={async () => {
              clearDraft();
              await api.logout().catch(() => undefined);
              window.location.assign("/login");
            }}>
              <Icon name="logout" /> {t("signOut")}
            </button>
          </div>
        </details>
      </header>
      {connection === "offline" ? <p className="offline-banner" role="alert"><Icon name="wifiOff" /> {t("reconnecting")}</p> : null}
      {work === null ? (
        error ? <main className="valet-page"><LoadFailed onRetry={() => void refresh()} /></main>
          : <main className="valet-page"><SkeletonRows /></main>
      ) : path === "/register" ? (
        <Register work={work} refresh={refresh} />
      ) : (
        <MyWork work={work} refresh={refresh} serverNow={serverNow} />
      )}
      <nav className="tabbar" aria-label={t("mainNav")}>
        {tabs.map(([href, label, icon]) => (
          <a key={href} href={href} aria-current={path === href ? "page" : undefined}
            onClick={(e) => { e.preventDefault(); navigate(href); }}>
            <Icon name={icon} /> <span>{t(label)}</span>
            {href === "/work" && offerId !== null && path !== "/work" ? <span className="tab-badge" aria-label={t("offerRetrieval")} /> : null}
          </a>
        ))}
      </nav>
    </div>
  );
}
