# 04 — WhatsApp contract and content

## Channels
Approved baseline: guests and valets use WhatsApp. Supervisors/managers/admins use the web console. A staff registration app is not silently introduced as a dependency. It may be proposed later with evidence if the WhatsApp intake experience proves too slow.

Use the official WhatsApp Business Platform directly or an approved provider behind an adapter. The account, sender number, verification and template approvals are external setup inputs. Browser automation of personal WhatsApp is not the production transport.

## Platform facts to verify at implementation
The official messaging policy requires recipient permission and approved templates for business-initiated conversations. Free-form responses are allowed within the customer-service window opened/reset by an incoming user message; outside it, use approved templates. Collecting a phone number at intake does not open that window. An outbound ticket alone does not open it either.

Apply this rule to valets too. A valet starting a shift by messaging the service can open a window, but an outbound assignment may still need an approved template when no active window exists. The transport adapter chooses an approved template or valid session message based on verified provider context; it must never assume “employee” bypasses the platform rules.

Template names and copy below are drafts, not Meta approvals. Check actual button limits, payload formats and template category at implementation. Message webhooks carry incoming messages and outgoing delivery statuses; persist and reconcile both. Sources: official policy and webhook references in `07_Decisions_and_Sources.md`.

## Staff intake interaction (proposed minimal sequence)
| Context | Staff action | Server behavior |
|---|---|---|
| Available on active shift | Tap/send “مركبة جديدة” | Reserve intake, create ticket, ask for guest phone |
| Awaiting phone | Send country code + number | Validate, show masked confirmation and ask to confirm/correct |
| Awaiting phone confirmation | Tap “تأكيد الرقم” | Record messaging permission, send guest ticket; ask the valet to confirm receipt |
| Awaiting receipt confirmation | Tap “نعم، استلمها” or “لم تصل” | Yes → CONFIRMED_IN_PERSON. No → visible contact exception and correction path. Either way ask vehicle info |
| Awaiting vehicle info | Send plate and optional description | Preserve raw text; parse conservatively; ask confirmation if ambiguous |
| Awaiting intake photos | Send four photos | Link each to this intake; confirm count; do not mark parked |
| Photos complete | Tap “بدء الركن” | Record `parking_started_at`; from now on the ticket cannot be cancelled |
| Parking in progress | Tap “تسجيل الموقع” and enter configured location | Store location; ask for key hook |
| Awaiting key hook | Send key-hook number; confirm parked | Validate occupancy; mark PARKED; release parking task |

The complete valet interaction contract after intake (shift readiness, breaks, offers, retrieval, ready, code verification, physical handover, help) is ADR-0006, approved 15 Nov 2026. Platform facts verified against Meta documentation on 15 Nov 2026 are recorded in `11_WhatsApp_Platform_Verification.md`.

Keep each prompt tied to ticket ID and explicit interaction context. Do not infer a phone, plate or key hook just because a message is numeric. Always offer correction/cancel/back where safe. Pending drafts must not silently consume unrelated messages.

During intake, photos belong to that ticket. Outside intake, attach to an explicitly selected open incident; if multiple incidents exist, ask which one. Do not attach to an arbitrary “latest incident”. File validation, size limits and malware/content-type checks are implementation requirements.

If photos or descriptors are missing, a controlled exception records why and who authorized it. The default is four photos before movement; never label an upload time as verified capture time.

## Guest ticket and action security
- A ticket action carries a high-entropy opaque reference bound to ticket, guest-binding revision, action and validity. Store a verifier rather than exposing internal IDs as authorization.
- Validate sender identity against the binding and current provider identity semantics. Do not assume the provider always supplies a raw phone number in the same field forever. Verified 15 Nov 2026: inbound messages always carry a business-scoped user ID (`from_user_id`) while the phone (`from`) may be omitted for username users; bindings store both and match on either, recording how the match was established.
- A forwarded ticket/button from another account cannot authorize retrieval. Log an identity exception without revealing the real owner's data.
- If a number is corrected, revoke all old ticket-action references and collection-code verifiers, audit old/new masked values and reissue to the confirmed guest. Previously sent messages cannot be assumed deleted.
- A generic request from a phone with multiple active tickets must show an explicit selection.
- Human fallback exists for no phone/WhatsApp, message failure or lost access. Never grant access based only on guessing a display number.

