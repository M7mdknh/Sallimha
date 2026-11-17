import type { ReactNode } from "react";

import { api, isAdmin, type Me } from "../api/client";
import { setLang } from "../i18n";
import { navigate, usePath } from "../router";
import { useT, type StringKey } from "../strings";
import { Icon } from "./Icon";

/** Links by role (AT-59, ADR-0011). Hiding a link is a convenience only; every page's API refuses out-of-role reads.
 *  Supervisors: Operations and Team. Admins add Dashboard and Settings. Valets use their own app (ValetApp). */
export function navLinks(me: Me, eventId?: number): [string, StringKey][] {
  const operations: [string, StringKey] = [eventId ? `/events/${eventId}` : "/operations", "navOps"];
  if (!isAdmin(me)) return [operations, ["/team", "navTeam"]];
  return [["/dashboard", "navDashboard"], operations, ["/team", "navTeam"], ["/settings", "navSettings"]];
}

/** Which top-level section a path belongs to, so sub-pages keep their section highlighted. */
function section(path: string, links: [string, StringKey][]): string | undefined {
  const find = (key: StringKey) => links.find(([, k]) => k === key)?.[0];
  if (/^\/events\/\d+\/report/.test(path)) return find("navDashboard");
  if (/^\/(events|operations|outages|carryover)/.test(path)) return find("navOps");
  if (path.startsWith("/settings") || path.startsWith("/dev/")) return find("navSettings");
  return links.map(([href]) => href).find((href) => path === href || path.startsWith(`${href}/`));
}

export function Shell({ me, eventId, children }: { me: Me; eventId?: number; children: ReactNode }) {
  const { t, lang } = useT();
  const path = usePath();
  const links = navLinks(me, eventId);
  const current = section(path, links);
  return (
    <div className="app">
      <header className="topbar">
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
