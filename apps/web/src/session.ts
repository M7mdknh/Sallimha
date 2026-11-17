// The operation last opened in this tab, so Operations, Team and Dashboard stay on it. Session storage only (an id,
// no personal data); falls back to the single open operation when storage is unavailable.
const KEY = "sallimha.event";

export function lastEvent(): number | undefined {
  try {
    const value = window.sessionStorage.getItem(KEY);
    return value ? Number(value) : undefined;
  } catch {
    return undefined;
  }
}

export function rememberEvent(eventId: number) {
  try {
    window.sessionStorage.setItem(KEY, String(eventId));
  } catch {
    // storage unavailable
  }
}
