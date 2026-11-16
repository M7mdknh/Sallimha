# Draft provisioning plan — Oracle Cloud, Riyadh (`me-riyadh-1`)

> **DRAFT — NOT APPLIED.** Prepared for approval only (docs/staging/hosting-options.md). Nothing is created until the
> owner approves the option and the cost ceiling. Every secret is entered by the account owner into OCI Vault.

## Order of work (after approval)
| # | Resource | Name / size | Notes |
|---|---|---|---|
| 1 | Tenancy (home region Riyadh), budget + alert | `sallimha`, budget per approval | Owner creates the account and payment method |
| 2 | Compartment | `sallimha-staging` (later `sallimha-production`) | Isolation of staging from production |
| 3 | IAM | groups `sallimha-admins` (MFA), `sallimha-deployers`; dynamic group for container instances | Least privilege |
| 4 | Network | VCN `10.20.0.0/16`; public subnet (load balancer), private subnet (containers, database) ; NAT + service gateway | Containers and database have no public IPs |
| 5 | Vault + secrets | `DJANGO_SECRET_KEY`, `FIELD_ENCRYPTION_KEY`, `HASH_KEY`, `DATABASE_URL`, `WHATSAPP_*`, object-storage keys | Formats in docs/staging-inputs.md |
| 6 | PostgreSQL | OCI Database with PostgreSQL 16+, `PostgreSQL.VM.Standard.E4.Flex` 1 OCPU / 16 GB, 50 GB, PITR 7–35 days (owner decides), private subnet | Release job runs `migrate` |
| 7 | Object Storage | private bucket `sallimha-staging-media`, no public access, versioning on; S3-compatible customer secret key for the app | `MEDIA_STORAGE=s3`, `MEDIA_S3_ENDPOINT_URL=https://<namespace>.compat.objectstorage.me-riyadh-1.oraclecloud.com`, `MEDIA_S3_REGION=me-riyadh-1` |
| 8 | Container registry | OCIR repository `sallimha/app`, image tag = git SHA | CI pushes only after approval |
| 9 | Container instances | `sallimha-web` (1 OCPU / 2 GB, gunicorn), `sallimha-worker` (1 OCPU / 2 GB, `run_worker`); release job as a short-lived instance | Same image, env from Vault |
| 10 | Load balancer + TLS | Flexible LB 10 Mbps, HTTPS listener with the staging certificate, backend `sallimha-web:8000`, health check `/healthz` | `TRUSTED_PROXY_COUNT=1`; certificate renewal automated |
| 11 | DNS | `staging.<domain>` → load balancer | Owner's DNS |
| 12 | Monitoring + alarms | uptime of `/readyz`, worker heartbeat (via `/readyz`), container restarts, database CPU/storage, budget | Alert recipients per decision 4 |
| 13 | Release gate | `python manage.py migrate --noinput && python manage.py deploy_check` | Must PASS (WhatsApp BLOCKED allowed only for a dry run) |
| 14 | Provider restore test | PITR restore of the staging database into a new database + bucket version restore; run `deploy_check` and the restore checks from scripts/rehearse-restore.sh against it | Required before staging is called ready |
| 15 | Real WhatsApp journey | docs/staging/whatsapp-onboarding.md A9 | Required before staging is called ready |
