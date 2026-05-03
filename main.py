from fastapi import FastAPI
from typing import Dict, Any
from bot import compose

app = FastAPI()

# ── In-memory storage ──────────────────────────────────────────────────────────
CATEGORIES: Dict[str, Any] = {}
MERCHANTS:  Dict[str, Any] = {}
TRIGGERS:   Dict[str, Any] = {}
CUSTOMERS:  Dict[str, Any] = {}


# ══════════════════════════════════════════════════════════════════════════════
# ROOT
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/")
def home():
    return {
        "message": "Magicpin AI Bot — Vera is live 🚀",
        "endpoints": ["/v1/healthz", "/v1/metadata", "/v1/context", "/v1/tick", "/v1/reply"],
    }


# ══════════════════════════════════════════════════════════════════════════════
# HEALTH CHECK
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/v1/healthz")
def healthz():
    return {"status": "ok"}


# ══════════════════════════════════════════════════════════════════════════════
# METADATA
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/v1/metadata")
def metadata():
    return {
        "team_name":   "Trisita_AI",
        "model":       "openrouter",
        "description": "LLM-powered merchant engagement bot with contextual trigger-based messaging",
        "capabilities": [
            "trigger-based messaging",
            "merchant personalization",
            "category-aware tone",
            "from_role branching (merchant vs customer)",
            "auto-reply detection",
            "hostility / STOP handling",
            "slot-pick customer replies",
        ],
    }


# ══════════════════════════════════════════════════════════════════════════════
# CONTEXT INGESTION
# ══════════════════════════════════════════════════════════════════════════════
@app.post("/v1/context")
def context(data: Dict[str, Any]):
    scope   = data["scope"]
    cid     = data["context_id"]
    payload = data["payload"]

    if scope == "category":
        CATEGORIES[cid] = payload
    elif scope == "merchant":
        MERCHANTS[cid] = payload
    elif scope == "trigger":
        TRIGGERS[cid] = payload
    elif scope == "customer":
        CUSTOMERS[cid] = payload

    return {"accepted": True}


# ══════════════════════════════════════════════════════════════════════════════
# TICK  — main scoring / trigger processing
# ══════════════════════════════════════════════════════════════════════════════
@app.post("/v1/tick")
def tick(data: Dict[str, Any]):
    actions = []

    for tid in data.get("available_triggers", []):
        trigger  = TRIGGERS.get(tid)
        if not trigger:
            continue

        mid      = trigger.get("merchant_id")
        merchant = MERCHANTS.get(mid)
        if not merchant:
            continue

        category = CATEGORIES.get(merchant.get("category_slug"))
        if not category:
            continue

        customer = None
        cid = trigger.get("customer_id")
        if cid:
            customer = CUSTOMERS.get(cid)

        action = compose(category, merchant, trigger, customer)
        action.update({
            "merchant_id": mid,
            "trigger_id":  tid,
            "customer_id": cid,
        })
        actions.append(action)

    return {"actions": actions}


# ══════════════════════════════════════════════════════════════════════════════
# REPLY HANDLER
# Key fix: branch on from_role — "customer" vs "merchant"
# ══════════════════════════════════════════════════════════════════════════════

# Patterns that indicate an automated / out-of-office response
AUTO_REPLY_PATTERNS = [
    "thank you for contacting",
    "thanks for contacting",
    "will respond shortly",
    "we will get back",
    "we'll get back",
    "out of office",
    "auto reply",
    "auto-reply",
    "automatic response",
    "not available right now",
    "currently unavailable",
    "on leave",
    "away from",
    "do not reply",
    "do not respond",
    "noreply",
    "no-reply",
    "this is an automated",
    "automated message",
    "dhanyavaad aapke",          # Hindi auto-reply variants
    "hum jald hi",
    "jald sampark karenge",
]

# Patterns that mean the user wants to stop
STOP_PATTERNS = [
    "stop", "spam", "unsubscribe", "remove me", "don't contact",
    "mat karo", "band karo", "bhejo mat", "nahin chahiye", "nahi chahiye",
    "opt out", "block",
]

# Customer booking / time signals
BOOKING_SIGNALS = [
    "book", "slot", "appointment", "schedule", "fix", "confirm",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "aaj", "kal", "parso", "today", "tomorrow",
    "morning", "evening", "noon", "afternoon", "night",
    "am", "pm", "baje", "o'clock",
    "nov", "dec", "jan", "feb", "mar", "apr", "may", "jun",
    "jul", "aug", "sep", "oct",
]

# Customer yes / affirmative signals
AFFIRMATIVE_SIGNALS = [
    "yes", "ok", "okay", "sure", "please", "confirm", "go ahead",
    "haan", "ha", "bilkul", "zaroor", "theek", "theek hai",
    "sounds good", "let's do", "lets do", "do it",
]

# Customer question signals
QUESTION_SIGNALS = [
    "how much", "kitna", "price", "cost", "charges", "fees", "rate",
    "available", "open", "timing", "time", "kab", "kaise", "kya",
    "when", "where", "which", "what", "kyun", "why",
]

# Merchant commitment signals
MERCHANT_COMMIT = [
    "ok", "okay", "yes", "haan", "bilkul", "let's", "lets",
    "do it", "proceed", "karo", "kar do", "bana do", "draft",
    "next", "what next", "aage", "go", "send", "push",
]

# Merchant question / hesitation signals
MERCHANT_QUESTION = [
    "kya", "kaisa", "kaise", "kyun", "why", "how", "what", "when",
    "samajh", "explain", "doubt", "confused", "sure", "really",
    "sach", "matlab", "iska", "isse", "will it", "kya hoga",
]


