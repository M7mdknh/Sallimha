import { useSyncExternalStore } from "react";

export type Lang = "ar" | "en";

const STORAGE_KEY = "sallimha.lang";
let current: Lang = readInitial();
const listeners = new Set<() => void>();

function readInitial(): Lang {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "ar" || stored === "en") return stored;
  } catch {
    // storage unavailable: Arabic default
  }
  return "ar";
}

function apply(lang: Lang) {
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
}

export function setLang(lang: Lang) {
  current = lang;
  apply(lang);
  try {
    window.localStorage.setItem(STORAGE_KEY, lang);
  } catch {
    // ignore
  }
  listeners.forEach((l) => l());
}

export function useLang(): Lang {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => current,
  );
}

apply(current);
