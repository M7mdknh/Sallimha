# ADR-0012 — Controlled admin access and an explicit offer acknowledgement

- Status: **Accepted 2026-11-17** (user review of the ADR-0011 build, before staging).
- Amends: ADR-0011 decision 3 (when an offer's window starts) and decisions 4 and 6 (who issues an admin's
  credentials). Everything else in ADR-0011 stands.

## Context
The security review of the ADR-0011 build noted two things:
- **Admins could reset each other.** Any admin could issue a setup code and a second-factor enrolment for another
  admin, then sign in as that person. In a team with one or two admins, one person could act as two, which defeats
  the two-person checks. For example, an outage handover reconciliation needs a verifier other than the admin.
- **Reading My work had a side effect.** `GET /api/valet/work` started the response window of a pending offer. A read
  that changes state can be triggered without the valet's intent, by prefetching, a stray tab or a retry, and it
  cannot carry CSRF protection.

## Decisions
1. **No admin credential is issued from the app.**
   - Admins keep routine onboarding and reset for valets and supervisors: a one-time setup code from the Team page.
   - For an admin, the setup-code endpoint refuses with `admin_access_procedure`, and the in-app second-factor
     endpoint is removed.
   - A setup code that is still pending when a role change involves ADMIN is cancelled. A code issued to a
     supervisor therefore never opens an admin account.
   - The detour "demote a peer, reset them, promote them back" ends at a sign-in that needs the controlled
     procedure. That procedure replaces the password the first admin chose.
2. **Controlled admin access** (`ops.services.staffdir.grant_admin_access`, run only as
   `manage.py admin_access` on the server by the technical owner) covers four situations:
   - first access after promotion;
   - a locked second factor;
   - a lost phone;
   - a suspected compromise.

   It requires:
   - a **requesting** enabled admin of the same organisation. This may be the target, when they are locked out.
   - a **different approving** enabled supervisor or admin of the same organisation, who is neither the requester
     nor the target.
   - a reason, and the operator's name.

   In one transaction it:
   - makes the old password unusable;
   - cancels any pending code;
   - issues a new second factor (which also clears a lock);
   - ends every session;
   - creates a new one-time setup code;
   - writes an audit record naming the requester, the approver, the operator and the reason.

   The code and the second-factor link are printed once for the person, who receives them in person. Only the
   organisation's very first admin, when nobody else could approve, may use `--first-admin`; it is refused while
   another enabled admin exists. The old `issue_mfa` command is removed.
3. **Not silent.** The Team page shows every admin the last controlled access on each admin's row: when, requested
   by, approved by and the reason. The audit log keeps the full history. This is the one visible addition.
4. **The offer acknowledgement is an explicit command.**
   - `GET /api/valet/work` is a pure read.
   - The app sends `POST /api/valet/tasks/<id>/shown` when the offer card is on screen and the page is visible. The
     command is authenticated, CSRF-protected, needs an Idempotency-Key and is limited to the valet's own retrieval
     offer.
   - The first acknowledgement starts the response window: `min(now + offer window, hard limit)`.
   - A later one (a refresh, another tab, a retry after a lost reply) answers `already_shown` with the same deadline
     and changes nothing.
   - An acknowledgement after acceptance, release or the hard limit is `stale` and changes nothing.
   - The read model exposes `shown`. While an offer is unshown the app retries the acknowledgement after each poll.
   - An offer that is never acknowledged still lapses at the hard limit from reservation (60 s by default) and goes
     to the next valet, so a locked or closed phone never holds a car.

## Consequences
- **Trust in the server.** Names given to `admin_access` are the operator's attestation. Anyone with server or
  database access is outside the app's role model. Who holds server access, and who may approve an admin's access,
  are owner decisions (docs/decisions-needed.md A7, A8).
- **Promotion has a second step.** A new admin is promoted in the app and then gets their sign-in through the
  procedure (README, runbook admin-access).
- **Lockouts need the technical owner.** A five-failure second-factor lock is cleared only by the procedure, which
  also resets the password.
- **Existing behaviour.** The "offer not yet shown on the valet's device" alert now means that no acknowledgement
  has arrived. Supervisors read it the same way as before.
- **Tests:**
  - `tests/app/test_admin_access.py` covers refusals, the demote-and-promote detour, the two-person rules, the reset
    effects, the lock, the first admin, the Team-page record and the command.
  - `tests/app/test_offer_shown.py` covers that a read writes nothing, the one-time start, refreshes and other tabs,
    the hard-limit cap, a late acknowledgement, polling without an acknowledgement, accepting before it, CSRF,
    ownership and the key.
  - Playwright `roles.spec.ts` covers an admin row with no setup code and the note.
