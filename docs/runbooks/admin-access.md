# Admin access: first sign-in, lockout, lost phone, compromise

**Owner:** on-call technical — _to be named_ (runs the command); approvers — _to be named_ (decisions A7, A8).

Admins never set up or reset another admin's sign-in in the app (ADR-0012). Valets and supervisors do not use this
runbook: an admin gives them a setup code from the Team page.

## When
- A supervisor was promoted to admin and has no second factor yet (sign-in says two-factor must be set up).
- An admin's second factor is locked after five wrong codes.
- An admin lost the phone with their authenticator, or forgot their password.
- An admin account may be compromised (first deactivate it, see [account-compromise.md](account-compromise.md)).

## Who
- **Requester:** an enabled admin. Admins who are locked out may ask for themselves.
- **Approver:** a different enabled supervisor or admin. Never the requester or the target. They confirm the
  target's identity in person.
- **Operator:** the technical owner, on the server. They should hold neither of the other two roles for this request.
  The command records the names it is given. It cannot prove who typed them, so the record and the people involved
  are the control.

## Steps
1. The requester asks the technical owner in writing (ticket or message without any code or password), naming the
   target and the reason.
2. The approver meets the target, checks who they are and confirms to the technical owner.
3. The technical owner runs, on the server (the container or VM shell *(provider)*):
   ```bash
   uv run python manage.py admin_access <target sign-in> --requested-by <requester sign-in> \
     --approved-by <approver sign-in> --reason "<why; how identity was checked>" --operator "<your name>"
   ```
   The command refuses a missing reason, a target who is not an enabled admin, a requester who is not an enabled
   admin, and an approver who is the requester, the target, a valet or from another organisation.
4. It prints the sign-in name, an 8-digit setup code (valid 72 hours) and a second-factor link, **once**. Give them
   to the target in person. Never send them by message or store them anywhere.
5. The target opens **First time, or forgot your password?** on the sign-in page, chooses a new password with the
   code, adds the link to an authenticator app, and signs in with password and code.
6. Everyone can check: the target's row on **Team** shows "Sign-in last set up from the server", with the date,
   requester, approver and reason.

## What it changes
- The old password stops working.
- Any pending setup code is cancelled.
- The old second factor stops working and any lock is cleared.
- Every open session of that person ends.
- The audit record names the requester, the approver, the operator and the reason. It never contains the code or the
  link.

## First admin of a new deployment
Only when no other enabled admin exists in the organisation, and nobody else could approve:
```bash
uv run python manage.py admin_access <sign-in> --first-admin --reason "new deployment" --operator "<your name>"
```
It is refused as soon as another enabled admin exists. Create the organisation, the first admin's staff record and
their sign-in account with the staging bootstrap steps (docs/staging-inputs.md).
