# ADR-0005 — Specification gaps and conflict resolutions

- Status: **Proposed — awaiting user approval**
- Date: 2026-11-15
- Scope: items where the pack is silent, inconsistent, or would behave incorrectly if implemented literally. docs/01–07 are not edited. Each resolution below takes effect only once approved.

Legend: **Business** = needs the owner's decision because it changes behaviour; **Technical** = implementation clarification that preserves approved behaviour.

## C1 — Key-hook occupancy must survive event closure (Technical; refines a proposed default)
docs/02 scopes uniqueness to `(event_id, key_station_id, hook_number)`. Key stations are physical venue fixtures, and docs/01 §8 keeps unclaimed cars in a carryover register after the event closes. With the event in the key, hook 12 holding an UNCLAIMED car's key would appear free at the next event at the same venue.

Resolution: key stations belong to the venue. Occupancy is unique on `(key_station_id, hook_number)` while the occupancy row is unreleased, regardless of event. Carryover cases keep their occupancy until released. Test: AT-43.

## C2 — Retrieval request terminal states (Technical)
docs/02 describes supervisor withdrawal before acceptance and later re-request, but the lifecycle `WAITING_FOR_PARKING → QUEUED → OFFERED → ACCEPTED → COMPLETED` has no withdrawn state. It also does not say what happens to an early request when its ticket is cancelled.

Resolution: add terminal `WITHDRAWN` with actor, reason and time. Cancelling a ticket withdraws any open request in the same transaction with reason `ticket_cancelled` and notifies the guest truthfully. The one-open-request constraint excludes `COMPLETED` and `WITHDRAWN`. Test: AT-54.

## C3 — In-person receipt confirmation step (Technical)
docs/01 §2 requires staff to confirm at the counter that the guest received the correct ticket, stored separately from provider delivery (`CONFIRMED_IN_PERSON`). The docs/04 intake sequence has no step for it.

Resolution: after the ticket is sent, prompt the valet: “هل ظهرت التذكرة على جوال الضيف؟” with “نعم، استلمها” / “لم تصل”. Yes → `CONFIRMED_IN_PERSON`. No or no answer → `UNCONFIRMED`, a visible “Guest contact unconfirmed” exception and the documented correction path. Intake continues either way. The exception surfaces in the supervisor view without forcing intervention in normal intakes. Test: AT-35.

## C4 — When cancellation stops being allowed (**Business**)
`CANCELLED` means “no vehicle was taken into custody”. The point at which custody starts is not defined.

Proposed default: cancellation is allowed only while the ticket is `RECEIVED` and the intake photos step has not been completed or excepted, because docs/04 makes photos the last step before the car moves. After that, the only outcomes are `DELIVERED` or `UNCLAIMED`. Supervisors and above must give a reason. **Needs your confirmation**, or another cutoff such as “keys received”.

## C5 — Valet WhatsApp interactions after intake (Technical, with business-visible wording)
docs/04 specifies intake only. Shift readiness, breaks, offer accept/decline, “ready”, code entry and delivery confirmation are needed for Phase 1. See **ADR-0006** for the proposed contract. Phase 1 dispatch work cannot start until it is approved.

## C6 — Shift start vs. valet messaging (Technical)
docs/01 §1 says the supervisor activates shifts. docs/04 notes that a valet message opens a WhatsApp service window.

Resolution: the supervisor activates the shift (attendance) in the console. The system then invites the valet to tap “جاهز”, which sets their availability preference and opens a service window. A valet cannot start their own shift.

## C7 — How the collection code is sent (Technical; platform-dependent)
The READY message carries the code. Whether it can go as a session message depends on whether the guest's earlier button tap opened a service window. If a template is required, its category (utility vs. authentication) must be verified with Meta, because a code inside a template may be classified differently.

Resolution: verify in the Phase 0 WhatsApp spike (ADR-0002 §Platform facts). The adapter chooses a session or template message. Business behaviour is unchanged.

## C8 — WhatsApp media is not camera-original (Technical clarification)
WhatsApp recompresses images and generally strips capture metadata. “Original media” therefore means the file exactly as received from the provider, with its hash, and `capture_time` stays null unless supplied. This matches docs/01: upload time is never presented as capture time.

## C9 — Starter CSS font defect (Technical; brand implementation, not identity)
`brand/tokens.css` sets `body { font-family: var(--sl-font-en) }` and Arabic only on `[lang="ar"]`. With the usual `<html lang="ar">`, body text inherits Noto Sans, which has no Arabic glyphs, so Arabic falls back to a system font. This was confirmed in Chromium. The stacks also lack a cross-script fallback for mixed Arabic/English strings.

Resolution at UI build: stacks become `"Noto Sans Arabic", "Noto Sans", sans-serif` and `"Noto Sans", "Noto Sans Arabic", sans-serif`, and the language rule applies to `html[lang]`. Colours, fonts and assets are unchanged. tokens.css is updated together with DESIGN.md per its change rule.

## C10 — Brand document nits (no identity change)
- Line heights in the brand PDF are rounded to whole pixels: 32/44 and 16/26 versus DESIGN.md's 1.4 and 1.65. **DESIGN.md governs.**
- `tokens.json` lacks the type scale and tinted status backgrounds, although the sample console uses an amber tint. They will be added at UI build from DESIGN.md values, with each tint's contrast checked.
- `logo-en.svg`'s accessible label includes Arabic. Correct it to `Sallimha` at the next asset update.
- The bilingual lockup at its 220 px minimum renders the English name very small. Observation only; it is acceptable at the documented minimum.

## C11 — Gate 2 needs a minimal console (Technical sequencing)
docs/06 Gate 2 includes AT-34 (stale console banner). A minimal, brand-approved supervisor live view must therefore ship in Phase 1, after brand approval. The full console follows in Phase 2.

## C12 — Kickoff file
README and the approach PDF reference `Claude_Kickoff.md`, which is absent. Its content arrived as the session prompt. It will not be recreated unless you ask.

## Consequences
The data model gains `WITHDRAWN`, venue-scoped key stations and a receipt-confirmation prompt. ADR-0006 becomes a Phase 1 prerequisite. C4 is the only business decision.
