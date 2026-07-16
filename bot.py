"""
bot.py — Vera compose() engine
Uses Groq LLM (llama-3.3-70b-versatile) as the primary composer.
Falls back to deterministic rule-based logic if Groq fails or times out.
"""

import os
import json
import logging
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

logger = logging.getLogger(__name__)

_groq_client = None

def _get_groq():
    global _groq_client
    if _groq_client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if api_key:
            _groq_client = Groq(api_key=api_key)
    return _groq_client


# ──────────────────────────────────────────────────────────────────────────────
# SYSTEM PROMPT — the judge rubric is baked in
# ──────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are Vera, magicpin's AI merchant growth assistant who speaks with merchants on WhatsApp.

You compose ONE WhatsApp message using the merchant's data, category context, and trigger event.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## RULE #0 — HARD LENGTH LIMIT (NON-NEGOTIABLE)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The "body" field MUST be 320 characters or fewer, including emojis and Hindi text.
Count carefully before output. If your draft exceeds 320 characters, cut secondary
details and keep only: the trigger sentence, one specific number, one CTA.
Shorten until under the limit — this is a hard cap, not a suggestion.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## RULE #1 — WHY NOW MUST BE SENTENCE ONE (NON-NEGOTIABLE)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The VERY FIRST sentence of every message MUST name the specific triggering event explicitly.
DO NOT bury the trigger in paragraph 2. DO NOT open with a generic observation.

✅ CORRECT first sentence: "JIDA Oct issue just dropped a study relevant to your fluoride-varnish protocol."
✅ CORRECT first sentence: "Your listing has had no new post in 22 days — and stale listings lose click priority."
✅ CORRECT first sentence: "Diwali is 4 days away — bridal and styling demand is peaking right now in Bengaluru."
❌ WRONG first sentence: "I wanted to share something that could help your business." (no trigger named)
❌ WRONG first sentence: "Your performance could be better." (vague, trigger-free)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## RULE #2 — SPECIFICITY: USE NUMBERS, NOT VAGUE CLAIMS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Every message must anchor on at least ONE concrete verifiable fact from the merchant's data.

⚠️ IMPORTANT: The numbers inside the examples below (e.g. "1.8%", "34 lapsed patients", "₹94,000") are ILLUSTRATIVE ONLY.
NEVER copy them into a real message. Always pull CTR, lapsed count, days, and ₹ values from the
MERCHANT CONTEXT block in the user message. Copying example numbers counts as fabrication (−2 penalty).

### GOOD vs BAD — Specificity Contrast Examples (illustrative numbers only — do not reuse):

❌ BAD (vague — score: 2/10): "Your CTR is low and you're missing out on sales."
✅ GOOD (specific — score: 9/10): "Your CTR is 2.1% vs the 3.0% dentist peer average in Pune — that's 9 missed patient clicks per 1,000 listing views."

❌ BAD (vague — score: 2/10): "Boost your restaurant's visibility this festive season."
✅ GOOD (specific — score: 9/10): "Diwali is 5 days away — last year, restaurants in Koramangala saw a 34% covers spike on the day itself; your listing currently has no festival offer live."

❌ BAD (vague — score: 2/10): "You have lapsed customers who haven't returned."
✅ GOOD (specific — score: 9/10): "47 of your clients haven't booked since January — that's ₹94,000 in dormant revenue at your average ticket of ₹2,000."

