"""Bilingual message catalogue (docs/04, ADR-0006). Draft copy — not Meta-approved templates.

Changing wording never changes behaviour: buttons carry opaque action payloads, and the
button *key* (not its title) is what the outbox stores (AT-47). Titles are ≤ 20 characters.
"""

MESSAGES: dict[str, dict[str, str]] = {
    # --- Guest -----------------------------------------------------------------------------
    "guest.ticket": {
        "ar": "أهلاً بك في سلّمها. تذكرة مركبتك رقم {ticket} لدى {venue}. سنخبرك عند اكتمال الركن. "
        "اطلب مركبتك من هنا عندما تستعد للمغادرة.",
        "en": "Welcome to Sallimha. Your vehicle ticket is {ticket} at {venue}. We will confirm when parking "
        "is complete. Request your car here when you are ready to leave.",
    },
    "guest.parked": {"ar": "تم ركن مركبتك. تذكرتك {ticket}.", "en": "Your car is parked. Ticket {ticket}."},
    "guest.early_request": {
        "ar": "استلمنا طلبك. يجري استكمال ركن المركبة، وسنتابع طلب الإحضار فور جاهزيتها.",
        "en": "Request received. Parking is still being completed. Retrieval will proceed as soon as the vehicle "
        "is ready.",
    },
    "guest.queued": {
        "ar": "استلمنا طلبك لتذكرة {ticket}. طلبك في الانتظار، وسنخبرك عند بدء الإحضار.",
        "en": "Request received for ticket {ticket}. You are in the queue. We will notify you when retrieval starts.",
    },
    "guest.accepted": {
        "ar": "جارٍ إحضار مركبتك. سنخبرك عند وصولها إلى نقطة التسليم.",
        "en": "Your car is being retrieved. We will notify you when it reaches the pickup point.",
    },
    "guest.ready": {
        "ar": "مركبتك جاهزة عند {pickup_point}. أظهر رمز الاستلام {code} للموظف عند التسليم.",
        "en": "Your car is ready at {pickup_point}. Show collection code {code} to the attendant at handover.",
    },
    "guest.delivered": {
        "ar": "تم تسليم مركبتك. رافقتك السلامة. كيف كانت خدمتنا؟",
        "en": "Your vehicle has been handed over. Safe travels. How was our service?",
    },
    "guest.poor_ack": {
        "ar": "نأسف لأن التجربة لم تكن بالمستوى المطلوب. أبلغنا المشرف بمتابعة ملاحظتك.",
        "en": "We are sorry the experience fell short. The supervisor has been notified to follow up.",
    },
    "guest.thanks": {"ar": "شكرًا لتقييمك.", "en": "Thank you for your feedback."},
    "guest.duplicate": {
        "ar": "طلبك مسجل بالفعل. الحالة الحالية: {status}.",
        "en": "Your request is already recorded. Current status: {status}.",
    },
    "guest.select_ticket": {
        "ar": "لديك أكثر من تذكرة نشطة. اختر المركبة المطلوبة:",
        "en": "You have more than one active ticket. Choose the vehicle:",
    },
    "guest.cancelled": {
        "ar": "تم إلغاء تذكرة {ticket}. إن كان لديك استفسار فتواصل مع فريق الخدمة.",
        "en": "Ticket {ticket} has been cancelled. Please contact the service team if you have any questions.",
    },
    "guest.withdrawn": {
        "ar": "أُلغي طلب إحضار مركبتك لتذكرة {ticket}، ومركبتك ما زالت مركونة بأمان. يمكنك طلبها مجددًا متى شئت.",
        "en": "Your retrieval request for ticket {ticket} was withdrawn. Your car is still safely parked; you can "
        "request it again any time.",
    },
    "guest.not_authorized": {
        "ar": "لا يمكن تنفيذ هذا الطلب من هذا الرقم. للمساعدة تواصل مع فريق الخدمة في الموقع.",
        "en": "This request cannot be made from this number. Please ask the service team on site for help.",
    },
    "guest.help": {
        "ar": "للمساعدة تواصل مع فريق الخدمة في الموقع، أو اطلب مركبتك من رسالة التذكرة.",
        "en": "For help, speak to the service team on site, or request your car from your ticket message.",
    },
    "guest.no_active_ticket": {
        "ar": "لا توجد تذكرة نشطة مرتبطة بهذا الرقم. للمساعدة تواصل مع فريق الخدمة.",
        "en": "There is no active ticket linked to this number. Please ask the service team for help.",
    },
    # --- Valet -----------------------------------------------------------------------------
    "valet.shift_started": {
        "ar": "بدأت مناوبتك في {event}. هل أنت جاهز لاستقبال المهام؟",
        "en": "Your shift at {event} has started. Are you ready to receive tasks?",
    },
    "valet.available_ok": {"ar": "أنت الآن متاح لاستقبال المهام.", "en": "You are now available for tasks."},
    "valet.unavailable_ok": {"ar": "تم تسجيلك غير متاح. اضغط «جاهز» عند العودة.", "en": "You are marked unavailable. "
                             "Tap “Ready” when you are back."},
    "valet.break_pending": {
        "ar": "ستبدأ استراحتك بعد إنهاء مهمتك الحالية.",
        "en": "Your break will start after you finish your current task.",
    },
    "valet.not_on_shift": {
        "ar": "لا توجد لديك مناوبة نشطة. تواصل مع المشرف.",
        "en": "You do not have an active shift. Please contact your supervisor.",
    },
    "valet.busy": {
        "ar": "لديك مهمة جارية لتذكرة {ticket}. أنهِها أولاً.",
        "en": "You have a task in progress for ticket {ticket}. Finish it first.",
    },
    "valet.ask_phone": {
        "ar": "تذكرة جديدة {ticket}. أرسل رقم جوال الضيف مع رمز الدولة.",
        "en": "New ticket {ticket}. Send the guest's phone number with country code.",
    },
    "valet.phone_invalid": {
        "ar": "الرقم غير صحيح. أرسل رقم جوال الضيف مع رمز الدولة.",
        "en": "That number is not valid. Send the guest's phone number with country code.",
    },
    "valet.confirm_phone": {
        "ar": "تذكرة {ticket}: هل الرقم {masked} صحيح؟ سيستلم الضيف تذكرته وتحديثات الخدمة عليه.",
        "en": "Ticket {ticket}: is {masked} correct? The guest will receive their ticket and service updates there.",
    },
    "valet.ask_receipt": {
        "ar": "تذكرة {ticket}: هل ظهرت التذكرة على جوال الضيف؟",
        "en": "Ticket {ticket}: has the ticket appeared on the guest's phone?",
    },
    "valet.receipt_unconfirmed": {
        "ar": "سُجّل أن الضيف لم يستلم التذكرة؛ سيظهر ذلك للمشرف. أكمل الاستلام.",
        "en": "Recorded that the guest has not received the ticket; the supervisor will see it. Continue intake.",
    },
    "valet.ask_vehicle": {
        "ar": "تذكرة {ticket}: أرسل رقم اللوحة ووصفًا مختصرًا (اختياري)، مثال: ABC 1234 كامري بيضاء.",
        "en": "Ticket {ticket}: send the plate and an optional short description, e.g. ABC 1234 white Camry.",
    },
    "valet.ask_photos": {
        "ar": "تذكرة {ticket}: أرسل ٤ صور للمركبة (أمام، يمين، خلف، يسار) قبل تحريكها.",
        "en": "Ticket {ticket}: send 4 photos of the vehicle (front, right, rear, left) before moving it.",
    },
    "valet.photo_count": {
        "ar": "تذكرة {ticket}: استلمنا {count} من ٤ صور.",
        "en": "Ticket {ticket}: {count} of 4 photos received.",
    },
    "valet.ready_to_park": {
        "ar": "تذكرة {ticket}: اكتملت الصور. اضغط «بدء الركن» قبل تحريك المركبة.",
        "en": "Ticket {ticket}: photos complete. Tap “Start parking” before moving the vehicle.",
    },
    "valet.ask_location": {
        "ar": "تذكرة {ticket}: أين ركنت المركبة؟ أرسل رمز المنطقة ثم الموقع، مثال: A 12. المناطق: {zones}",
        "en": "Ticket {ticket}: where is the car parked? Send the zone code then the spot, e.g. A 12. Zones: {zones}",
    },
    "valet.location_invalid": {
        "ar": "رمز المنطقة غير معروف. المناطق: {zones}",
        "en": "Unknown zone code. Zones: {zones}",
    },
    "valet.ask_hook": {
        "ar": "تذكرة {ticket}: أرسل رقم خطاف المفتاح.",
        "en": "Ticket {ticket}: send the key hook number.",
    },
    "valet.hook_invalid": {
        "ar": "رقم الخطاف غير صحيح أو مشغول. أرسل رقمًا آخر.",
        "en": "That hook number is invalid or occupied. Send another number.",
    },
    "valet.parked_done": {
        "ar": "تم الركن — تذكرة {ticket}، {location}، المفتاح {hook}. شكرًا.",
        "en": "Parked — ticket {ticket}, {location}, key {hook}. Thank you.",
    },
    "valet.offer": {
        "ar": "مهمة إحضار — تذكرة {ticket}. {vehicle}. الموقع {location}، المفتاح {hook}. ينتهي العرض {expires}.",
        "en": "Retrieval task — ticket {ticket}. {vehicle}. Location {location}, key {hook}. Offer expires {expires}.",
    },
    "valet.assigned": {
        "ar": "تم إسنادها إليك. أحضر المفتاح والمركبة، ثم اضغط «السيارة جاهزة» عند نقطة التسليم.",
        "en": "Assigned to you. Fetch the key and the car, then tap “Car ready” at the pickup point.",
    },
    "valet.offer_released": {"ar": "تم تسجيل اعتذارك.", "en": "Declined."},
    "valet.ask_code": {
        "ar": "تذكرة {ticket}: اطلب من الضيف رمز الاستلام وأرسله هنا.",
        "en": "Ticket {ticket}: ask the guest for the collection code and send it here.",
    },
    "valet.code_ok": {
        "ar": "الرمز صحيح لتذكرة {ticket} — {vehicle}. سلّم المركبة ثم اضغط «تم التسليم».",
        "en": "Code correct for ticket {ticket} — {vehicle}. Hand over the car, then tap “Delivered”.",
    },
    "valet.code_wrong": {
        "ar": "الرمز غير صحيح. المحاولات المتبقية: {remaining}.",
        "en": "Incorrect code. Attempts remaining: {remaining}.",
    },
    "valet.code_locked": {
        "ar": "تم إيقاف التحقق لهذه التذكرة. لا تسلّم المركبة — تواصل مع المشرف.",
        "en": "Verification is locked for this ticket. Do not hand over the car — contact the supervisor.",
    },
    "valet.delivered_done": {"ar": "تم التسليم لتذكرة {ticket}. شكرًا.", "en": "Ticket {ticket} delivered. Thank you."},
    "valet.handover_blocked": {
        "ar": "التسليم موقوف لهذه التذكرة. لا تسلّم المركبة — تواصل مع المشرف.",
        "en": "Handover is on hold for this ticket. Do not hand over the car — contact the supervisor.",
    },
    "valet.stale": {
        "ar": "هذه المهمة لم تعد مسندة إليك. راجع مهمتك الحالية قبل تحريك المركبة.",
        "en": "This task is no longer assigned to you. Check your current task before moving the vehicle.",
    },
    "valet.duplicate": {"ar": "تم تسجيل ذلك مسبقًا.", "en": "That was already recorded."},
    "valet.praise": {
        "ar": "قيّم ضيف تذكرة {ticket} الخدمة بأنها ممتازة. أحسنت!",
        "en": "The guest on ticket {ticket} rated the service excellent. Well done!",
    },
    "valet.custody_assigned": {
        "ar": "نُقلت إليك عهدة تذكرة {ticket}. المركبة: {vehicle_location}. المفتاح: {key_location}. أكّد الاستلام.",
        "en": "Custody of ticket {ticket} was transferred to you. Car: {vehicle_location}. Key: {key_location}. "
        "Confirm receipt.",
    },
    "valet.custody_released": {
        "ar": "حُلّت عهدة تذكرة {ticket} وأصبحت المهمة منتهية بالنسبة لك.",
        "en": "Custody of ticket {ticket} has been resolved; the task is closed for you.",
    },
    "valet.help": {
        "ar": "مهمتك الحالية: {current}. للأوامر: «مركبة جديدة»، «جاهز»، «استراحة». للمساعدة تواصل مع المشرف.",
        "en": "Current task: {current}. Commands: “New car”, “Ready”, “Break”. For help contact your supervisor.",
    },
    "valet.unknown_input": {
        "ar": "لم أفهم. اختر من الأزرار، أو أرسل «مساعدة».",
        "en": "I did not understand. Use the buttons, or send “Help”.",
    },
    "valet.cancelled": {
        "ar": "أُلغيت تذكرة {ticket} وأُنهيت مهمة الاستلام.",
        "en": "Ticket {ticket} was cancelled and the intake task closed.",
    },
}

