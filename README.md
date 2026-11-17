# Sallimha | سلّمها

Valet operations for a small team. Customers use WhatsApp only (ticket, request button, status, collection code,
rating, help). Valets and supervisors use a bilingual (Arabic RTL / English LTR) web app on phones and tablets;
admins also use it for the dashboard, team and settings (ADR-0011).

**Status (branch `build/phase-0-2`):** built and tested locally. Nothing is deployed. All WhatsApp behaviour runs
through a **simulated** transport and a development simulator; no real WhatsApp account has been connected.
Evidence: [docs/evidence/](docs/evidence/). Staging inputs: [docs/staging-inputs.md](docs/staging-inputs.md).
Pages, roles and flows at a glance: [docs/SYSTEM_OVERVIEW.md](docs/SYSTEM_OVERVIEW.md).

## Local demo

### Prerequisites
Docker (for PostgreSQL), [uv](https://docs.astral.sh/uv/) (installs Python 3.14 and the backend), Node.js 24,
`curl` and `make`. Free local ports: 55432 (PostgreSQL), 8100 (API), 5180 (app).

### Start
```bash
make demo-clean
```
This starts PostgreSQL in Docker, installs dependencies, migrates, seeds **synthetic** data (one open operation,
three valets on shift), runs the API and the worker, builds the app and serves it at **http://127.0.0.1:5180**.
`make demo` instead opens mid-event (cars parked, a retrieval offered, alerts). Stop with Ctrl+C, then `make stop`
to stop PostgreSQL. Each start reseeds the demo database.

### Accounts (synthetic, local-only)
| Sign in with | Role | Second factor |
|---|---|---|
| `admin` | Admin | `make demo-code` prints the current code |
| `supervisor` | Supervisor | — |
| `0550000101` (ماجد), `0550000102` (سارة), `0550000103` (فهد) | Valet | — |

Passwords are in `DEMO_PASSWORDS` in [services/api/ops/management/commands/seed_demo.py](services/api/ops/management/commands/seed_demo.py).
They exist only in local/test databases. Real people never receive a password: an admin adds them and gives them a
one-time setup code (Team → person → **رمز الإعداد**), and they choose their own password at **أول دخول أو نسيت كلمة
المرور؟** (First time, or forgot your password?) on the sign-in page.

Use a phone-sized window (or your phone on the same network) for valets, and a second browser or private window for
the supervisor; each person needs their own session.

### Walkthrough: registration to verified delivery
The app opens in Arabic; **English** switches language (valets: menu at the top). Labels are Arabic (English).
1. **Valet** — sign in as ماجد (`0550000101`). **مهامي** (My work) shows no task and the status *متاح* (Available).
2. Tap **تسجيل سيارة** (Register car). Enter the customer's number `0501234567` and `ABC 1234 كامري بيضاء`, then
   **التالي** (Next). Check the number with the customer and tap **إرسال التذكرة** (Send ticket): the customer's
   WhatsApp ticket is queued at once.
3. **التقاط صورة** (Take photo) four times (front, back, both sides). Answer **هل وصلت التذكرة؟** (Did the ticket
   arrive?), tap **بدء الركن** (Start parking), then choose zone **A**, spot `12`, key hook `15` and **تم الركن**
   (Parked).
4. **Customer** — in another window sign in as `supervisor` and open http://127.0.0.1:5180/dev/simulator (a
   development tool that stands in for the customer's phone). Open +966501234567 and tap **اطلب سيارتي** (Request my car).
5. **Valet** — My work shows **طلب إحضار** (Retrieval request) with a countdown. **قبول** (Accept), bring the car,
   **السيارة جاهزة** (Car ready).
6. **Customer** — the simulator thread shows a six-digit collection code. **Valet** — enter it and **تحقق**
   (Verify), hand over the car, **تم التسليم** (Delivered). The customer receives the rating buttons.
7. **Supervisor** — **التشغيل** (Operations) shows problems first, then cars waiting / on the way / ready with their
   waiting time, and a search. **الفريق** (Team) shows who is on shift, busy or on a break.

### Walkthrough: exceptions (supervisor)
Open a car from Operations. The detail shows one primary action and the rest under **إجراءات أخرى** (More actions):
safety hold and clear, incident, assisted request and assisted handover, withdraw, custody transfer, intake
transfer, phone correction, relocation (**نقل المركبة**: the valet accepts and records the new place in their app),
cancel before parking, propose unclaimed. **تواصل مع العميل** (Contact customer) opens the customer's number for a call
or WhatsApp from your own phone; that conversation happens outside Sallimha and opening the number is audited. If a
customer writes on WhatsApp, the message is kept on the ticket and **عميل يطلب المساعدة** appears in Problems.

**A valet's phone stops working:** Team → that valet → **جهازه لا يعمل** (Device not working) with a reason. You can then
record their acceptance, car ready and custody receipt on the ticket, or register and park a car for them; each
record names the valet, how you confirmed it and you. **عاد جهازه للعمل** ends it.

**Customer WhatsApp down:** in the simulator press **محاكاة انقطاع واتساب**. Staff keep working in the app; Operations
and the valets' screens say customer messages are not arriving. Use **طلب إحضار بمساعدة المشرف** for a customer at
the stand and **تسليم بمساعدة المشرف** to hand over without a code. When it ends, queued messages that are still true
are delivered; nothing stale (an expired offer, a code for a car already handed over) is sent. Admins declare and end
the outage in Operations → **الأعطال** (Outages); supervisors report it.

### Walkthrough: admin
Sign in as `admin` with the code from `make demo-code`.
- **لوحة المتابعة** (Dashboard): parked cars, waiting and delayed requests, deliveries, request-to-ready time (defined
  on the screen), unresolved problems and the team. **التقرير الكامل والتصدير** opens the full report and CSV exports.
- **الفريق** (Team): add a valet or supervisor (name, mobile, role), give them their one-time setup code, put them on
  the operation's team, change role, deactivate or reactivate; admins also get second-factor setup.
- **الإعدادات** (Settings): the operation and venue, timings and wording, retention; under **متقدم** (Advanced):
  message delivery (dead letters and replay), WhatsApp status and the simulator (development builds only).
- Operations → **الأعطال**: declare or end a customer WhatsApp outage; after a whole-system outage record its window
  and reconcile intakes and handovers made during it. Carryover approvals and incident resolution are admin-only.

Runbooks: [docs/runbooks/](docs/runbooks/README.md).

## Development
| Command | What it does |
|---|---|
| `make test` | Backend suite (pytest against real PostgreSQL) |
| `make lint` | Ruff and TypeScript type check |
| `make e2e` | Playwright suite (valet phone, supervisor and admin; phone and tablet screenshots in two languages); set `PW_CHANNEL=chrome` to use an installed Chrome |
| `make contract` | Regenerate `contracts/openapi.yaml` (fails on any schema warning) and the console's TypeScript types |
| `docker build -t sallimha:local . && scripts/smoke-image.sh` | Build the deployable image and run it with staging settings and placeholder secrets (needs `make db` running) |
| `scripts/rehearse-restore.sh` | Backup and restore rehearsal on the local database, synthetic data (needs `make db` running) |

Django refuses to start unless `SALLIMHA_ENV` is `local`, `test`, `staging` or `production`; the Makefile and
scripts set `local` for you. For a manual command: `cd services/api && SALLIMHA_ENV=local uv run python manage.py …`.

CI (`.github/workflows/ci.yml`) runs the backend suite, the contract drift check, the web build and the
Playwright suite on every push.

---

## Specification pack (handoff v1.0)

Prepared 15 November 2026, Asia/Riyadh. A self-contained specification for Claude Code. The original PDFs and sketch are not required.

### Start here
1. Extract this folder into the root of the Sallimha repository. Keep its relative paths. If files already exist, merge deliberately instead of overwriting them.
2. Read `Sallimha_Final_Approach.pdf` for the operating model and `Sallimha_Brand_Identity.pdf` for the proposed visual identity.
3. Start a fresh Claude Code session from the repository root. Paste `Claude_Kickoff.md`.
4. Claude must first verify the supplied files, inspect any actual application code, and record remaining deployment inputs. It should not ask for the source PDFs.

### What is authoritative
The user-approved process is specified in `docs/01_Final_Approach.md`. The other documents make it implementable. All newly selected implementation details, target metrics, and brand assets are explicitly proposed defaults. They have not been approved separately or validated in production.

| File | Purpose |
|---|---|
| `CLAUDE.md` | Repository instructions and working rules |
| `docs/01_Final_Approach.md` | Product scope and complete operating process |
| `docs/02_Roles_and_State_Model.md` | Permissions, states, entities and invariants |
| `docs/03_Dispatch_and_Reliability.md` | Fair assignment, concurrency and recovery |
| `docs/04_WhatsApp_and_Messages.md` | Registration, messaging and bilingual copy |
| `docs/05_Architecture_and_Deployment.md` | Proposed architecture and deployment requirements |
| `docs/06_Test_and_Release_Plan.md` | Acceptance scenarios and release gates |
| `docs/07_Decisions_and_Sources.md` | Approved versus proposed choices, sources and open inputs |
| `DESIGN.md` | Brand and UI specification |
| `brand/` | Vector identity assets, design tokens and licensed fonts |
| `Claude_Kickoff.md` | Ready-to-paste starting prompt |

### Scope
This pack specifies the product. (When written, it was not an implemented or deployed application; see Status above for what is now built.) No source repository was audited here. The user-provided Claude readiness report described an empty clone. No hosting provider, production domain, WhatsApp account, legal retention schedule, or operating capacity has been verified.

Keep the software deterministic: vehicle assignment, ticket transitions and ownership checks must not depend on an LLM. AI coding tools help build the product; they are not required in its operational request path.

