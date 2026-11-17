# ADR-0008 — Outage relay and reconciliation

> **Amended by [ADR-0011](0011-staff-app-and-three-roles.md):** relayed actions are now allowed for a valet whose device a supervisor marked as not working (staff connectivity loss), not because customer WhatsApp is down. Declaring and ending a customer WhatsApp outage, recording a system outage and reconciling are ADMIN actions (previously manager and above). Reconciliation rules are unchanged.

- Status: **Accepted 2026-11-16** (user mandate 2026-11-16 item 2; resolves the open item in the outage runbook).
- Requirement basis: docs/03 ("WhatsApp unavailable: keep state, show outage, queue allowed messages;
  supervisor-assisted operations with explicit identity verification"; "During a total service outage, staff use
  an agreed human continuity procedure, preserve custody, and reconcile records afterward"), CLAUDE.md (no routine
  manual dispatch; holds never bypassed; an acknowledged action is durably committed).

## Amendment 2026-11-16 (owner decision)
- **Declaring and ending** the organisation-wide WhatsApp outage is for **managers and above** only. Supervisors
  **report** a problem for their event (critical alert to managers, one open alert per event; every report audited)
  and, once a manager has declared the outage, perform the relayed actions within their assigned events.
- **Live intake on a valet's behalf** no longer creates a parked car in one step (see Task 3 of the second
  2026-11-16 plan): it registers the car (RECEIVED), keeps photos where they can be taken (or requires an explicit
  exception), and only a separate parking confirmation with location, key hook and the responsible valet parks it.
  The retrospective reconciliation after a whole-system outage still records an already-parked car with its actual
  times and evidence.

## Decision
### WhatsApp unavailable, console working
- A supervisor **declares** a WhatsApp outage (reason, audited, critical alert on every open event). The sender is
  organisation-wide, so the outage is too; one open outage per organisation (database constraint). A supervisor
  must be assigned to an open event to declare it; only the declarer or a manager ends it.
- **Only while it is open**, a supervisor may record, with `confirmed_via` (in person / radio):
  1. the valet's acceptance of the **dispatcher's current offer** (retrieval or move) — the supervisor cannot
     choose or change the valet, so this is not manual dispatch;
  2. "car ready" for the accepted retrieval — handover then uses the existing supervisor-assisted verification;
  3. receipt of a custody transfer by the receiving valet;
  4. an **intake on a valet's behalf**: the ticket is created parked by that valet, photos excepted with the reason,
     guest contact = supervisor-assisted fallback, and the guest's WhatsApp ticket is **queued** (not delivered).
- Each record is audited with the valet as the actor plus `relayed_by` and `confirmed_via`; the WhatsApp buttons
  for that step are revoked so a late tap cannot apply it twice.

### Whole system unavailable
- Staff follow the continuity procedure (runbook). After recovery a **manager records the outage window** with
  venue-local start and end (in the past, ≤ 24 h long, within 30 days, never overlapping another window).
- **Reconciliation** (manager+), per ticket:
  - *Handover:* actual time (`occurred_at`) stored apart from the entry time (`recorded_at`), the valet who handed
    over (must be a valet assigned to the event), the verifier (supervisor+ for the event, **not** the person
    entering — two-person attestation), the verification method, evidence and reason. The open request is
    completed and live tasks closed; the key is released at the actual time.
  - *Intake:* actual received and parked times inside the window, valet, evidence, reason.
  - Rejected: times outside the window, before parking, or in the future; missing evidence; an already
    delivered or cancelled ticket (`already_delivered`); a second reconciliation of the same kind (database
    constraint); an active handover-blocking safety hold (`handover_blocked` — clear it first, with a reason).
- An incident is never needed to correct the record: a delivered car is reconciled to DELIVERED, not left PARKED.

## Not decided here (for the owner)
- Whether reconciliation should require photo evidence (currently text evidence + offline log reference).
- The continuity procedure's offline log format and who keeps it (business owner).
- Whether a manager (not only a supervisor) must confirm a WhatsApp outage declaration.
