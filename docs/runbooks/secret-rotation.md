# Secret rotation

**Owner:** on-call technical — _to be named_. Secrets live only in the hosting secret store.

| Secret | How to rotate | Effect |
|---|---|---|
| `WHATSAPP_APP_SECRET` | Set the new value, move the old one to `WHATSAPP_APP_SECRET_PREVIOUS`, restart; rotate in Meta; clear the previous value after a day | Webhooks signed with either secret are accepted during the overlap |
| `WHATSAPP_ACCESS_TOKEN` | Issue a new system-user token in Meta, set it, restart web and worker, revoke the old token | Sends in flight may fail transiently and retry |
| `WHATSAPP_VERIFY_TOKEN` | Set the new value, then update it in the Meta webhook settings | Only used when Meta re-verifies the webhook |
| `DJANGO_SECRET_KEY` | Set the new value; put the old one in `DJANGO_SECRET_KEY_FALLBACKS`; restart. Remove the fallback after a day (sessions last 12 h) | Nobody is signed out during the overlap |
| `DATABASE_URL` password | Rotate in the database provider, update the secret, restart | Brief reconnect |
| `FIELD_ENCRYPTION_KEY` | 1. Generate a new Fernet key. 2. Set it as `FIELD_ENCRYPTION_KEY` and put the old one in `FIELD_ENCRYPTION_KEYS_PREVIOUS`; restart web and worker. 3. `manage.py rotate_keys` (dry run) then `--apply`. 4. `--verify` until `pending 0`. 5. Remove the old key from the environment; **keep it in the secret store while backups that need it exist** | No downtime; old data stays readable throughout |
| `HASH_KEY` | Same steps with `HASH_KEY` / `HASH_KEY_PREVIOUS`, preferably together with the field key. Keep `HASH_KEY_PREVIOUS` until the events open at rotation time have closed (guests' WhatsApp buttons hash with the old key) | Lookups accept both keys during the overlap; login-throttle counters reset |
| Staff MFA secrets | Admin uses **Issue two-factor setup** per person | That person's old authenticator stops working |

After any rotation: check `/readyz`, the health line in Operations and one simulated or test send on staging.
Recovery: an interrupted `rotate_keys --apply` is safe to rerun. To restore a backup taken before a rotation, put
the key it was written with back into the matching `…_PREVIOUS` variable and run `rotate_keys --apply` (ADR-0009).
