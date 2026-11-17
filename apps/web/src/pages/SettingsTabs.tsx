import type { Me } from "../api/client";
import { Icon } from "../components/Icon";
import { navigate, usePath } from "../router";
import { useT, type StringKey } from "../strings";

/** Settings' sections. Everyday configuration first; delivery diagnostics, WhatsApp status and the development
 *  simulator are grouped under Advanced, away from ordinary staff screens (ADR-0011). */
export function SettingsTabs({ me }: { me: Me }) {
  const { t } = useT();
  const path = usePath();
  const tabs: [string, StringKey, string][] = [
    ["/settings/operation", "setOperation", "pin"], ["/settings", "setTimings", "clock"]];
  const advanced: [string, StringKey, string][] = [
    ["/settings/delivery", "setDelivery", "send"], ["/settings/whatsapp", "setIntegration", "message"]];
  if (me.simulator) advanced.push(["/dev/simulator", "setSimulator", "refresh"]);
  const link = ([href, label, icon]: [string, StringKey, string]) => (
    <a key={href} href={href} aria-current={path === href ? "page" : undefined}
      onClick={(e) => { e.preventDefault(); navigate(href); }}>
      <Icon name={icon} size={18} /> {t(label)}
    </a>
  );
  return (
    <nav className="subtabs" aria-label={t("navSettings")}>
      {tabs.map(link)}
      <span className="subtabs-sep" aria-hidden="true" />
      <span className="subtabs-label">{t("setAdvanced")}</span>
      {advanced.map(link)}
    </nav>
  );
}
