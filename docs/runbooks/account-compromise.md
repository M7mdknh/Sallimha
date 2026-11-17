# Account compromise

**Owner:** on-call technical — _to be named_; admin.

## Any staff account (valet, supervisor, admin)
1. **Team** page: **Deactivate** the account with the reason. All its sessions end immediately (the session
   epoch changes), and it can no longer sign in.
2. If the person still holds custody of a car or key, the system raises a custody alert: resolve it with
   [stuck-accepted-task.md](stuck-accepted-task.md) steps.
3. When it is safe: **Reactivate**, then **Setup code** and give the code to the person directly (never by message).
   They choose a new password with it; every other session of theirs ends. Nobody else ever knows the password.
4. Admins: another admin uses **Issue two-factor setup** for that person. The old authenticator stops working; the
   new setup link is shown once and must be delivered out of band.
5. An admin account is usable again only after both a new password and a new second factor.
6. Review the audit log for that account's actions in the affected window *(provider log access)*.

## Lost or stolen valet phone
- The app on that phone is signed in. Deactivate the person at once (all sessions end), mark their device as not
  working on the Team page so a supervisor can record their actions, and resolve any custody they hold. Reactivate
  and issue a setup code when they have a phone again.

## Login abuse
- Repeated failures are throttled per account and network without locking the real user out; second-factor
  failures lock the second factor after five attempts. An admin re-issues it.
