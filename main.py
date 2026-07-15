"""
main.py — Vera HTTP server
Implements all 5 judge endpoints per the testing-brief specification.
"""

import os
import time
import uuid
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv
from groq import Groq

from bot import compose

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Vera — magicpin Merchant AI", version="2.0.0")

START_TIME = time.time()

# ── In-memory stores ───────────────────────────────────────────────────────────
# (scope, context_id) → {version: int, payload: dict}
CONTEXTS: Dict[tuple, Dict[str, Any]] = {}

# conversation_id → {merchant_id, trigger_id, customer_id, history: [{role, body}]}
CONVERSATIONS: Dict[str, Dict[str, Any]] = {}

# suppression_key → bool (to avoid duplicate sends)
SENT_SUPPRESSIONS: set = set()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_payload(scope: str, context_id: str) -> Optional[Dict]:
    entry = CONTEXTS.get((scope, context_id))
    return entry["payload"] if entry else None

def _count_contexts() -> Dict[str, int]:
    counts = {"category": 0, "merchant": 0, "customer": 0, "trigger": 0}
    for (scope, _) in CONTEXTS:
        if scope in counts:
            counts[scope] += 1
    return counts

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ══════════════════════════════════════════════════════════════════════════════
# GET /v1/healthz
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/v1/healthz")
def healthz():
    return {
        "status":          "ok",
        "uptime_seconds":  int(time.time() - START_TIME),
        "contexts_loaded": _count_contexts(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# GET /v1/metadata
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/v1/metadata")
def metadata():
    return {
        "team_name":    "Trisita_AI",
        "team_members": ["Trisita Ghosh"],
        "model":        "llama-3.3-70b-versatile (Groq)",
        "approach":     (
            "Groq LLM composer with structured 4-context prompt targeting all 5 rubric dimensions. "
            "Rule-based fallback for reliability. Context-aware multi-turn reply handler."
        ),
        "contact_email":  "",
        "version":        "2.0.0",
        "submitted_at":   _now_iso(),
        "capabilities": [
            "llm-composed messages with category voice matching",
            "hindi-english code-mix detection",
            "trigger-specific composition (6+ trigger kinds)",
            "multi-turn context-aware reply",
            "auto-reply detection (EN + HI patterns)",
            "stop/unsubscribe handling",
            "version-idempotent context ingestion",
            "suppression dedup",
        ],
    }


# ══════════════════════════════════════════════════════════════════════════════
# POST /v1/context  — receive a context push
# ══════════════════════════════════════════════════════════════════════════════
@app.post("/v1/context")
def push_context(data: Dict[str, Any]):
    scope      = data.get("scope", "")
    context_id = data.get("context_id", "")
    version    = data.get("version", 1)
    payload    = data.get("payload", {})

    if scope not in ("category", "merchant", "customer", "trigger"):
        return {"accepted": False, "reason": "invalid_scope", "details": f"Unknown scope: {scope}"}

    key = (scope, context_id)
    existing = CONTEXTS.get(key)

    # Idempotency: reject stale version
    if existing and existing["version"] >= version:
        return {
            "accepted":        False,
            "reason":          "stale_version",
            "current_version": existing["version"],
        }

    CONTEXTS[key] = {"version": version, "payload": payload}

    return {
        "accepted":   True,
        "ack_id":     f"ack_{context_id}_v{version}",
        "stored_at":  _now_iso(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# POST /v1/tick  — periodic wake-up; bot initiates messages
# ══════════════════════════════════════════════════════════════════════════════
@app.post("/v1/tick")
def tick(data: Dict[str, Any]):
    available_triggers: List[str] = data.get("available_triggers", [])
    actions = []

    for tid in available_triggers:
        trigger = _get_payload("trigger", tid)
        if not trigger:
            continue

        mid      = trigger.get("merchant_id")
        merchant = _get_payload("merchant", mid)
        if not merchant:
            continue

        cat_slug = merchant.get("category_slug")
        category = _get_payload("category", cat_slug)
        if not category:
            continue

        cid      = trigger.get("customer_id")
        customer = _get_payload("customer", cid) if cid else None

        # Suppression check
        suppression_key = trigger.get("suppression_key", "")
        if suppression_key and suppression_key in SENT_SUPPRESSIONS:
            continue

        try:
            result = compose(category, merchant, trigger, customer)
        except Exception as exc:
            logger.error("compose() failed for trigger %s: %s", tid, exc)
            continue

        if not result.get("body"):
            continue

        # Track suppression
        if suppression_key:
            SENT_SUPPRESSIONS.add(suppression_key)

        conversation_id = f"conv_{mid}_{tid}_{uuid.uuid4().hex[:8]}"

        # Store conversation state for context-aware replies
        CONVERSATIONS[conversation_id] = {
            "merchant_id":  mid,
            "trigger_id":   tid,
            "customer_id":  cid,
            "cat_slug":     cat_slug,
            "history":      [{"role": "vera", "body": result["body"]}],
            "last_cta":     result.get("cta", ""),
        }

        # Build WhatsApp template params from merchant name + trigger kind
        merchant_name = merchant.get("identity", {}).get("name", "Merchant")
        trigger_kind  = trigger.get("kind", "general")
        template_name = f"vera_{trigger_kind}_v1"
        template_params = [
            merchant_name,
            trigger_kind.replace("_", " ").title(),
            result.get("cta", ""),
        ]

        actions.append({
            "conversation_id":  conversation_id,
            "merchant_id":      mid,
            "customer_id":      cid,
            "send_as":          result.get("send_as", "vera"),
            "trigger_id":       tid,
            "template_name":    template_name,
            "template_params":  template_params,
            "body":             result["body"],
            "cta":              result.get("cta", "open_ended"),
            "suppression_key":  suppression_key,
            "rationale":        result.get("rationale", ""),
        })

    return {"actions": actions}


# ══════════════════════════════════════════════════════════════════════════════
# Auto-reply / STOP detection patterns
# ══════════════════════════════════════════════════════════════════════════════

AUTO_REPLY_PATTERNS = [
    "thank you for contacting", "thanks for contacting",
    "will respond shortly", "we will get back", "we'll get back",
    "out of office", "auto reply", "auto-reply", "automatic response",
    "not available right now", "currently unavailable", "on leave",
    "away from", "do not reply", "do not respond",
    "noreply", "no-reply", "this is an automated", "automated message",
    "dhanyavaad aapke", "hum jald hi", "jald sampark karenge",
    "main ek automated", "yeh ek automated",
]

STOP_PATTERNS = [
    "stop", "spam", "unsubscribe", "remove me",
    "don't contact", "mat karo", "band karo",
    "bhejo mat", "nahin chahiye", "nahi chahiye",
    "opt out", "block",
]

def _contains_any(text: str, patterns: list) -> bool:
    return any(p in text for p in patterns)


# ══════════════════════════════════════════════════════════════════════════════
# LLM-powered reply composer
# ══════════════════════════════════════════════════════════════════════════════

REPLY_SYSTEM_PROMPT = """You are Vera, magicpin's AI merchant assistant on WhatsApp.
You are continuing a conversation with a merchant (or customer). You have the full context.

Your job is to produce the NEXT reply in the conversation.

Rules:
- Stay on the original topic (the trigger that started this conversation)
- If merchant says yes/ok/proceed → immediately take action, don't ask qualifying questions again
- If merchant asks a question → answer it briefly using their specific data, then re-offer the action
- If merchant says no/not now → acknowledge politely, offer to check back later, then end gracefully
- Keep responses SHORT — 2-4 sentences max for follow-up turns
- Hindi-English mix if merchant prefers Hindi
- Always include a rationale field
- Determine action: "send" | "wait" | "end"

Output ONLY valid JSON:
{
  "action": "send" | "wait" | "end",
  "body": "the reply text (only if action=send)",
  "cta": "yes_no | open_ended | approve_draft | none (only if action=send)",
  "wait_seconds": 1800,
  "rationale": "why this response"
}"""


def _compose_reply_with_groq(
    conversation: Dict[str, Any],
    merchant_message: str,
    merchant: Dict[str, Any],
    category: Dict[str, Any],
) -> Optional[Dict]:
    """Use Groq to compose a context-aware multi-turn reply."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None

    try:
        client = Groq(api_key=api_key)

        # Build history string
        history = conversation.get("history", [])
        history_text = "\n".join([
            f"[{turn['role'].upper()}]: {turn['body']}"
            for turn in history[-4:]  # last 4 turns for context
        ])

        merchant_name = merchant.get("identity", {}).get("name", "")
        city          = merchant.get("identity", {}).get("city", "")
        languages     = merchant.get("identity", {}).get("languages", ["en"])
        ctr           = merchant.get("performance", {}).get("ctr", 0)
        cat_slug      = category.get("slug", "")
        peer_ctr      = category.get("peer_stats", {}).get("avg_ctr", 0.03)
        active_offers = [o["title"] for o in merchant.get("offers", []) if o.get("status") == "active"]
        lang_note     = "Use Hindi-English code-mix." if "hi" in languages else "Use English."

        user_prompt = f"""CONVERSATION CONTEXT:
Merchant: {merchant_name}, {city} | Category: {cat_slug}
CTR: {ctr:.2%} vs peer {peer_ctr:.2%} | Active offers: {active_offers}
{lang_note}

CONVERSATION SO FAR:
{history_text}

MERCHANT'S LATEST MESSAGE: "{merchant_message}"

Produce the next reply. Be concise. If they said yes, take the action immediately."""

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": REPLY_SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0,
            max_tokens=300,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content.strip()
        result = json.loads(raw)

        if result.get("action") not in ("send", "wait", "end"):
            return None

        return result

    except Exception as exc:
        logger.warning("Reply Groq call failed: %s", exc)
        return None


# ══════════════════════════════════════════════════════════════════════════════
# Rule-based reply fallback
# ══════════════════════════════════════════════════════════════════════════════

MERCHANT_COMMIT = [
    "ok", "okay", "yes", "haan", "bilkul", "let's", "lets",
    "do it", "proceed", "karo", "kar do", "bana do", "draft",
    "next", "what next", "aage", "go", "send", "push", "sure",
]

MERCHANT_QUESTION = [
    "kya", "kaisa", "kaise", "kyun", "why", "how", "what", "when",
    "samajh", "explain", "doubt", "confused", "really", "sach",
    "matlab", "will it", "kya hoga",
]

CUSTOMER_BOOKING = [
    "book", "slot", "appointment", "schedule", "fix", "confirm",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "aaj", "kal", "today", "tomorrow", "morning", "evening", "noon",
]

CUSTOMER_AFFIRMATIVE = [
    "yes", "ok", "okay", "sure", "please", "confirm", "go ahead",
    "haan", "ha", "bilkul", "zaroor", "theek",
]

NEGATIVE_SIGNALS = [
    "no", "nahi", "nahin", "nope", "not now", "abhi nahi", "later", "baad me",
]


def _rule_based_reply(msg: str, from_role: str, merchant_name: str, last_cta: str) -> Dict:
    """Deterministic fallback reply."""
    if from_role == "customer":
        if _contains_any(msg, CUSTOMER_BOOKING):
            return {
                "action": "send",
                "body": (
                    f"✅ Done! Your appointment request has been noted.\n\n"
                    f"{merchant_name} will confirm your exact slot shortly — usually within the hour."
                ),
                "cta": "none",
                "rationale": "Customer expressed booking intent; confirming receipt and next step.",
            }
        if _contains_any(msg, CUSTOMER_AFFIRMATIVE):
            return {
                "action": "send",
                "body": (
                    f"Perfect! {merchant_name} will reach out shortly to confirm. "
                    f"What time of day works best — morning, afternoon, or evening?"
                ),
                "cta": "slot_pick",
                "rationale": "Customer confirmed; collecting slot preference for booking.",
            }
        if _contains_any(msg, NEGATIVE_SIGNALS):
            return {
                "action": "end",
                "rationale": "Customer declined; graceful exit.",
            }
        return {
            "action": "send",
            "body": f"Thanks! {merchant_name} will get back to you soon. Anything else I can help with?",
            "cta": "open_ended",
            "rationale": "Generic customer fallback.",
        }

    # Merchant branch
    if _contains_any(msg, MERCHANT_COMMIT):
        return {
            "action": "send",
            "body": (
                "Perfect -- drafting your optimized post + offer right now. 30 seconds...\n\n"
                "Ek baar ready ho jaye toh aap directly approve karke live push kar sakte hain."
            ),
            "cta": "approve_draft",
            "rationale": "Merchant committed; moving to action phase immediately.",
        }
    if _contains_any(msg, MERCHANT_QUESTION) or "?" in msg:
        return {
            "action": "send",
            "body": (
                "Valid question — quickly explain karta hoon.\n\n"
                "Aapke CTR data aur category benchmarks dekh ke yeh ek high-ROI move hai. "
                "Koi extra budget nahi lagega.\n\nProceed karoon? YES / NO"
            ),
            "cta": "yes_no",
            "rationale": "Merchant asked a question; providing context and re-offering the action.",
        }
    if _contains_any(msg, NEGATIVE_SIGNALS):
        return {
            "action": "send",
            "body": "Understood! Koi pressure nahi.\nJab bhi ready ho, main hoon. Tab tak aapki listing monitor karti rehungi.",
            "cta": "none",
            "rationale": "Merchant declined; acknowledging and gracefully standing by.",
        }
    if len(msg.split()) > 4:
        return {
            "action": "send",
            "body": (
                "Got it -- noted.\n\n"
                "Main is context ke saath ek targeted plan draft karti hoon. "
                "Proceed karoon?"
            ),
            "cta": "yes_no",
            "rationale": "Merchant shared context; offering to proceed with a plan.",
        }
    return {
        "action": "wait",
        "wait_seconds": 300,
        "rationale": "Unclear merchant signal; waiting for a clearer response.",
    }


# ══════════════════════════════════════════════════════════════════════════════
# POST /v1/reply  — receive a reply from the simulated merchant/customer
# ══════════════════════════════════════════════════════════════════════════════
@app.post("/v1/reply")
def reply(data: Dict[str, Any]):
    raw_msg         = data.get("message", "")
    msg             = raw_msg.lower().strip()
    from_role       = data.get("from_role", "merchant")
    conversation_id = data.get("conversation_id", "")
    merchant_id     = data.get("merchant_id", "")

    # ── 1. Auto-reply detection — fast path, no LLM ─────────────────────────
    if _contains_any(msg, AUTO_REPLY_PATTERNS):
        return {
            "action":   "end",
            "rationale": "Detected automated/out-of-office reply. Exiting conversation gracefully.",
        }

    # ── 2. STOP / unsubscribe — fast path, no LLM ───────────────────────────
    if _contains_any(msg, STOP_PATTERNS):
        return {
            "action":   "end",
            "rationale": "Merchant/customer opted out. Conversation ended immediately.",
        }

    # ── 3. Retrieve conversation context ────────────────────────────────────
    conversation = CONVERSATIONS.get(conversation_id, {})
    if not merchant_id:
        merchant_id = conversation.get("merchant_id", "")

    merchant  = _get_payload("merchant", merchant_id) or {}
    cat_slug  = conversation.get("cat_slug") or merchant.get("category_slug", "")
    category  = _get_payload("category", cat_slug) or {}
    last_cta  = conversation.get("last_cta", "")
    merchant_name = merchant.get("identity", {}).get("name", "the merchant")

    # ── 4. LLM-powered context-aware reply ──────────────────────────────────
    if conversation and merchant and category:
        result = _compose_reply_with_groq(conversation, raw_msg, merchant, category)
        if result:
            # Update conversation history
            conversation.setdefault("history", []).append({"role": from_role, "body": raw_msg})
            if result.get("action") == "send" and result.get("body"):
                conversation["history"].append({"role": "vera", "body": result["body"]})
                conversation["last_cta"] = result.get("cta", "")
            return result

    # ── 5. Rule-based fallback ───────────────────────────────────────────────
    result = _rule_based_reply(msg, from_role, merchant_name, last_cta)

    # Update history
    if conversation:
        conversation.setdefault("history", []).append({"role": from_role, "body": raw_msg})
        if result.get("action") == "send" and result.get("body"):
            conversation["history"].append({"role": "vera", "body": result.get("body", "")})

    return result


# ══════════════════════════════════════════════════════════════════════════════
# GET /  — root
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/")
def home():
    return {
        "message":   "Vera — magicpin Merchant AI 🚀 v2.0",
        "endpoints": ["/v1/healthz", "/v1/metadata", "/v1/context", "/v1/tick", "/v1/reply"],
        "model":     "llama-3.3-70b-versatile (Groq)",
    }


# ══════════════════════════════════════════════════════════════════════════════
# POST /v1/teardown  — optional: wipe state at end of test
# ══════════════════════════════════════════════════════════════════════════════
@app.post("/v1/teardown")
def teardown():
    CONTEXTS.clear()
    CONVERSATIONS.clear()
    SENT_SUPPRESSIONS.clear()
    return {"status": "state_wiped"}