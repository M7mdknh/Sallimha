# Retention deletion

**Owner:** business — _to be named_ (chooses the periods); admin applies.

## Facts
- Zero means "never delete automatically" (the system default). The owner must choose periods before launch;
  no legal period is assumed by the product.
- Three separate periods: guest phone numbers, intake photos, resolved-incident evidence. Periods count from
  when the ticket or incident closed.
- Anything tied to an open incident or an active safety hold is protected and never deleted.

## Steps (admin)
1. **Settings → Data retention:** set the periods the owner chose and save. The change is audited.
2. Each field shows how many items are eligible now.
3. **Apply retention now** → confirm. Phone numbers are redacted; photos are deleted from private storage.
   The result shows how many items were removed; the action is audited without copying the deleted data.
4. Backups keep deleted data until they expire *(provider backup window)*. After a restore, apply retention again.
