import { latinDigits } from "./PhoneField";
import { useT } from "../strings";

export type PlateKind = "SAUDI" | "OTHER" | "NONE";
export type PlateValue = { kind: PlateKind; letters: string; digits: string; text: string; reason: string };
export const EMPTY_PLATE: PlateValue = { kind: "SAUDI", letters: "", digits: "", text: "", reason: "" };

// The 17 Saudi plate letters (ADR-0013, verified). Used here only to show the plate as typed and to hint; the server
// decides. No conversion between scripts is shown: the letter positions of the two rows are not verified.
const ARABIC_LETTERS = "ابحدرسصطعقكلمنهوى";
const LATIN_LETTERS = "ABJDRSXTEGKLZNHUV";
const VARIANTS: Record<string, string> = { "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ي": "ى", "ھ": "ه" };

/** The letters as they would appear on the plate, in the order typed; null if not a Saudi plate entry (yet). */
export function plateLetters(raw: string): { script: "ar" | "en"; letters: string[]; unknown: boolean } | null {
  const clean = raw.replace(/[\s\-_.ـ]/g, "");
  if (!clean) return null;
  if (/[؀-ۿ]/.test(clean)) {
    const letters = [...clean].map((c) => VARIANTS[c] ?? c);
    return { script: "ar", letters, unknown: letters.some((c) => !ARABIC_LETTERS.includes(c)) };
  }
  const letters = [...clean.toUpperCase()];
  return { script: "en", letters, unknown: letters.some((c) => !LATIN_LETTERS.includes(c)) };
}

function PlatePreview({ value }: { value: PlateValue }) {
  const { t } = useT();
  const read = plateLetters(value.letters);
  const digits = latinDigits(value.digits).replace(/\D/g, "");
  if (!read && !digits) return null;
  return (
    <div className="plate-preview" aria-label={t("platePreview")} data-testid="plate-preview">
      <span className="plate-part plate-digits" dir="ltr">{digits || "—"}</span>
      <span className="plate-part plate-letters" dir={read?.script === "ar" ? "rtl" : "ltr"}
        lang={read?.script === "ar" ? "ar" : "en"}>
        {read ? read.letters.map((c, i) => <span key={i} className="plate-letter">{c === "ه" ? "هـ" : c}</span>) : "—"}
      </span>
    </div>
  );
}

/** How the car is identified: a Saudi plate (letters and digits kept apart), another plate as written on it, or no
 *  readable plate with a reason. The description (make, colour) is asked for separately. */
export function PlateField({ value, onChange, error }: { value: PlateValue; onChange: (v: PlateValue) => void;
  error?: string }) {
  const { t } = useT();
  const set = (patch: Partial<PlateValue>) => onChange({ ...value, ...patch });
  const read = plateLetters(value.letters);
  const hint = read?.unknown ? t("plateLetterHint") : read && read.letters.length !== 3 ? t("plateCountHint") : "";
  return (
    <fieldset className="plate-field">
      <legend>{t("plateLegend")}</legend>
      <div className="segmented" role="radiogroup" aria-label={t("plateLegend")}>
        {(["SAUDI", "OTHER", "NONE"] as PlateKind[]).map((k) => (
          <label key={k} className={`segment ${value.kind === k ? "is-on" : ""}`}>
            <input type="radio" name="plate-kind" checked={value.kind === k} onChange={() => set({ kind: k })} />
            {t(k === "SAUDI" ? "plateSaudi" : k === "OTHER" ? "plateOther" : "plateNone")}
          </label>
        ))}
      </div>
      {value.kind === "SAUDI" ? (
        <>
          <div className="plate-inputs">
            <label className="field"><span>{t("plateLetters")}</span>
              <input value={value.letters} onChange={(e) => set({ letters: e.target.value })} autoComplete="off"
                autoCapitalize="characters" spellCheck={false} maxLength={8} dir="auto" className="plate-input"
                enterKeyHint="next" aria-describedby="plate-letters-hint" /></label>
            <label className="field"><span>{t("plateDigits")}</span>
              <input value={value.digits} onChange={(e) => set({ digits: e.target.value })} autoComplete="off"
                inputMode="numeric" maxLength={6} dir="ltr" className="plate-input" enterKeyHint="next" /></label>
          </div>
          <small id="plate-letters-hint" className={hint ? "field-hint is-warning" : "field-hint muted"}>
            {hint || t("plateLettersHint")}
          </small>
          <PlatePreview value={value} />
        </>
      ) : null}
      {value.kind === "OTHER" ? (
        <label className="field"><span>{t("plateOtherText")}</span>
          <input value={value.text} onChange={(e) => set({ text: e.target.value })} autoComplete="off"
            autoCapitalize="characters" spellCheck={false} maxLength={40} dir="auto" enterKeyHint="next" /></label>
      ) : null}
      {value.kind === "NONE" ? (
        <label className="field"><span>{t("plateMissingReason")}</span>
          <input value={value.reason} onChange={(e) => set({ reason: e.target.value })} autoComplete="off"
            maxLength={200} enterKeyHint="next" placeholder={t("plateMissingExample")} /></label>
      ) : null}
      {error ? <p className="form-error" role="alert">{error}</p> : null}
    </fieldset>
  );
}

/** The request fields for the server's VehicleEntryFields. */
export function plateBody(plate: PlateValue, description: string) {
  return {
    plate_kind: plate.kind,
    plate_letters: plate.kind === "SAUDI" ? plate.letters : "",
    plate_digits: plate.kind === "SAUDI" ? plate.digits : "",
    plate_text: plate.kind === "OTHER" ? plate.text : "",
    plate_missing_reason: plate.kind === "NONE" ? plate.reason : "",
    vehicle_description: description.trim(),
  };
}
