import type { ReactNode } from "react";

import { api, atLeast, type Me } from "../api/client";
import { setLang } from "../i18n";
import { navigate, usePath } from "../router";
import { useT, type StringKey } from "../strings";
import { Icon } from "./Icon";

/** Links by role (AT-59). Hiding a link is a convenience only; every page's API refuses out-of-role reads. */
export function navLinks(me: Me, eventId?: number): [string, StringKey][] {
  const links: [string, StringKey][] = [eventId ? [`/events/${eventId}`, "live"] : ["/events", "events"]];
  if (eventId) links.push([`/events/${eventId}/incidents`, "navIncidents"]);
  if (atLeast(me, "MANAGER")) links.push(["/manage", "navEvents"], ["/staff", "navStaff"], ["/carryover", "navCarryover"]);
  if (atLeast(me, "ADMIN")) links.push(["/settings", "navSettings"], ["/operations", "navOperations"]);
  if (atLeast(me, "SUPER_ADMIN")) links.push(["/integrations", "navIntegrations"]);
  if (me.simulator) links.push(["/dev/simulator", "simulator"]);
  return links;
}

export function Shell({ me, eventId, children }: { me: Me; eventId?: number; children: ReactNode }) {
  const { t, lang } = useT();
  const path = usePath();
  const links = navLinks(me, eventId);
  // The most specific matching link is current, so /events/1/incidents does not also mark Live. An event
  // report belongs to Events (management), not to the live view.
  const matchPath = /^\/events\/\d+\/report/.test(path) ? "/manage" : path;
  const current = links.map(([href]) => href)
    .filter((href) => matchPath === href || matchPath.startsWith(`${href}/`))
    .sort((a, b) => b.length - a.length)[0];
  return (
    <div className="app">
      <header className={`topbar ${links.length > 4 ? "nav-row" : ""}`}>
        <a href="/" className="brand" onClick={(e) => { e.preventDefault(); navigate("/"); }}>
          <img src="/brand/assets/mark-on-plum.svg" alt="" width={32} height={32} />
          <span className="brand-name">{t("appName")}</span>
        </a>
        <nav className="nav" aria-label={t("mainNav")}>
          {links.map(([href, label]) => (
            <a key={href} href={href} className="nav-link" aria-current={href === current ? "page" : undefined}
              onClick={(e) => { e.preventDefault(); navigate(href); }}>
              {t(label)}
            </a>
          ))}
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
