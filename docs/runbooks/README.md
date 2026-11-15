# Operational runbooks (drafts, Gate 3)

Drafts for the 13 situations in docs/05 ("Operational runbooks required before launch"). They describe the
system as built on `build/phase-0-2`. **Owners are not yet named**: the business owner and the on-call
technical owner for each runbook must be named before production (Gate 4/5). Steps that depend on the
hosting provider are marked *(provider)* and are completed once hosting is chosen.

| # | Situation | File | Console role |
|---|---|---|---|
| 1 | WhatsApp outage | [whatsapp-outage.md](whatsapp-outage.md) | Supervisor, admin |
| 2 | Invalid guest phone | [invalid-phone-correction.md](invalid-phone-correction.md) | Supervisor |
| 3 | Dead-letter replay | [dead-letter-replay.md](dead-letter-replay.md) | Admin |
| 4 | Stuck accepted task | [stuck-accepted-task.md](stuck-accepted-task.md) | Supervisor |
| 5 | Missing key or car | [missing-key-or-car.md](missing-key-or-car.md) | Supervisor, manager |
| 6 | Identity dispute at handover | [identity-dispute.md](identity-dispute.md) | Supervisor, manager |
| 7 | Unclaimed vehicle custody | [unclaimed-custody.md](unclaimed-custody.md) | Supervisor, manager |
| 8 | Account compromise | [account-compromise.md](account-compromise.md) | Admin, super admin, engineer |
| 9 | Backup restore | [backup-restore.md](backup-restore.md) | Engineer |
| 10 | Database migration failure | [migration-failure.md](migration-failure.md) | Engineer |
| 11 | Release rollback | [rollback.md](rollback.md) | Engineer |
| 12 | Retention deletion | [retention-deletion.md](retention-deletion.md) | Admin |
| 13 | Secret rotation | [secret-rotation.md](secret-rotation.md) | Engineer |

Ground rules that apply to every runbook:
- Never delete a ticket, shift or audit record to "clean up". Every console action asks for a reason and is audited.
- No action moves a car or key without a named person taking custody. There is no automatic reassignment of an
  accepted task.
- Never paste a guest phone number, collection code, token or secret into chat, tickets or logs.
