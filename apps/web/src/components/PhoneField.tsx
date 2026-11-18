import { useMemo } from "react";
import { AsYouType, type CountryCode, getCountries, getCountryCallingCode } from "libphonenumber-js/min";

import { useT } from "../strings";

export type PhoneValue = { raw: string; region: CountryCode };
export const EMPTY_PHONE: PhoneValue = { raw: "", region: "SA" };

const FIRST: CountryCode[] = ["SA", "AE", "KW", "BH", "QA", "OM", "EG", "JO"];
const ARABIC = "٠١٢٣٤٥٦٧٨٩";
const PERSIAN = "۰۱۲۳۴۵۶۷۸۹";

/** Arabic-Indic and Persian digits as Latin digits, for display only (the server normalises on its own). */
export const latinDigits = (text: string) =>
  text.replace(/[٠-٩۰-۹]/g, (d) => String(ARABIC.includes(d) ? ARABIC.indexOf(d) : PERSIAN.indexOf(d)));

/** The number as it will be read: formatted international form, or "" while it cannot be read yet. Never decides
 *  validity: the server does (ADR-0013). */
export function readablePhone(value: PhoneValue): string {
  const typed = latinDigits(value.raw).trim().replace(/^00/, "+");
  if (typed.replace(/\D/g, "").length < 6) return "";
  const formatter = new AsYouType(typed.startsWith("+") ? undefined : value.region);
  formatter.input(typed);
  const number = formatter.getNumber();
  return number ? number.formatInternational() : "";
}

function useCountries(lang: string) {
  return useMemo(() => {
    const names = new Intl.DisplayNames([lang === "ar" ? "ar" : "en"], { type: "region" });
    const rest = getCountries().filter((c) => !FIRST.includes(c))
      .sort((a, b) => (names.of(a) ?? a).localeCompare(names.of(b) ?? b, lang));
    return [...FIRST, ...rest].map((code) => ({ code, label: `${names.of(code) ?? code} +${getCountryCallingCode(code)}` }));
  }, [lang]);
}

/** Customer number: country (Saudi Arabia by default) and the number as the customer says it. Local or international
 *  forms, spaces, hyphens and Arabic digits are all accepted; what was typed is kept after an error. */
export function PhoneField({ value, onChange, error, id = "guest-phone", autoFocus }: { value: PhoneValue;
  onChange: (v: PhoneValue) => void; error?: string; id?: string; autoFocus?: boolean }) {
  const { t, lang } = useT();
  const countries = useCountries(lang);
  const readable = readablePhone(value);
  return (
    <div className="field phone-field">
      <label htmlFor={id}>{t("customerPhone")}</label>
      <div className="phone-row">
        <select aria-label={t("phoneCountry")} value={value.region}
          onChange={(e) => onChange({ ...value, region: e.target.value as CountryCode })}>
          {countries.map((c) => <option key={c.code} value={c.code}>{c.label}</option>)}
        </select>
        <input id={id} dir="ltr" type="tel" inputMode="tel" autoComplete="off" value={value.raw}
          placeholder={value.region === "SA" ? "05x xxx xxxx" : ""} autoFocus={autoFocus} enterKeyHint="next"
          aria-invalid={error ? true : undefined} aria-describedby={`${id}-read ${id}-err`}
          onChange={(e) => onChange({ ...value, raw: e.target.value })} />
      </div>
      <small id={`${id}-read`} className="phone-read" aria-live="polite">
        {readable ? <bdi dir="ltr">{readable}</bdi> : <span className="muted">{t("phoneHint")}</span>}
      </small>
      {error ? <p id={`${id}-err`} className="form-error" role="alert">{error}</p> : null}
    </div>
  );
}
