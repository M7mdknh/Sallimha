# Secret rotation

**Owner:** on-call technical — _to be named_. Secrets live only in the hosting secret store.

| Secret | How to rotate | Effect |
|---|---|---|
| `WHATSAPP_APP_SECRET` | Set the new value, move the old one to `WHATSAPP_APP_SECRET_PREVIOUS`, restart; rotate in Meta; clear the previous value after a day | Webhooks signed with either secret are accepted during the overlap |
| `WHATSAPP_ACCESS_TOKEN` | Issue a new system-user token in Meta, set it, restart web and worker, revoke the old token | Sends in flight may fail transiently and retry |
| `WHATSAPP_VERIFY_TOKEN` | Set the new value, then update it in the Meta webhook settings | Only used when Meta re-verifies the webhook |
| `DJANGO_SECRET_KEY` | Set a new value and restart | Everyone is signed out; staff sign in again |
| `DATABASE_URL` password | Rotate in the database provider, update the secret, restart | Brief reconnect |
| `FIELD_ENCRYPTION_KEY` | **Not supported yet.** Needs a re-encryption command (Phase 3 work) | Changing it without re-encryption makes stored phones unreadable |
| `HASH_KEY` | **Not supported yet.** Needs a re-hash migration (Phase 3 work) | Changing it breaks guest phone matching |
| Staff MFA secrets | Admin uses **Issue two-factor setup** per person | That person's old authenticator stops working |

After any rotation: check `/readyz`, the live view health line and one simulated or test send on staging.
