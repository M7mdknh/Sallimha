# WhatsApp onboarding checklist — Sallimha

Prepared 2026-11-16 from Meta's developer documentation (sources at the end) and docs/11. **Nothing here has been
exercised with a real account yet: every result stays BLOCKED until it is done on staging.** Secrets (access token,
app secret, verify token, two-step PIN) go straight into the hosting secret store by the account owner — never into
chat, tickets or this repository.

## A. Required for testing (staging)
| # | Step | Who | Done when |
|---|---|---|---|
| A1 | Meta account for the owner with two-factor authentication; a **Meta Business portfolio** for Sallimha (business.facebook.com). Verification is not needed yet | Owner | Portfolio exists |
| A2 | In the App Dashboard, **create an app** with the use case "Connect with customers through WhatsApp", linked to the portfolio. Meta creates a WhatsApp Business Account (WABA) and a **test business number** | Owner | API Setup page shows the test number |
| A3 | **Staging sender:** either Meta's test number (only allow-listed recipients, test display name) or — recommended for the real journey — a **dedicated staging number** that is not on the WhatsApp app, can receive SMS or a voice call, registered with a **two-step PIN** (owner keeps the PIN). A new portfolio may register **2 numbers** until it is verified | Owner | Number shows "Connected" |
| A4 | **System user** in Business Settings with the app and the WABA assigned (full control); generate a **permanent token** with `whatsapp_business_messaging` and `whatsapp_business_management` → secret store as `WHATSAPP_ACCESS_TOKEN`. Phone number ID → `WHATSAPP_PHONE_NUMBER_ID` | Owner | Token stored; never pasted in chat |
| A5 | App secret (App settings → Basic) → `WHATSAPP_APP_SECRET`. A random verify token chosen by the owner → `WHATSAPP_VERIFY_TOKEN` | Owner | Both in the secret store |
| A6 | **Webhook:** callback URL `https://<staging-host>/webhooks/whatsapp`, the verify token, subscribe the app to the WABA and to the **`messages`** field (delivers messages and statuses). Meta's GET verification must succeed; our server checks `X-Hub-Signature-256` on every POST | Me, once staging runs | `deploy_check` shows WhatsApp PASS; signed test webhook accepted, unsigned refused |
| A7 | **Templates** (list in section C): submit Arabic and English versions, category **Utility**, with quick-reply buttons where listed. The code message (`guest_ready`) may be categorised as authentication by Meta — verify | Me drafts, owner submits | All approved |
| A8 | **Test phones:** 3 customer handsets (synthetic people, real phones) and 3 staff phones or tablets for the web app. With Meta's test number every customer number must be on the allow-list in API Setup | Owner provides handsets | Numbers registered |
| A9 | **Real journey on staging** (Gate 4): valet app intake → customer's WhatsApp ticket → parking → request → offer in the valet app → accept → ready → code → verified handover → rating; plus customer help, a withdrawal, a phone correction, a customer-WhatsApp outage drill and recovery. Record each result as PASS only when observed on real phones | Me with owner's testers | Evidence in docs/evidence |

Limits that apply while testing: a new, unverified portfolio may start **250** business-initiated messages per
24 hours (shared by all its numbers) and register 2 numbers.

## B. Additionally required for production
| # | Step | Notes |
|---|---|---|
| B1 | **Business verification** of the portfolio (legal documents of the Saudi entity) | Raises the limit to **2,000** per 24 h and allows up to 20 numbers; later tiers (10,000, 100,000, unlimited) scale automatically with volume and quality |
| B2 | **Production number** (dedicated, not on the WhatsApp app), registered with a two-step PIN; **display name** "Sallimha / سلّمها" approved | Separate from the staging number |
| B3 | **Payment method** on the WABA (owner adds it in Meta Business Manager) | Meta charges per message since 1 July 2025; rates differ by recipient country (Saudi Arabia has its own rates). Per Meta's pricing page, service messages are charged beyond 1,000 free per number per month and utility templates sent inside an open window are charged from 1 October 2026 — confirm the current Saudi rate card before go-live |
| B4 | Templates approved in the **production** WABA (approvals do not carry over from a separate staging WABA) | Same list as section C |
| B5 | Quality rating and messaging-limit monitoring (Meta Business Manager) | Add to the on-call checklist |
| B6 | Privacy policy URL and business profile (Arabic/English), opt-in recorded at intake (already implemented) | Messaging policy |

## C. Template inventory (customers only; sent when the customer has not written in the last 24 hours)
The app sends a free-form message when the 24-hour window is open and otherwise the approved template of the same
name (dots become underscores: `guest.ticket` → `guest_ticket`). Each needs Arabic **and** English versions. Staff
work in the web app (ADR-0011), so no staff templates are needed. A customer's free-text message is answered with
`guest.help_received` inside the 24-hour window that their message opened (no template needed).

| Template | Recipient | Variables | Buttons |
|---|---|---|---|
| `guest_ticket` | Guest (always outside a window: first message) | ticket, venue | Request my car |
| `guest_parked` | Guest | ticket | — |
| `guest_ready` | Guest | code, pickup_point | — (category to verify: utility vs authentication) |
| `guest_accepted` | Guest | — | — |
| `guest_delivered` | Guest | — | Excellent / Okay / Poor |
| `guest_withdrawn` | Guest | ticket | — |
| `guest_cancelled` | Guest | ticket | — |

Staging checks for templates: variable order or names must match what the app sends (the request builder sends
body parameters in the order listed); a button tap on a template must open the 24-hour window (docs/11 item 5).

## Sources (read 2026-11-16)
- [Cloud API get started](https://developers.facebook.com/docs/whatsapp/cloud-api/get-started) — app creation, test
  number, system-user token permissions.
- [Business phone numbers](https://developers.facebook.com/docs/whatsapp/cloud-api/phone-numbers) — number
  requirements, SMS/voice verification, two-step PIN, 2 numbers until verified (then 20).
- [Messaging limits](https://developers.facebook.com/docs/whatsapp/messaging-limits) — 250 → 2,000 → 10,000 →
  100,000 → unlimited, per business portfolio.
- [Pricing](https://developers.facebook.com/docs/whatsapp/pricing) — per-message pricing, category and country rates.
- docs/11_WhatsApp_Platform_Verification.md — webhook signature, buttons, 24-hour window, sender identity.
