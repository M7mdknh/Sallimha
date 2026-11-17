// The first registration step's answers (customer number, vehicle, language) survive moving between screens but live
// only in memory: never written to the device, gone on reload or sign-out (ADR-0011).
export type Draft = { phone: string; vehicle: string; language: "ar" | "en" };

const EMPTY: Draft = { phone: "", vehicle: "", language: "ar" };
let draft: Draft = { ...EMPTY };

export const readDraft = (): Draft => draft;
export const saveDraft = (next: Draft) => { draft = { ...next }; };
export const clearDraft = () => { draft = { ...EMPTY }; };
