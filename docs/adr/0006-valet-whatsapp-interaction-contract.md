# ADR-0006 — Valet WhatsApp interaction contract (beyond intake)

- Status: **Proposed — awaiting user approval** (Phase 1 prerequisite)
- Date: 2026-11-15
- Builds on: docs/01 §1, §5, §6; docs/02 staff availability; docs/03; docs/04 intake table; ADR-0005 C3 and C6

## Context
Valets work through WhatsApp only. docs/04 defines the intake sequence; the other valet actions the approved flow requires are unspecified. All copy below is draft. Template and button formats are subject to the Phase 0 platform verification.

## Decision
Every valet message names the ticket display number and the single next action. Buttons carry an opaque, single-use action reference bound to the staff member, the task generation and an expiry. Free text is interpreted only inside an explicit prompt context; a bare number is never guessed to be a phone, plate, hook or code. Every handler calls the same domain command as the console.

| Situation | Valet sees | Valet action | Server command / effect |
|---|---|---|---|
| Supervisor activated shift | “بدأت مناوبتك في {event}. هل أنت جاهز لاستقبال المهام؟” | [جاهز] / [غير متاح] | Set availability preference. Opens service window. Dispatch may start |
| Wants a break | — | Send “استراحة” or tap [استراحة] in help menu | If no live task: unavailable now. If holding custody: “ستبدأ استراحتك بعد إنهاء مهمتك الحالية” and pending until release |
| Returns | — | [جاهز] | Available again (subject to shift) |
| New car | “مركبة جديدة” per docs/04 | Intake sequence, plus receipt-confirmation step (ADR-0005 C3) | `register_vehicle`, `confirm_guest_contact`, `attach_intake_media`, `complete_parking` |
| Retrieval offer | “مهمة إحضار — تذكرة {ticket}. {vehicle}. الموقع {location}، المفتاح {hook}. ينتهي العرض {time}.” | [قبول] / [اعتذار] | `accept_task` (rechecks everything) or decline → requeue (docs/03) |
| Accepted | “تم إسنادها إليك. أحضر المفتاح والمركبة، ثم اضغط «السيارة جاهزة» عند نقطة التسليم.” | [السيارة جاهزة] | `mark_ready`. Guest receives the code |
| Ready, guest arrives | “اطلب من الضيف رمز الاستلام وأرسله هنا.” | Sends 6 digits | `verify_collection`. Shows remaining attempts on failure; supervisor review after 5 failures |
| Code verified | “الرمز صحيح لتذكرة {ticket} — {vehicle}. سلّم المركبة ثم اضغط «تم التسليم».” | [تم التسليم] | `complete_handover`: closes the ticket, releases capacity, sends the rating request |
| Stale or superseded action | docs/04 stale message | — | No state change, no duplicate audit event |
| Lost or unsure | Send “مساعدة” | — | Shows current task summary and the supervisor contact route |

Rules:
- Offers never contain the collection code or the guest phone.
- “جاهز” cannot clear an assignment the valet holds. The busy state ends only through the task's own completion or an explicit custody transfer.
- The offer acceptance window starts when the provider accepts the send, within the 60 s hard reservation limit (docs/03).
- Staff language preference defaults to Arabic; English copy mirrors the same actions.

## Alternatives considered
- **Keyword-only text commands.** Rejected: error-prone, and they invite numeric-guessing bugs.
- **A staff web app for retrieval.** Rejected for V1 per docs/04; can be re-proposed with evidence.

## Consequences
Phase 1 can model each row as a command plus a contract test. Button limits, template needs outside the window, and the payload format are verified in Phase 0 before the copy is submitted for template approval.