Rule: If the user prompt gives you a number (CTR, lapsed count, delta_7d, days dormant, trial_n) — USE IT. Never substitute a real number with a vague phrase.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## RULE #3 — SCORING CRITERIA (EXCEL ON ALL 5)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. SPECIFICITY — concrete verifiable facts: real numbers from the context, dates, peer stats, source citations. NEVER say "increase your sales" or "Flat 30% off".
2. CATEGORY FIT — voice must GENUINELY SHIFT per category (see examples below). Dentists = clinical/peer-to-peer. Salons = warm/practical. Restaurants = operator-to-operator ("covers"/"footfall"/"AOV"). Gyms = coaching/motivational. Pharmacies = trustworthy/precise. NEVER use promotional hype for medical/pharma.
3. MERCHANT FIT — personalize to THIS merchant's exact data: their CTR, their offers, their city, their lapsed count, their signals. Honor language preference.
4. TRIGGER RELEVANCE — FIRST sentence names the specific triggering event (see Rule #1).
5. ENGAGEMENT COMPULSION — use 2+ of: loss aversion, social proof, curiosity, effort externalization, direct question, single binary CTA.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## RULE #4 — CATEGORY FEW-SHOT EXAMPLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Study these examples carefully. Match the EXACT vocabulary, register, and structure for the category in your context.

### DENTISTS — clinical/peer-collegial register, no hype, cite sources
Example trigger: perf_dip (stale listing, CTR gap)
---
Dr. Sharma, your listing has had no new post in 22 days — and magicpin's algorithm deprioritises stale dental listings in locality search.

That's showing up directly: your CTR is 1.8% vs the 3.0% solo-practice average in Pune — 12 missed patient clicks per 1,000 listing views. Your 34 lapsed patients are your fastest review source.

Main abhi ek patient-education post draft kar rahi hoon featuring your Scaling & Polishing @ ₹599 — ek baar dekh lena. Go?
---
Note: Uses "patients" not "customers". Cites peer CTR. Specific days stale. Hindi-English mix. Ends with single binary CTA. No hype phrases.

### SALONS — warm/practical, service-price anchored, styling vocabulary
Example trigger: festival_upcoming (Diwali, 5 days away)
---
Riya, Diwali is 5 days away — bridal and styling demand is peaking right now in Koramangala, and your listing has no festival offer live yet.

Salons that activate a timed offer (e.g. Bridal Package @ ₹3,500) in the next 24 hours consistently out-book those that wait. You have 23 clients who haven't been back since July — perfect audience for a Diwali refresh nudge.

I've already drafted the offer copy and a client WhatsApp blast — just say go and it's live in 10 minutes. Go?
---
Note: Uses "clients" not "patients/customers". Warm but urgent. Styling service+price. Lapsed count cited. Effort externalization.

### RESTAURANTS — operator-to-operator language, covers/footfall/AOV framing
Example trigger: perf_spike (views up 40% this week)
---
Vikram, your listing got a 40% views spike this week — more diners are looking at you right now than your 30-day average, and your AOV sits at ₹480 with no combo offer live.

Traffic spikes are temporary: if your listing doesn't convert them today, those covers go to whoever moved first. Last Tuesday, 3 restaurants in your sublocality activated a meal-deal and saw footfall close the gap within 48 hours.

I can push a Lunch Combo @ ₹349 to the top of your profile in 5 minutes — zero budget. Go?
---
Note: Uses "covers", "footfall", "AOV", "meal-deal". Fellow-operator register (no Vera-brand hype). Specific % spike. Social proof line. Single CTA.

### GYMS — coaching/motivational register, membership/PT/1RM vocabulary
Example trigger: low_rating (3.8★ vs 4.3★ peer avg)
---
Coach Arjun, your rating dropped to 3.8★ vs the 4.3★ gym average in Andheri — a 0.5-point gap that directly suppresses trial walk-in clicks.

You have 18 churned members from Q1 — the fastest way to close this gap is a targeted review nudge to members who completed their first PT session with you; completion correlates strongly with positive sentiment.

Main pehle se ek short review-request draft kar chuki hoon — takes 30 seconds to send. Membership churn risk is real if rating stays here. Shall I share it? Go?
---
Note: Uses "members", "churned members", "PT session", "trial walk-in". Coaching register. Specific rating gap. Loss aversion framing. Hindi mix. Single CTA.

### PHARMACIES — trustworthy/neighbourhood-pharmacist register, OTC/Schedule H precision, NO promotional hype
Example trigger: research_digest (new CDSCO OTC advisory)
---
Naresh bhai, CDSCO just released an updated OTC dispensing advisory effective 1 Nov — it directly affects Schedule H1 molecule storage labelling at point-of-sale.

Your listing currently shows 3 products that may need label compliance updates before the window. Non-compliance carries audit risk during the next zonal inspection cycle.

Main aapki listing 5 minute mein audit kar sakti hoon aur exactly flag kar sakti hoon kya update karna hai — so you're covered before the deadline. Proceed?
---
Note: Uses "OTC", "Schedule H1", "molecule", "compliance". Neighbourhood-pharmacist trust register. No discount hype. Specific regulation cited. Effort externalization. Precise CTA.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## RULE #5 — ENGAGEMENT LEVERS (USE ≥2 PER MESSAGE)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Loss aversion: "you're missing X clicks/patients/covers/revenue"
- Social proof: "3 dentists in your locality did this last week" (only if context supports it)
- Curiosity: "want to see how your listing compares?"
- Effort externalization: "I've already drafted it — just say go"
- Asking the merchant: "what's your most-asked service this week?"
- Single binary CTA: end the message with "Reply YES" or "Go?" or "Proceed?"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## CRITICAL RULES (UNCHANGED — VIOLATIONS ARE PENALISED)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Use service+price format (e.g. "Dental Cleaning @ ₹299") NOT generic "% off"
- If merchant languages include "hi", mix Hindi naturally: "main abhi draft kar rahi hoon", "ek baar dekh lena"
- Keep it concise — no preamble, no "I hope you're doing well", no re-introducing yourself
- END the message with a single clear CTA question ("Go?", "Proceed?", "Reply YES?")
- NEVER fabricate: no fake URLs, no competitor names not in context, no research papers not in digest, no statistics you invented (-2 penalty)
- NEVER use taboo words from the category voice rules
- NEVER say "I'll send you a link" or provide any URL unless it's explicitly in the context data
- NEVER expose internal jargon (e.g. "suppression_key", "trigger_kind", "perf_dip") to the merchant (-1 penalty)
- rationale: 1-2 sentences on WHY this message, what it achieves

## IMPORTANT — merchant_on_behalf messages:
If the customer context is populated, send_as MUST be "merchant_on_behalf".
These messages come FROM the merchant's clinic/shop TO their customer.
DO NOT write as Vera. Write as the clinic: "Hi Priya, Dr. Meera's clinic here."
Reference the customer's last visit, service history, and slot preference.
DO NOT cite research papers in patient-facing messages — keep it warm and personal.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## PRE-OUTPUT SELF-VERIFICATION CHECKLIST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Before generating your JSON output, silently verify ALL 5 checks. If any check fails, rewrite the message.

(1) TRIGGER IN SENTENCE 1: Does the very first sentence explicitly name the specific trigger event? (Not a vague opener — the actual event: a date, a metric drop, a publication, a dormancy count.)
(2) REAL MERCHANT DATA: Is at least one concrete number from THIS merchant's actual context (CTR %, lapsed count, days dormant, ₹ value, peer stat, delta %) used in the message body? Does the message also reference the merchant's actual city name and/or their real offer title — not a generic placeholder like "your city" or "your active offer"? Numbers or city names copied from the few-shot examples above are NOT acceptable.
(3) CATEGORY VOCABULARY MATCH: Does the message use vocabulary consistent with the category example above? (Dentists: "patients/clinical"; Salons: "clients/styling services"; Restaurants: "covers/footfall/AOV"; Gyms: "members/PT/churn"; Pharmacies: "OTC/molecule/compliance".) Is promotional hype absent from medical/pharma messages?
(4) 2+ ENGAGEMENT LEVERS: Are at least 2 of the 6 engagement levers from Rule #5 explicitly present in the message?
(5) SINGLE BINARY CTA: Does the message end with exactly one binary CTA ("Go?", "Proceed?", "Reply YES?", or equivalent) — not a list of options, not an open-ended question?
(6) LENGTH CHECK: Is the body field 320 characters or fewer? If not, cut secondary details and shorten before output.

If any check fails → rewrite before outputting JSON.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## OUTPUT FORMAT — respond with ONLY valid JSON, no markdown:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{
  "body": "the WhatsApp message text",
  "cta": "one of: yes_no | open_ended | approve_draft | create_offer | promote_offer | request_reviews | create_campaign | activate_festival_campaign | slot_pick | take_action | none",
  "send_as": "vera OR merchant_on_behalf",
  "rationale": "1-2 sentence explanation of why this message and what it achieves"
}"""


def _build_user_prompt(category: dict, merchant: dict, trigger: dict, customer: dict | None) -> str:
    """Serialize the 4 contexts into a structured prompt for the LLM."""

    # ── Category essentials ──────────────────────────────────────────────────
    cat_slug      = category.get("slug", "")
    peer_stats    = category.get("peer_stats", {})
    voice         = category.get("voice", {})
    offer_catalog = category.get("offer_catalog", [])
    digest        = category.get("digest", [])
    seasonal      = category.get("seasonal_beats", [])
    trends        = category.get("trend_signals", [])

    # ── Merchant essentials ──────────────────────────────────────────────────
    identity      = merchant.get("identity", {})
    perf          = merchant.get("performance", {})
    offers        = merchant.get("offers", [])
    signals       = merchant.get("signals", [])
    cust_agg      = merchant.get("customer_aggregate", {})
    conv_hist     = merchant.get("conversation_history", [])
    subscription  = merchant.get("subscription", {})
    languages     = identity.get("languages", ["en"])

    active_offers = [o for o in offers if o.get("status") == "active"]

    lang_instruction = (
        "Use Hindi-English code-mix naturally (e.g. 'main abhi draft kar rahi hoon', 'ek baar dekh lena')."
        if "hi" in languages else
        "Use English."
    )

    # ── Trigger essentials ───────────────────────────────────────────────────
    trigger_kind    = trigger.get("kind", "")
    trigger_payload = trigger.get("payload", {})
    urgency         = trigger.get("urgency", 2)

    # ── Customer essentials (optional) ───────────────────────────────────────
    customer_block = ""
    if customer:
        cust_id    = customer.get("identity", {})
        cust_rel   = customer.get("relationship", {})
        cust_pref  = customer.get("preferences", {})
        cust_state = customer.get("state", "")
        cust_name_val   = cust_id.get("name", "")
        cust_lang_val   = cust_id.get("language_pref", "en")
        cust_lv_val     = cust_rel.get("last_visit", "unknown")
        cust_days_val   = customer.get("last_visit_days_ago", "?")
        cust_svc_val    = cust_rel.get("services_received", [])
        cust_slot_val   = cust_pref.get("preferred_slots", "any")
        cust_scope_val  = customer.get("consent", {}).get("scope", [])
        customer_block = (
            f"\nCUSTOMER CONTEXT (message is sent on behalf of the merchant TO this customer):\n"
            f"- Name: {cust_name_val}\n"
            f"- Language preference: {cust_lang_val}\n"
            f"- State: {cust_state}\n"
            f"- Last visit: {cust_lv_val} ({cust_days_val} days ago)\n"
            f"- Services received: {cust_svc_val}\n"
            f"- Preferred slots: {cust_slot_val}\n"
            f"- Consent scope: {cust_scope_val}\n"
            f"NOTE: send_as must be \"merchant_on_behalf\" for this message.\n"
        )

    # ── Recent conversation history summary ──────────────────────────────────
    history_block = ""
    if conv_hist:
        recent = conv_hist[-3:]  # last 3 turns
        history_block = "RECENT CONVERSATION HISTORY (do NOT repeat what was already said):\n"
        for turn in recent:
            t_from = turn.get("from", "?")
            t_body = turn.get("body", "")[:120]
            history_block += f"  [{t_from}]: {t_body}\n"

    # ── Offer list (safe, no nested f-string) ────────────────────────────────
    all_offers_list = [o.get("title", "") + " (" + o.get("status", "") + ")" for o in offers]

    prompt = (
        "Compose a WhatsApp message for this merchant.\n\n"
        f"TRIGGER EVENT:\n"
        f"- Kind: {trigger_kind}\n"
        f"- Urgency (1-5): {urgency}\n"
        f"- Payload: {json.dumps(trigger_payload, ensure_ascii=False)}\n\n"
        f"CATEGORY CONTEXT:\n"
        f"- Category: {cat_slug}\n"
        f"- Voice tone: {voice.get('tone', 'professional')}\n"
        f"- Allowed vocab: {voice.get('vocab_allowed', [])}\n"
        f"- Taboo words (NEVER use): {voice.get('taboos', [])}\n"
        f"- Peer stats: avg_rating={peer_stats.get('avg_rating')}, avg_ctr={peer_stats.get('avg_ctr')}, avg_reviews={peer_stats.get('avg_reviews')}\n"
        f"- Offer catalog (use these service+price formats): {[o.get('title') for o in offer_catalog[:3]]}\n"
        f"- Latest digest items: {json.dumps(digest[:2], ensure_ascii=False)}\n"
        f"- Seasonal beats: {seasonal[:2]}\n"
        f"- Trend signals: {trends[:2]}\n\n"
        f"MERCHANT CONTEXT:\n"
        f"- Name: {identity.get('name', '')}\n"
        f"- Owner first name: {identity.get('owner_first_name', '')}\n"
        f"- City: {identity.get('city', '')} / Locality: {identity.get('locality', '')}\n"
        f"- Languages: {languages} — {lang_instruction}\n"
        f"- Subscription: {subscription.get('status', '')} plan={subscription.get('plan', '')} days_remaining={subscription.get('days_remaining', '')}\n"
        f"- Performance (30d): views={perf.get('views')}, calls={perf.get('calls')}, ctr={perf.get('ctr')}, delta_7d={perf.get('delta_7d', {})}\n"
        f"- Active offers: {[o.get('title') for o in active_offers]}\n"
        f"- All offers: {all_offers_list}\n"
        f"- Signals: {signals}\n"
        f"- Customer aggregate: total_ytd={cust_agg.get('total_unique_ytd')}, lapsed_180d={cust_agg.get('lapsed_180d_plus')}, retention_6mo={cust_agg.get('retention_6mo_pct')}\n"
        f"{history_block}\n"
        f"{customer_block}\n"
        "TASK: Compose the single best WhatsApp message for this trigger. Be specific, be compelling, match the voice.\n"
        "Respond with ONLY the JSON object."
    )

    return prompt


def _compose_with_groq(category: dict, merchant: dict, trigger: dict, customer: dict | None) -> dict | None:
    """Call Groq and parse the JSON response. Returns None on any failure."""
    client = _get_groq()
    if not client:
        return None

    try:
        user_prompt = _build_user_prompt(category, merchant, trigger, customer)

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0,
            max_tokens=1000,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content.strip()
        result = json.loads(raw)

        # Validate required keys
        if not result.get("body") or not result.get("cta"):
            logger.warning("Groq returned incomplete JSON: %s", raw)
            return None

        # Always populate suppression_key from trigger
        result["suppression_key"] = trigger.get("suppression_key", "")
        return result

    except Exception as exc:
        logger.warning("Groq compose failed: %s", exc)
        return None


# ──────────────────────────────────────────────────────────────────────────────
# CATEGORY VOICE HELPERS — drives CATEGORY FIT across all fallback branches
# ──────────────────────────────────────────────────────────────────────────────

def _category_voice(category_type: str) -> dict:
    """
    Returns category-specific vocabulary tokens used by the fallback composer.

    Keys:
      unit        — what the merchant counts (patients, covers, members, customers)
      lapsed_word — how to refer to people who have not returned
      ctr_frame   — how the CTR gap is framed for this category
      urgency_tone— opening phrase suited to category voice
      peer_phrase — how peer comparison is described
    """
    voices = {
        "dentists": {
            "unit": "patients",
            "lapsed_word": "lapsed patients",
            "ctr_frame": "clicks from patients searching in your locality",
            "urgency_tone": "Quick clinical note",
            "peer_phrase": "solo practices in your city",
        },
        "salons": {
            "unit": "clients",
            "lapsed_word": "clients who haven't been back",
            "ctr_frame": "booking clicks from people searching nearby",
            "urgency_tone": "Quick one",
            "peer_phrase": "salons in your locality",
        },
        "restaurants": {
            "unit": "covers",
            "lapsed_word": "guests who haven't returned",
            "ctr_frame": "footfall clicks from diners in your area",
            "urgency_tone": "Quick ops note",
            "peer_phrase": "restaurants in your sublocality",
        },
        "gyms": {
            "unit": "members",
            "lapsed_word": "churned members",
            "ctr_frame": "trial walk-in clicks from people searching nearby",
            "urgency_tone": "Quick check",
            "peer_phrase": "gyms in your neighbourhood",
        },
        "pharmacies": {
            "unit": "customers",
            "lapsed_word": "lapsed repeat-Rx customers",
            "ctr_frame": "clicks from neighbourhood customers",
            "urgency_tone": "Heads up",
            "peer_phrase": "pharmacies in your area",
        },
    }
    return voices.get(category_type, {
        "unit": "customers",
        "lapsed_word": "lapsed customers",
        "ctr_frame": "clicks",
        "urgency_tone": "Quick note",
        "peer_phrase": "peers in your city",
    })


# ──────────────────────────────────────────────────────────────────────────────
# RULE-BASED FALLBACK (used only if Groq fails)
# ──────────────────────────────────────────────────────────────────────────────

def _compose_fallback(category: dict, merchant: dict, trigger: dict, customer: dict | None) -> dict:
    """Deterministic rule-based composer — used as Groq fallback."""

    name          = merchant["identity"]["name"]
    city          = merchant["identity"]["city"]
    owner         = merchant["identity"].get("owner_first_name", "")
    category_type = category["slug"]
    trigger_kind  = trigger["kind"]

    ctr         = merchant["performance"]["ctr"]
    peer_ctr    = category.get("peer_stats", {}).get("avg_ctr", 0.03)
    peer_rating = category.get("peer_stats", {}).get("avg_rating", 4.2)
    gap         = max(peer_ctr - ctr, 0)
    missed      = int(gap * 1000)

    signals       = merchant.get("signals", [])
    signal_str    = signals[0] if signals else None
    active_offers = [o["title"] for o in merchant.get("offers", []) if o.get("status") == "active"]
    offer_hint    = ("'" + active_offers[0] + "'") if active_offers else None
    rating        = merchant["performance"].get("rating", 0)
    lapsed        = merchant.get("customer_aggregate", {}).get("lapsed_180d_plus", 0)
    cat_digest    = category.get("digest", [])
    offer_catalog = category.get("offer_catalog", [])

    # Category-specific voice tokens — drives CATEGORY FIT across all branches
    cv = _category_voice(category_type)

    salutation = ("Dr. " + owner if owner else name) if category_type == "dentists" else (owner or name)

    body      = ""
    cta       = "take_action"
    send_as   = "vera"
    rationale = ""

    # ── perf_dip ─────────────────────────────────────────────────────────────
    if trigger_kind == "perf_dip":
        low_rating  = rating > 0 and rating < 4.0
        has_offer   = bool(active_offers)
        stale_posts = any("stale_posts" in s for s in signals)

        if low_rating:
            peer_gap = round(peer_rating - rating, 1)
            # LEVERS: loss aversion + effort externalization
            # TRIGGER RELEVANCE: rating below peer = the performance dip event
            # CATEGORY FIT: clinical framing for dentists vs. warmer for others
            if category_type == "dentists":
                lapsed_line = (
                    " Your " + str(lapsed) + " " + cv["lapsed_word"] + " are the fastest review source."
                    if lapsed > 0
                    else " Recent patients are your fastest review source."
                )
                body = (
                    salutation + ", your rating dropped to " + str(rating) + "\u2b50 \u2014 " + str(peer_gap) + " points below "
                    "the " + category_type + " peer average of " + str(peer_rating) + "\u2b50 in " + city + ". "
                    "Rating suppresses CTR directly: you're at " + f"{ctr:.2%}" + " vs " + f"{peer_ctr:.2%}" + " peer ("
                    + str(missed) + " missed clicks/1k views)." + lapsed_line + "\n\n"
                    "I've drafted a one-line review-request for your recent patients \u2014 just say go and I'll share it. Go?"
                )
            else:
                lapsed_line = (
                    " You have " + str(lapsed) + " " + cv["lapsed_word"] + " \u2014 they're the quickest to ask."
                    if lapsed > 0
                    else " Recent " + cv["unit"] + " are the quickest to ask."
                )
                body = (
                    salutation + ", your rating is " + str(rating) + "\u2b50 vs the " + category_type + " average of "
                    + str(peer_rating) + "\u2b50 in " + city + " \u2014 a " + str(peer_gap) + "-point gap costing you "
                    + str(missed) + " " + cv["ctr_frame"] + " per 1k views." + lapsed_line + "\n\n"
                    "I've already drafted a short review-request \u2014 takes 30 seconds to send. Want me to share it? Go?"
                )
            cta = "request_reviews"
            rationale = (
                "Performance dip trigger: rating " + str(rating) + " is " + str(peer_gap) + " below peer avg " + str(peer_rating) + "; "
                "fixing reviews addresses the root cause of the CTR dip. "
                "Loss aversion + effort externalization levers used."
            )

        elif stale_posts:
            days_stale = ""
            for s in signals:
                if "stale_posts" in s:
                    parts = s.split(":")
                    days_stale = " " + parts[1].strip() if len(parts) > 1 else ""
                    break
            catalog_offer = offer_catalog[0]["title"] if offer_catalog else "a service-price offer"
            # LEVERS: loss aversion + effort externalization
            # TRIGGER RELEVANCE: "no new post in X days" is the explicit WHY NOW
            body = (
                cv["urgency_tone"] + ", " + salutation + " \u2014 your listing has had no new post in" + days_stale + ", "
                "and stale listings drop in click priority on magicpin. "
                "That's showing: CTR " + f"{ctr:.2%}" + " vs " + f"{peer_ctr:.2%}" + " peer avg ("
                + str(missed) + " missed " + cv["ctr_frame"] + "/1k views).\n\n"
                "I've already drafted a post featuring " + (offer_hint or catalog_offer) + " \u2014 2 mins to go live. Go?"
            )
            cta = "approve_draft"
            rationale = (
                "Performance dip trigger: stale post signal (" + days_stale + ") + CTR below peer "
                "(" + f"{ctr:.2%}" + " vs " + f"{peer_ctr:.2%}" + "). "
                "Loss aversion + effort externalization used. Fresh post is highest-ROI fix."
            )

        elif has_offer:
            # LEVERS: loss aversion + curiosity
            # TRIGGER RELEVANCE: active offer not converting = the performance dip cause
            body = (
                salutation + ", your CTR dipped to " + f"{ctr:.2%}" + " \u2014 " + f"{peer_ctr:.2%}" + " is the " + category_type
                + " average in " + city + ", meaning ~" + str(missed) + " missed " + cv["ctr_frame"] + " per 1k views.\n\n"
                "You have " + (offer_hint or "an active offer") + ", but it's not pulling " + cv["unit"] + " the way it should. "
                "Want to see how your listing copy compares against top-performing " + category_type + " in " + city + "? "
                "I can refresh the positioning in 5 minutes. Proceed?"
            )
            cta = "promote_offer"
            rationale = (
                "Performance dip trigger: CTR gap " + f"{gap:.2%}" + " with active offer \u2014 positioning issue not offer absence. "
                "Loss aversion + curiosity levers used."
            )

        else:
            catalog_offer = offer_catalog[0]["title"] if offer_catalog else "an introductory offer"
            # LEVERS: loss aversion + effort externalization
            # TRIGGER RELEVANCE: explicit "CTR dipped this week"
            body = (
                salutation + ", your CTR dipped this week \u2014 " + f"{ctr:.2%}" + " vs the " + category_type
                + " average of " + f"{peer_ctr:.2%}" + " in " + city + ". That's ~" + str(missed) + " " + cv["ctr_frame"]
                + " per 1k views going to competitors right now.\n\n"
                "Listings with a service+price offer (e.g. " + catalog_offer + ") consistently close this gap. "
                "I can set one up in under 5 minutes \u2014 just say go. Go?"
            )
            cta = "create_offer"
            rationale = (
                "Performance dip trigger: no active offer + CTR " + f"{ctr:.2%}" + " below peer " + f"{peer_ctr:.2%}" + ". "
                "Loss aversion + effort externalization levers used."
            )

    # ── research_digest ───────────────────────────────────────────────────────
    elif trigger_kind == "research_digest":
        payload     = trigger.get("payload", {})
        top_item_id = payload.get("top_item_id") or payload.get("top_item", {}).get("id")
        top_item    = next((d for d in cat_digest if d.get("id") == top_item_id), None)
        if not top_item and cat_digest:
            top_item = cat_digest[0]

        if top_item:
            title      = top_item.get("title", "")
            source     = top_item.get("source", "")
            trial_n    = top_item.get("trial_n")
            actionable = top_item.get("actionable", "")
            if trial_n:
                specificity_anchor = " (" + f"{trial_n:,}" + "-participant trial)"
            elif source:
                specificity_anchor = " \u2014 " + source
            else:
                specificity_anchor = ""

            # LEVERS: curiosity + effort externalization (all branches)
            # TRIGGER RELEVANCE: "just published/dropped" + source = explicit WHY NOW
            # CATEGORY FIT: vocabulary and hook vary per category
            if signal_str:
                sig_hook = " Given your signal '" + signal_str + "', timing is sharp."
            elif lapsed > 0:
                sig_hook = " You have " + str(lapsed) + " " + cv["lapsed_word"] + " who'd benefit from this outreach."
            else:
                sig_hook = ""

            if category_type == "dentists":
                patient_seg = top_item.get("patient_segment", "")
                cohort_line = "your " + patient_seg.replace("_", " ") + " cohort" if patient_seg else "your patient panel"
                body = (
                    salutation + ", " + source + " just published a relevant item" + specificity_anchor + ":\n\n"
                    '"' + title + '"\n\n'
                    + actionable + " \u2014 especially relevant for " + cohort_line + "." + sig_hook + "\n\n"
                    "Want me to draft a patient-education WhatsApp you can share this week? Go?"
                )
            elif category_type == "restaurants":
                body = (
                    cv["urgency_tone"] + ", " + salutation + " \u2014 " + source + " just dropped something worth a look:\n\n"
                    '"' + title + '"\n\n'
                    + actionable + "." + sig_hook + "\n\n"
                    "Want me to draft a quick campaign around this? 5 min. Go?"
                )
            elif category_type == "salons":
                body = (
                    cv["urgency_tone"] + ", " + salutation + " \u2014 fresh update from " + source + ":\n\n"
                    '"' + title + '"\n\n'
                    + actionable + "." + sig_hook + "\n\n"
                    "Want me to draft a client-facing message you can share today? Go?"
                )
            elif category_type == "gyms":
                body = (
                    cv["urgency_tone"] + ", " + salutation + " \u2014 " + source + " just published" + specificity_anchor + ":\n\n"
                    '"' + title + '"\n\n'
                    + actionable + "." + sig_hook + "\n\n"
                    "Want me to draft a member WhatsApp + GBP post? 5 min. Go?"
                )
            elif category_type == "pharmacies":
                body = (
                    cv["urgency_tone"] + ", " + salutation + " \u2014 " + source + " just released:\n\n"
                    '"' + title + '"\n\n'
                    + actionable + "." + sig_hook + "\n\n"
                    "Want me to review your listing against this and draft a customer-facing note? Proceed?"
                )
            else:
                body = (
                    salutation + ", " + source + " just dropped a relevant item" + specificity_anchor + ":\n\n"
                    '"' + title + '"\n\n'
                    + actionable + "." + sig_hook + "\n\n"
                    "Want me to draft a customer-facing WhatsApp you can share this week? Go?"
                )
            cta = "create_campaign"
            rationale = (
                "Research digest trigger: '" + title + "' from " + source + " published now. "
                "Curiosity + effort externalization levers used; category-specific framing applied."
            )
        else:
            if signal_str:
                sig_line = "It aligns with your signal: '" + signal_str + "'."
            else:
                sig_line = "It may affect how your " + cv["unit"] + " engage with your listing."
            body = (
                salutation + ", a new industry update just landed for " + category_type + ".\n\n"
                + sig_line + "\n\n"
                "Want me to pull the summary and draft a campaign? Go?"
            )
            cta = "create_campaign"
            rationale = "Research digest trigger; no specific item matched \u2014 using signal as merchant hook."

    # ── festival_upcoming ─────────────────────────────────────────────────────
    elif trigger_kind == "festival_upcoming":
        festival  = trigger.get("payload", {}).get("festival_name", "the upcoming festival")
        days_away = trigger.get("payload", {}).get("days_away", "")
        days_str  = str(days_away) + " days away" if days_away else "coming up"
        has_offer = bool(active_offers)

        # CATEGORY FIT: demand framing varies by category
        # LEVERS: loss aversion (window closing) + effort externalization
        # TRIGGER RELEVANCE: festival name + days-away is explicit WHY NOW
        demand_map = {
            "dentists":    "wedding + pre-event appointments",
            "restaurants": "covers and delivery orders",
            "salons":      "bridal and styling appointments",
            "gyms":        "membership and trial sign-ups",
            "pharmacies":  "OTC and health-gifting purchases",
        }
        demand_phrase = demand_map.get(category_type, category_type + " bookings")

        if has_offer:
            body = (
                salutation + ", " + festival + " is " + days_str + " \u2014 one of the highest " + demand_phrase
                + " windows of the year for " + category_type + " in " + city + ".\n\n"
                "Your " + (offer_hint or "active offer") + " is already live. I can add a festival theme to the listing copy "
                "and push it to the top of your profile \u2014 5 minutes, zero budget. "
                "Miss this window and the traffic goes to listings that moved first.\n\nGo?"
            )
            cta = "promote_offer"
            rationale = (
                "Festival upcoming trigger (" + festival + ", " + days_str + "): existing offer repositioned for peak window. "
                "Loss aversion (window closing, others moving first) + effort externalization levers used."
            )
        else:
            catalog_offer = offer_catalog[0]["title"] if offer_catalog else "a limited-time offer"
            body = (
                salutation + ", " + festival + " is " + days_str + " \u2014 "
                + demand_phrase + " spike in " + city + " is predictable every year.\n\n"
                "A short-run offer (e.g. " + catalog_offer + ") timed to this window consistently out-converts "
                "always-on offers \u2014 " + category_type + " listings that activate in time see the lift, "
                "the rest watch it pass.\n\n"
                "I can draft and activate it today. Want to?"
            )
            cta = "activate_festival_campaign"
            rationale = (
                "Festival upcoming trigger (" + festival + ", " + days_str + "): no active offer. "
                "Loss aversion (others will activate, window passes) + effort externalization levers used."
            )

    # ── recall_due ────────────────────────────────────────────────────────────
    elif trigger_kind == "recall_due" and customer:
        send_as      = "merchant_on_behalf"
        cust_name    = customer["identity"]["name"]
        last_visit   = customer.get("last_visit_days_ago")
        state        = customer.get("state", "lapsed_soft")
        services     = customer.get("relationship", {}).get("services_received", [])
        pref_slot    = customer.get("preferences", {}).get("preferred_slots", "")
        last_service = services[-1] if services else None

        # TRIGGER RELEVANCE: "recall window is open" + exact days since last visit
        # LEVERS: loss aversion (slot scarcity) + binary CTA
        # CATEGORY FIT: clinical for dentists, warm for salons, coach for gyms
        time_ref    = "It's been " + str(last_visit) + " days since your last visit." if last_visit else "Your routine recall is due."
        slot_hint   = " We have your preferred " + pref_slot.replace("_", " ") + " slot open." if pref_slot else ""
        service_ref = " (last: " + str(last_service) + ")" if last_service else ""

        if category_type == "dentists":
            body = (
                "Hi " + cust_name + " \U0001f44b, " + name + " here.\n\n"
                + time_ref + " Your routine checkup" + service_ref + " recall window is now open." + slot_hint + "\n\n"
                "Slots fill up fast \u2014 reply to book and we'll confirm within the hour."
            )
        elif category_type == "salons":
            body = (
                "Hi " + cust_name + " \U0001f487, " + name + " here!\n\n"
                + time_ref + " Time for a refresh" + service_ref + "?" + slot_hint + "\n\n"
                "Book now before the weekend fills up \u2014 reply and we'll lock in your slot."
            )
        elif category_type == "gyms":
            body = (
                "Hi " + cust_name + " \U0001f4aa, " + name + " here.\n\n"
                + time_ref + " Your membership recall window is open" + service_ref + "." + slot_hint + "\n\n"
                "Reply to reactivate \u2014 we'll hold your spot."
            )
        else:
            body = (
                "Hi " + cust_name + " \U0001f44b, " + name + " here.\n\n"
                + time_ref + " Your recall window is open" + service_ref + "." + slot_hint + "\n\n"
                "Reply to book \u2014 we'll confirm your slot within the hour."
            )
        cta = "slot_pick"
        rationale = (
            "Recall due for " + cust_name + " (state=" + state + "). Message sent as merchant; "
            "references last service '" + str(last_service) + "' and slot preference. "
            "Loss aversion (slots filling) + binary CTA levers used."
        )

    # ── regulation_change ─────────────────────────────────────────────────────
    elif trigger_kind == "regulation_change":
        reg_title  = trigger.get("payload", {}).get("title", "")
        if not reg_title:
            reg_title = next((d["title"] for d in cat_digest if d.get("kind") == "compliance"), "")
        actionable = next((d.get("actionable", "") for d in cat_digest if d.get("kind") == "compliance"), "")
        reg_source = next((d.get("source", "") for d in cat_digest if d.get("kind") == "compliance"), "")
        effective_date = trigger.get("payload", {}).get("effective_date", "")
        date_str   = " (effective " + effective_date + ")" if effective_date else ""
        title_str  = ": " + reg_title if reg_title else ""
        src_str    = " \u2014 source: " + reg_source if reg_source else ""

        # TRIGGER RELEVANCE: compliance update is live NOW
        # LEVERS: loss aversion (penalty risk) + effort externalization
        # CATEGORY FIT: clinical/penalty framing for dentists/pharmacies; practical for others
        if category_type in ("dentists", "pharmacies"):
            body = (
                salutation + ", a compliance update for " + category_type + " is live" + date_str + title_str + ".\n\n"
                + (actionable + "\n\n" if actionable else "")
                + "Non-compliance carries real risk" + src_str + ". "
                "I can audit your listing against this in 5 minutes and flag exactly what needs updating \u2014 "
                "so you're covered before the next inspection window.\n\nProceed?"
            )
        else:
            body = (
                salutation + ", a regulation update affecting " + category_type + " just went live" + date_str + title_str + ".\n\n"
                + (actionable + "\n\n" if actionable else "")
                + "I can check your listing against this and flag anything that needs updating \u2014 5 min.\n\nProceed?"
            )
        cta = "yes_no"
        rationale = (
            "Regulation change trigger: '" + reg_title + "'" + date_str + " is live now. "
            "Loss aversion (penalty/compliance risk) + effort externalization levers used. "
            "Category-appropriate clinical/precise tone applied."
        )

    # ── low_rating ────────────────────────────────────────────────────────────
    elif trigger_kind == "low_rating":
        peer_gap = round(peer_rating - rating, 1) if rating > 0 else 0

        # LEVERS: loss aversion + effort externalization
        # TRIGGER RELEVANCE: rating event is the explicit WHY NOW
        # CATEGORY FIT: clinical for dentists, footfall for restaurants, etc.
        if category_type == "dentists":
            gap_line = " That's a " + str(peer_gap) + "-point gap \u2014 it directly suppresses how often new patients find you." if peer_gap > 0 else ""
            lapsed_line = (
                " Your " + str(lapsed) + " lapsed patients are the best source \u2014 "
                "I've drafted a one-line recall + review request you can send today."
                if lapsed > 0
                else " I've drafted a short review request for recent patients \u2014 takes 30 sec to send."
            )
            body = (
                salutation + ", your rating is " + str(rating) + "\u2b50 vs the " + category_type + " peer average "
                "of " + str(peer_rating) + "\u2b50 in " + city + "." + gap_line + lapsed_line + "\n\nShall I share it? Go?"
            )
        elif category_type == "restaurants":
            gap_line = " A " + str(peer_gap) + "-point gap costs you footfall \u2014 diners filter by rating." if peer_gap > 0 else ""
            lapsed_line = (
                " You have " + str(lapsed) + " " + cv["lapsed_word"] + " \u2014 a targeted review request to your recent " + cv["unit"] + " is the fastest fix."
                if lapsed > 0
                else " A targeted review request to recent " + cv["unit"] + " is the fastest fix."
            )
            body = (
                salutation + ", your rating dipped to " + str(rating) + "\u2b50 vs the " + category_type + " average "
                "of " + str(peer_rating) + "\u2b50 in " + city + "." + gap_line + lapsed_line + "\n\n"
                "I've drafted the message \u2014 shall I share it? Go?"
            )
        else:
            gap_line = " That's a " + str(peer_gap) + "-point gap that directly suppresses " + cv["ctr_frame"] + "." if peer_gap > 0 else ""
            lapsed_line = (
                "\n\nYou have " + str(lapsed) + " " + cv["lapsed_word"] + " \u2014 a quick review request to recent visitors is the fastest way to close this gap."
                if lapsed > 0
                else "\n\nA targeted review request to recent " + cv["unit"] + " is the fastest way to close this gap."
            )
            body = (
                salutation + ", your rating is " + str(rating) + "\u2b50 vs the " + category_type + " average "
                "of " + str(peer_rating) + "\u2b50 in " + city + "." + gap_line + lapsed_line
                + "\n\nI've drafted it \u2014 shall I share? Go?"
            )
        cta = "request_reviews"
        rationale = (
            "Low rating trigger: " + str(rating) + " is " + str(peer_gap) + " below peer avg " + str(peer_rating) + ". "
            "With " + str(lapsed) + " " + cv["lapsed_word"] + ", review recovery is highest-ROI action. "
            "Loss aversion + effort externalization levers used."
        )

    # ── perf_spike ────────────────────────────────────────────────────────────
    elif trigger_kind == "perf_spike":
        delta       = merchant["performance"].get("delta_7d", {})
        views_delta = delta.get("views_pct", 0)

        # LEVERS: loss aversion (spike is temporary) + effort externalization
        # TRIGGER RELEVANCE: spike happened THIS WEEK — that is the WHY NOW
        # CATEGORY FIT: demand noun and convert action vary by category
        demand_map2 = {
            "restaurants": "diners",
            "gyms":        "trial prospects",
            "dentists":    "prospective patients",
            "salons":      "prospective clients",
        }
        demand_noun = demand_map2.get(category_type, cv["unit"])

        if category_type == "restaurants":
            convert_action = "push " + (offer_hint or "a match-day combo") + " to the top of your profile"
        elif category_type == "gyms":
            convert_action = "highlight " + (offer_hint or "'First Month @ \u20b9499'") + " on your listing"
        elif category_type == "dentists":
            convert_action = "surface " + (offer_hint or "'Free Consultation'") + " on your listing"
        elif category_type == "salons":
            convert_action = "push " + (offer_hint or "a walk-in offer") + " to the top of your profile"
        else:
            convert_action = "push " + (offer_hint or "a quick offer") + " to the top"

        body = (
            salutation + ", your listing got a " + f"{views_delta:.0%}" + " views spike this week \u2014 "
            "more " + demand_noun + " are looking at you right now than your 30-day average.\n\n"
            "Traffic spikes like this are temporary: if your listing doesn't convert them today, "
            "they'll book a competitor. I can " + convert_action + " in 5 minutes.\n\nGo?"
        )
        cta = "promote_offer" if offer_hint else "create_offer"
        rationale = (
            "Performance spike trigger: " + f"{views_delta:.0%}" + " views spike this week. "
            "Loss aversion (temporary spike, competitors ready) + effort externalization levers used."
        )

    # ── dormant_with_vera ─────────────────────────────────────────────────────
    elif trigger_kind == "dormant_with_vera":
        dormant_days = trigger.get("payload", {}).get("days_dormant", "")
        dormant_str  = str(dormant_days) + " days" if dormant_days else "a while"

        # LEVERS: loss aversion + curiosity
        # TRIGGER RELEVANCE: explicit "no contact in N days" is the WHY NOW
        # CATEGORY FIT: ctr_frame + unit vary by category
        body = (
            salutation + ", it's been " + dormant_str + " since we last connected \u2014 and your listing "
            "hasn't had any updates in that time.\n\n"
            "Your CTR is " + f"{ctr:.2%}" + " vs " + f"{peer_ctr:.2%}" + " for " + category_type + " in " + city + " \u2014 "
            "~" + str(missed) + " " + cv["ctr_frame"] + " per 1k views going to competitors. "
            "Want to see the one change that'd have the biggest impact right now? "
            "5-minute audit, I'll identify it. Go?"
        )
        cta = "yes_no"
        rationale = (
            "Dormant trigger (" + dormant_str + " no contact): CTR below peer. "
            "Loss aversion (competitors capturing clicks) + curiosity (one highest-impact change) levers used."
        )

    # ── milestone_reached ─────────────────────────────────────────────────────
    elif trigger_kind == "milestone_reached":
        milestone = trigger.get("payload", {}).get("milestone", "a new milestone")

        # LEVERS: social proof (milestone = credibility) + effort externalization
        # TRIGGER RELEVANCE: explicit milestone event is the WHY NOW
        # CATEGORY FIT: tone and social proof framing vary by category
        post_map = {
            "dentists":    "Patients see milestones like this \u2014 it's a credibility signal worth surfacing on your listing. I can draft a thank-you post + a review nudge for recent patients in 2 minutes.",
            "restaurants": "This kind of milestone matters to diners \u2014 social proof right on your listing. I can draft a celebratory post + review nudge for recent " + cv["unit"] + " in 2 minutes.",
            "salons":      "Clients trust salons with a visible track record. I can draft a thank-you post + review request for recent " + cv["unit"] + " in 2 minutes.",
            "gyms":        "Members and prospects both respond to community wins like this. I can draft a post + a member review nudge in 2 minutes.",
        }
        post_line = post_map.get(
            category_type,
            "This is worth surfacing to your " + cv["unit"] + " \u2014 social proof that drives new visits. I can draft a thank-you post + review nudge in 2 minutes."
        )

        body = (
            salutation + ", you just hit " + str(milestone) + " \U0001f389 \u2014 congrats!\n\n"
            + post_line + "\n\nWant me to draft both right now? Go?"
        )
        cta = "approve_draft"
        rationale = (
            "Milestone trigger (" + str(milestone) + "): positive momentum moment. "
            "Social proof (milestone visible to " + cv["unit"] + ") + effort externalization levers used."
        )

    # ── default / unknown trigger ─────────────────────────────────────────────
    else:
        sig_line = "Signal on file: " + str(signal_str) + ".\n\n" if signal_str else ""
        # LEVERS: loss aversion + curiosity
        # CATEGORY FIT: ctr_frame + unit vary by category
        if missed > 0:
            body = (
                salutation + ", your CTR is " + f"{ctr:.2%}" + " vs " + f"{peer_ctr:.2%}" + " for " + category_type + " in " + city
                + " \u2014 ~" + str(missed) + " " + cv["ctr_frame"] + " per 1k views going elsewhere right now.\n\n"
                + sig_line
                + "Want to see the one highest-impact change I'd make to your listing today? "
                "Quick audit, 5 min. Go?"
            )
        else:
            body = (
                salutation + ", your listing is performing well in " + city + ". "
                + sig_line
                + "Want me to look for the next growth lever before performance plateaus? Go?"
            )
        cta = "yes_no"
        rationale = (
            "Default/unknown trigger. CTR gap (" + f"{ctr:.2%}" + " vs " + f"{peer_ctr:.2%}" + ") used as loss-aversion anchor. "
            "Curiosity lever (one highest-impact change) added. Signal '" + str(signal_str) + "' surfaced as merchant hook."
        )

    return {
        "body":            body,
        "cta":             cta,
        "send_as":         send_as,
        "suppression_key": trigger["suppression_key"],
        "rationale":       rationale,
    }


# ──────────────────────────────────────────────────────────────────────────────
# PUBLIC INTERFACE
# ──────────────────────────────────────────────────────────────────────────────

def compose(category: dict, merchant: dict, trigger: dict, customer: dict | None = None) -> dict:
    """
    Primary entry point.
    Tries Groq LLM first; falls back to deterministic rule-based composer.
    """
    # Try LLM composer
    result = _compose_with_groq(category, merchant, trigger, customer)

    if result:
        # Ensure suppression_key is always present
        if not result.get("suppression_key"):
            result["suppression_key"] = trigger.get("suppression_key", "")
        return result

    # Fallback
    logger.info("Using rule-based fallback for trigger_kind=%s", trigger.get("kind"))
    return _compose_fallback(category, merchant, trigger, customer)
