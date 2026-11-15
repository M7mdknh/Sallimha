# Account compromise

**Owner:** on-call technical — _to be named_; super admin.

## Console staff account
1. **Staff** page: **Deactivate** the account with the reason. All its sessions end immediately (the session
   epoch changes), and it can no longer sign in.
2. If the person still holds custody of a car or key, the system raises a custody alert: resolve it with
   [stuck-accepted-task.md](stuck-accepted-task.md) steps.
3. Engineer: reset the password on the server — `uv run python manage.py changepassword <username>` — and give
   the new password to the person out of band.
4. Manager and above: an admin uses **Issue two-factor setup** for that person. The old authenticator stops
   working; the new setup link is shown once and must be delivered out of band.
5. Reactivate only after the person has a new password and a new second factor.
6. Review the audit log for that account's actions in the affected window *(provider log access)*.

## Valet (WhatsApp)
- A valet works from their registered number. If the phone is lost or taken: deactivate the staff record, end
  their shift once custody is resolved, and create a new record when they have a new number.

## Login abuse
- Repeated failures are throttled per account and network without locking the real user out; second-factor
  failures lock the second factor after five attempts. An admin re-issues it.
