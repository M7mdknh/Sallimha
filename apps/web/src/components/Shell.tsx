import type { ReactNode } from "react";

import { api, type Me } from "../api/client";
import { setLang } from "../i18n";
import { navigate, usePath } from "../router";
import { useT } from "../strings";
import { Icon } from "./Icon";

export function Shell({ me, eventId, children }: { me: Me; eventId?: number; children: ReactNode }) {
  const { t, lang } = useT();
  const path = usePath();
  const link = (href: string, label: string) => (
    <a
      href={href}
      className="nav-link"
      aria-current={path.startsWith(href) ? "page" : undefined}
      onClick={(e) => {
        e.preventDefault();
        navigate(href);
      }}
    >
      {label}
    </a>
  );
  return (
    <div className="app">
      <header className="topbar">
        <a href="/" className="brand" onClick={(e) => { e.preventDefault(); navigate("/"); }}>
          <img src="/brand/assets/mark-on-plum.svg" alt="" width={32} height={32} />
          <span className="brand-name">{t("appName")}</span>
        </a>
        <nav className="nav" aria-label={t("events")}>
          {eventId ? link(`/events/${eventId}`, t("live")) : link("/events", t("events"))}
          {link("/dev/simulator", t("simulator"))}
        </nav>
        <div className="topbar-end">
          <span className="who">{me.name}</span>
          <button type="button" className="btn btn-quiet on-dark" onClick={() => setLang(lang === "ar" ? "en" : "ar")}>
            {lang === "ar" ? "English" : "العربية"}
          </button>
          <button
            type="button"
            className="btn btn-quiet on-dark"
            onClick={async () => {
              await api.logout().catch(() => undefined);
              window.location.assign("/login");
            }}
          >
            <Icon name="logout" /> <span className="hide-narrow">{t("signOut")}</span>
          </button>
        </div>
      </header>
      {children}
    </div>
  );
}
