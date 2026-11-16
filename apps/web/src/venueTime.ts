// Console times are the venue's wall-clock time (Venue.timezone; Saudi venues default to Asia/Riyadh), never the
// browser's. The zone of the event being worked is remembered when its live view or event list loads.
const KEY = "sallimha.tz";
export const DEFAULT_ZONE = "Asia/Riyadh";

export function currentZone(): string {
  try {
    return window.sessionStorage.getItem(KEY) || DEFAULT_ZONE;
  } catch {
    return DEFAULT_ZONE;
  }
}

export function rememberZone(zone: string | undefined) {
  try {
    if (zone) window.sessionStorage.setItem(KEY, zone);
  } catch {
    // storage unavailable: the default zone is used
  }
}

export const venueTime = (iso: string | number, lang: string, zone = currentZone()) =>
  new Date(iso).toLocaleString(lang === "ar" ? "ar-SA-u-nu-latn" : "en-GB",
    { timeZone: zone, dateStyle: "short", timeStyle: "short" });

export const venueClock = (iso: string | number, lang: string, zone = currentZone()) =>
  new Date(iso).toLocaleTimeString(lang === "ar" ? "ar-SA-u-nu-latn" : "en-GB", { timeZone: zone });
