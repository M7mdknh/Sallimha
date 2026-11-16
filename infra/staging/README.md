# Staging configuration (provider-neutral, ADR-0004)

Nothing here is deployed. These are the settings a staging host needs once the hosting decision is made
(docs/decisions-needed.md). Values live in the provider's secret store; this file lists **names only**.

## One image, three process types
| Process | Command | Replicas |
|---|---|---|
| Release job (before each rollout) | `python manage.py migrate --noinput && python manage.py deploy_check` | one-off |
| Web (API, webhook, console on one origin) | image default: `gunicorn sallimha.wsgi:application --bind 0.0.0.0:8000` | ≥ 1 (production ≥ 2) |
| Worker | `python manage.py run_worker` | ≥ 1, always running |

Health: `/healthz` (process up) for liveness; `/readyz` (database + worker heartbeat) for readiness. Both are exempt
from the HTTPS redirect so a platform load balancer can probe them over plain HTTP.

## Environment
| Name | Staging value |
|---|---|
| `SALLIMHA_ENV` | `staging` (the app refuses to start without an explicit value) |
| `DJANGO_SECRET_KEY`, `FIELD_ENCRYPTION_KEY`, `HASH_KEY`, `DATABASE_URL` | from the secret store (formats in docs/staging-inputs.md) |
| `DJANGO_ALLOWED_HOSTS` / `DJANGO_CSRF_TRUSTED_ORIGINS` | the staging host name / `https://` + host name |
| `TRUSTED_PROXY_COUNT` | number of proxies that append `X-Forwarded-For` (also enables `X-Forwarded-Proto`) |
| `MEDIA_STORAGE=s3`, `MEDIA_S3_BUCKET`, `MEDIA_S3_REGION`, `MEDIA_S3_ENDPOINT_URL` (non-AWS), `MEDIA_S3_SSE` | private bucket, no public access; credentials via the platform identity or `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` from the secret store |
| `WHATSAPP_TRANSPORT=cloud`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN` | staging test sender (BLOCKED until supplied) |
| `SECURE_HSTS_SECONDS` | `3600` on staging; raise only after HTTPS is confirmed for the whole domain |
| `SIMULATOR_ENABLED` | unset (refused outside local/test) |
| Rotation only: `DJANGO_SECRET_KEY_FALLBACKS`, `FIELD_ENCRYPTION_KEYS_PREVIOUS`, `HASH_KEY_PREVIOUS`, `WHATSAPP_APP_SECRET_PREVIOUS` | empty except during a rotation |

## Release gate
`deploy_check` prints PASS / FAIL / BLOCKED for: environment, demo features off, secret strength, host names over
HTTPS, Django `check --deploy`, database reachable with migrations applied, fresh worker heartbeat, private bucket
write/read/delete, WhatsApp sender configured. Any FAIL stops the release; BLOCKED (external input missing) stops it
unless `--allow-blocked` is passed for a dry staging run.

## Verified locally (not on a host)
- `docker build .` and `scripts/smoke-image.sh`: migrate job, health/readiness with a real worker, console and assets
  on one origin, HTTPS redirect, simulator absent, `deploy_check` refusing only for local media (no bucket) with
  WhatsApp BLOCKED. CI builds the image and runs `check --deploy` in it on every push.
- `scripts/rehearse-restore.sh`: backup → restore into an empty database → schema current, identical row counts,
  audit trigger present.
- S3 behaviour against an S3 emulator (moto): encrypted private objects, no public grants, streaming through the
  authorised media view.

## Still BLOCKED until a host exists
Real bucket, managed PostgreSQL point-in-time recovery, TLS certificate and domain, WhatsApp sender and webhook,
monitoring and alerting, the production-like smoke test on the exact released image.