def _contains_any(text: str, patterns: list) -> bool:
    return any(p in text for p in patterns)


@app.post("/v1/reply")
def reply(data: Dict[str, Any]):
    raw_msg     = data.get("message", "")
    msg         = raw_msg.lower().strip()
    from_role   = data.get("from_role", "merchant")   # "merchant" | "customer"
    merchant_id = data.get("merchant_id", "")
    merchant    = MERCHANTS.get(merchant_id, {})
    merchant_name = (
        merchant.get("identity", {}).get("name", "the clinic")
        if merchant else "the clinic"
    )

    # ── 1. Auto-reply detection (applies regardless of role) ───────────────────
    if _contains_any(msg, AUTO_REPLY_PATTERNS):
        return {"action": "end"}

    # ── 2. STOP / hostile (applies regardless of role) ────────────────────────
    if _contains_any(msg, STOP_PATTERNS):
        return {"action": "end"}

    # ══════════════════════════════════════════════════════════════════════════
    # CUSTOMER BRANCH
    # Replies must be addressed TO the customer, customer-voiced, helpful
    # ══════════════════════════════════════════════════════════════════════════
    if from_role == "customer":

        # 2a. Booking / slot intent
        if _contains_any(msg, BOOKING_SIGNALS):
            return {
                "action":   "send",
                "body": (
                    f"✅ Done! Your appointment request has been noted.\n\n"
                    f"{merchant_name} will confirm your exact slot shortly — "
                    f"usually within the hour. Please keep your phone handy.\n\n"
                    f"Is there anything specific you'd like the doctor to know before your visit?"
                ),
                "cta":      "open_ended",
                "send_as":  "vera",
            }

        # 2b. Price / availability question
        if _contains_any(msg, QUESTION_SIGNALS) or "?" in raw_msg:
            return {
                "action":   "send",
                "body": (
                    f"Great question! {merchant_name} will be able to give you exact details.\n\n"
                    f"Would you like me to flag this for them so they can reply to you quickly? "
                    f"Just say Yes and I'll notify them right away."
                ),
                "cta":      "yes_no",
                "send_as":  "vera",
            }

        # 2c. Affirmative / yes from customer
        if _contains_any(msg, AFFIRMATIVE_SIGNALS):
            return {
                "action":   "send",
                "body": (
                    f"Perfect! {merchant_name} will reach out to you shortly to confirm everything.\n\n"
                    f"What time of day works best for you — morning, afternoon, or evening?"
                ),
                "cta":      "slot_pick",
                "send_as":  "vera",
            }

        # 2d. Negative / not interested
        if _contains_any(msg, ["no", "nahi", "nahin", "nope", "not now", "abhi nahi", "later", "baad me"]):
            return {
                "action":   "send",
                "body": (
                    f"No problem at all! Whenever you're ready, {merchant_name} is here. "
                    f"Feel free to reach out anytime. 😊"
                ),
                "cta":      "none",
                "send_as":  "vera",
            }

        # 2e. Default customer fallback
        return {
            "action":   "send",
            "body": (
                f"Thanks for your message! {merchant_name} will get back to you soon.\n\n"
                f"In the meantime, can I help you book an appointment or answer any questions?"
            ),
            "cta":      "open_ended",
            "send_as":  "vera",
        }

    # ══════════════════════════════════════════════════════════════════════════
    # MERCHANT BRANCH
    # Replies are operational — push merchant toward action
    # ══════════════════════════════════════════════════════════════════════════

    # 3a. Merchant commits / says yes
    if _contains_any(msg, MERCHANT_COMMIT):
        return {
            "action":   "send",
            "body": (
                "Perfect — drafting your optimized post + offer right now. "
                "30 seconds ⏳\n\n"
                "Ek baar ready ho jaye toh aap directly approve karke live push kar sakte hain. "
                "Koi changes chahiye ho toh woh bhi kar denge."
            ),
            "cta":      "approve_draft",
            "send_as":  "vera",
        }

    # 3b. Merchant asks a question / hesitates
    if _contains_any(msg, MERCHANT_QUESTION) or "?" in raw_msg:
        return {
            "action":   "send",
            "body": (
                "Bilkul valid question hai — quickly explain karta hoon.\n\n"
                "Aapke current CTR data aur category benchmarks dekh ke yeh ek high-ROI move hai. "
                "Sirf listing copy + visual change hai — koi extra budget nahi lagega.\n\n"
                "Proceed karoon? ✅ / ❌"
            ),
            "cta":      "yes_no",
            "send_as":  "vera",
        }

    # 3c. Merchant says no / not interested
    if _contains_any(msg, ["no", "nahi", "nahin", "nope", "not now", "abhi nahi", "baad me", "later"]):
        return {
            "action":   "send",
            "body": (
                "Understood! Koi pressure nahi. 🙏\n\n"
                "Jab bhi ready ho, main hoon. "
                "Tab tak aapki listing monitor karti rehungi."
            ),
            "cta":      "none",
            "send_as":  "vera",
        }

    # 3d. Merchant sends off-topic / context info (e.g. X-ray setup, equipment)
    if len(msg.split()) > 4:
        return {
            "action":   "send",
            "body": (
                "Got it — noted that context. 📝\n\n"
                "Main is information ko dhyan me rakh ke aapke liye ek targeted plan draft karti hoon. "
                "Kuch aur add karna ho toh batayein, warna main draft shuru karti hoon.\n\n"
                "Proceed karoon?"
            ),
            "cta":      "yes_no",
            "send_as":  "vera",
        }

    # 3e. Default merchant fallback — wait for clearer signal
    return {
        "action":       "wait",
        "wait_seconds": 5,
    }