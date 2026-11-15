# ADR-0006 — Valet WhatsApp interaction contract

- Status: **Accepted 2026-11-15** insofar as it implements the agreed workflow (user decision 3)
- Builds on: docs/01 §1–§6; docs/02; docs/03; docs/04 intake table; ADR-0005; `11_WhatsApp_Platform_Verification.md`

## Decision
Every valet message names the ticket display number and the single next action. Buttons carry an opaque single-use action reference (≤256 chars, verified server-side) bound to staff member, ticket/task, task generation and expiry. Free text is interpreted only within an explicit prompt context; a bare number is never guessed to be a phone, plate, hook or code. Every handler calls the same domain command as the console. Interactive messages use at most three reply buttons with titles ≤20 characters.

| Situation | Valet sees | Action | Command / effect |
|---|---|---|---|
| Shift activated by supervisor | “بدأت مناوبتك في {event}. هل أنت جاهز لاستقبال المهام؟” | [جاهز] [غير متاح] | `set_availability`; opens service window |
| Break / unavailable | — | “استراحة” or [استراحة] | Immediate if no live task; otherwise pending until custody is released (“ستبدأ استراحتك بعد إنهاء مهمتك الحالية”) |
| Back | — | [جاهز] | Available (shift permitting) |
| New car | “مركبة جديدة” | Intake per docs/04: phone → confirm → **receipt confirmation** → vehicle → 4 photos → **[بدء الركن]** → location → key hook → [تم الركن] | `register_vehicle`, `confirm_guest_phone`, `confirm_guest_receipt`, `record_vehicle`, `attach_intake_media`, `start_parking`, `record_location`, `complete_parking` |
| Retrieval offer | “مهمة إحضار — تذكرة {ticket}. {vehicle}. الموقع {location}، المفتاح {hook}. ينتهي العرض {time}.” | [قبول] [اعتذار] | `accept_task` (rechecks shift, permission, generation, expiry, state, holds) / `decline_task` → requeue |
| Accepted | “تم إسنادها إليك…” | [السيارة جاهزة] | `mark_ready` → guest gets code |
| Guest arrives | “اطلب من الضيف رمز الاستلام وأرسله هنا.” | Sends 6 digits | `verify_collection` (5 failed attempts → supervisor review) |
| Code verified | “الرمز صحيح لتذكرة {ticket} — {vehicle}. سلّم المركبة ثم اضغط «تم التسليم».” | [تم التسليم] | `complete_handover` |
| Stale/expired action | docs/04 stale message | — | No state change, no duplicate audit |
| Duplicate tap | Current outcome repeated | — | No second effect |
| Help | “مساعدة” | — | Current task summary + supervisor route |

Rules:
- Availability is derived: enabled + open shift on this event + preference AVAILABLE + no live task (intake, offer, accepted retrieval, relocation). Breaks never release custody.
- An accepted task is never automatically reassigned; transfer only via `transfer_custody` (location of car/key recorded, old action references revoked, receiving valet acknowledges).
- Offers never contain the collection code or the guest phone.

## Consequences
Each row is a command with integration tests (simulated transport) and a contract test against the verified webhook shapes. Copy may be refined during template submission without changing operations (AT-47).