BUTTONS: dict[str, dict[str, str]] = {
    "request_car": {"ar": "اطلب سيارتي", "en": "Request my car"},
    "rate_excellent": {"ar": "ممتازة", "en": "Excellent"},
    "rate_okay": {"ar": "عادية", "en": "Okay"},
    "rate_poor": {"ar": "سيئة", "en": "Poor"},
    "ready": {"ar": "جاهز", "en": "Ready"},
    "unavailable": {"ar": "غير متاح", "en": "Unavailable"},
    "confirm_phone": {"ar": "تأكيد الرقم", "en": "Confirm number"},
    "edit_phone": {"ar": "تعديل الرقم", "en": "Edit number"},
    "receipt_yes": {"ar": "نعم، استلمها", "en": "Yes, received"},
    "receipt_no": {"ar": "لم تصل", "en": "Not received"},
    "start_parking": {"ar": "بدء الركن", "en": "Start parking"},
    "accept": {"ar": "قبول", "en": "Accept"},
    "decline": {"ar": "اعتذار", "en": "Decline"},
    "car_ready": {"ar": "السيارة جاهزة", "en": "Car ready"},
    "delivered": {"ar": "تم التسليم", "en": "Delivered"},
    "ack_custody": {"ar": "استلمت العهدة", "en": "Custody received"},
    "select_ticket": {"ar": "تذكرة {ticket}", "en": "Ticket {ticket}"},
}

REQUEST_STATUS = {
    "WAITING_FOR_PARKING": {"ar": "يجري استكمال الركن", "en": "parking still in progress"},
    "QUEUED": {"ar": "في الانتظار", "en": "in the queue"},
    "OFFERED": {"ar": "في الانتظار", "en": "in the queue"},
    "ACCEPTED": {"ar": "جارٍ الإحضار", "en": "being retrieved"},
    "READY": {"ar": "جاهزة عند نقطة التسليم", "en": "ready at the pickup point"},
}


def render_text(template: str, language: str, params: dict) -> str:
    entry = MESSAGES[template]
    return entry.get(language, entry["ar"]).format(**params)


def button_title(key: str, language: str, params: dict | None = None) -> str:
    entry = BUTTONS[key]
    return entry.get(language, entry["ar"]).format(**(params or {}))
