// The first stage's answers (customer number, plate, description, language) survive moving between screens but live
// only in memory: never written to the device, gone on reload or sign-out (ADR-0011).
import { EMPTY_PHONE, type PhoneValue } from "../components/PhoneField";
import { EMPTY_PLATE, type PlateValue } from "../components/PlateField";

export type Draft = { phone: PhoneValue; plate: PlateValue; description: string; language: "ar" | "en" };

const EMPTY: Draft = { phone: EMPTY_PHONE, plate: EMPTY_PLATE, description: "", language: "ar" };
let draft: Draft = { ...EMPTY };

export const readDraft = (): Draft => draft;
export const saveDraft = (next: Draft) => { draft = { ...next }; };
export const clearDraft = () => { draft = { ...EMPTY }; };