## Message catalogue (draft copy)
Arabic is default. Preserve the guest's selected language; English is supported. Arabic copy is short, calm and service-focused. Variables are examples; never hard-code sample data.

| Trigger | Arabic | English |
|---|---|---|
| Registered | أهلاً بك في سلّمها. تذكرة مركبتك رقم {ticket} لدى {venue}. سنخبرك عند اكتمال الركن. اطلب مركبتك من هنا عندما تستعد للمغادرة. | Welcome to Sallimha. Your vehicle ticket is {ticket} at {venue}. We will confirm when parking is complete. Request your car here when you are ready to leave. |
| Request button | اطلب سيارتي | Request my car |
| Parked | تم ركن مركبتك. تذكرتك {ticket}. | Your car is parked. Ticket {ticket}. |
| Early request | استلمنا طلبك. يجري استكمال ركن المركبة، وسنتابع طلب الإحضار فور جاهزيتها. | Request received. Parking is still being completed. Retrieval will proceed as soon as the vehicle is ready. |
| Queued | استلمنا طلبك لتذكرة {ticket}. طلبك في الانتظار، وسنخبرك عند بدء الإحضار. | Request received for ticket {ticket}. You are in the queue. We will notify you when retrieval starts. |
| Accepted | جارٍ إحضار مركبتك. سنخبرك عند وصولها إلى نقطة التسليم. | Your car is being retrieved. We will notify you when it reaches the pickup point. |
| Ready | مركبتك جاهزة عند {pickup_point}. أظهر رمز الاستلام {code} للموظف عند التسليم. | Your car is ready at {pickup_point}. Show collection code {code} to the attendant at handover. |
| Delivered/rating | تم تسليم مركبتك. رافقتك السلامة. كيف كانت خدمتنا؟ | Your vehicle has been handed over. Safe travels. How was our service? |
| Rating options | ممتازة / عادية / سيئة | Excellent / Okay / Poor |
| Poor rating acknowledgement | نأسف لأن التجربة لم تكن بالمستوى المطلوب. أبلغنا المشرف بمتابعة ملاحظتك. | We are sorry the experience fell short. The supervisor has been notified to follow up. |
| Duplicate request | طلبك مسجل بالفعل. الحالة الحالية: {status}. | Your request is already recorded. Current status: {status}. |
| Stale staff action | هذه المهمة لم تعد مسندة إليك. راجع مهمتك الحالية قبل تحريك المركبة. | This task is no longer assigned to you. Check your current task before moving the vehicle. |
| Ticket cancelled (intake abandoned) | تم إلغاء تذكرة {ticket}. إن كان لديك استفسار فتواصل مع فريق الخدمة. | Ticket {ticket} has been cancelled. Please contact the service team if you have any questions. |
| Request withdrawn by supervisor | أُلغي طلب إحضار مركبتك لتذكرة {ticket}، ومركبتك ما زالت مركونة بأمان. يمكنك طلبها مجددًا متى شئت. | Your retrieval request for ticket {ticket} was withdrawn. Your car is still safely parked; you can request it again any time. |

## Guest receipt and ownership
Confirming receipt at intake means the person at the counter has the correct ticket on their phone; a delivery callback alone is insufficient. Staff should visually match event/ticket and vehicle, without reading unrelated private messages.

The proposed collection code is created for READY, rotated if necessary, rate-limited to five failed attempts per ticket before supervisor review, and invalidated after delivery. Do not show it in a retrieval offer or normal staff list. Server validation is authoritative. A verified code authorizes handover eligibility; only the staff's final physical-delivery confirmation closes the ticket.

## Correction and assistance
Ordinary input correction before sending can be handled by the receiving valet. After a ticket has been sent, a phone-binding correction requires supervisor verification as a proposed default because it changes who may request a vehicle. Reissue and revoke rather than merely editing a display field.

Keep a visible help route in guest messages or the business profile. The requested service is transactional; collecting a phone number does not authorize marketing campaigns.

