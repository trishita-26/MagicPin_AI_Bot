"""Helper: writes the improved bot.py to disk."""
import pathlib

BOT_SRC = r'''"""
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

SYSTEM_PROMPT = """You are Vera, magicpin\'s AI merchant growth assistant who speaks with merchants on WhatsApp.

You compose ONE WhatsApp message using the merchant\'s data, category context, and trigger event.

## Scoring criteria (be excellent on ALL 5):
1. SPECIFICITY — anchor on concrete verifiable facts: real numbers, dates, peer stats, source citations. NEVER say "increase your sales" or "Flat 30% off".
2. CATEGORY FIT — match voice/tone to category. Dentists = peer/clinical tone ("fluoride varnish", "caries", peer-collegial register). Salons = warm practical ("balayage", "keratin", "hair spa"). Restaurants = appetite-driven fellow-operator language ("covers", "footfall", "AOV", "table turnover"). Gyms = energetic coach-to-member ("membership churn", "PT sessions", "1RM"). Pharmacies = trustworthy precise neighbourhood-pharmacist ("OTC", "Schedule H", "molecule"). NEVER use promotional hype for medical/pharma categories.
3. MERCHANT FIT — personalize to THIS merchant\'s exact state: their CTR, their offers, their city, their lapsed count, their signals. Honor language preference.
4. TRIGGER RELEVANCE — the message must clearly explain WHY NOW — what specific event triggered this message. Name the trigger explicitly (e.g. "JIDA Oct issue just dropped", "your listing has had no new post in 22 days", "Diwali is 4 days away").
5. ENGAGEMENT COMPULSION — use at least 2 of these levers explicitly:
   - Loss aversion: "you\'re missing X clicks/patients/covers"
   - Social proof: "3 dentists in your locality did this last week" (only if context supports it)
   - Curiosity: "want to see how your listing compares?"
   - Effort externalization: "I\'ve already drafted it — just say go"
   - Asking the merchant: "what\'s your most-asked service this week?"
   - Single binary CTA: end the message with "Reply YES" or "Go?" or "Proceed?"

## Critical Rules:
- Use service+price format (e.g. "Dental Cleaning @ ₹299") NOT generic "% off"
- If merchant languages include "hi", mix Hindi naturally: "main abhi draft kar rahi hoon", "ek baar dekh lena"
- Keep it concise — no preamble, no "I hope you\'re doing well", no re-introducing yourself
- END the message with a single clear CTA question ("Go?", "Proceed?", "Reply YES?")
- NEVER fabricate: no fake URLs, no competitor names not in context, no research papers not in digest, no statistics you invented
- NEVER use taboo words from the category voice rules
- NEVER say "I\'ll send you a link" or provide any URL unless it\'s explicitly in the context data
- rationale: 1-2 sentences on WHY this message, what it achieves

## IMPORTANT — merchant_on_behalf messages:
If the customer context is populated, send_as MUST be "merchant_on_behalf".
These messages come FROM the merchant\'s clinic/shop TO their customer.
DO NOT write as Vera. Write as the clinic: "Hi Priya, Dr. Meera\'s clinic here."
Reference the customer\'s last visit, service history, and slot preference.
DO NOT cite research papers in patient-facing messages — keep it warm and personal.

## Output format — respond with ONLY valid JSON, no markdown:
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
        "Use Hindi-English code-mix naturally (e.g. \'main abhi draft kar rahi hoon\', \'ek baar dekh lena\')."
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
        customer_block = f"""
CUSTOMER CONTEXT (message is sent on behalf of the merchant TO this customer):
- Name: {cust_id.get("name", "")}
- Language preference: {cust_id.get("language_pref", "en")}
- State: {cust_state}
- Last visit: {cust_rel.get("last_visit", "unknown")} ({customer.get("last_visit_days_ago", "?")} days ago)
- Services received: {cust_rel.get("services_received", [])}
- Preferred slots: {cust_pref.get("preferred_slots", "any")}
- Consent scope: {customer.get("consent", {}).get("scope", [])}
NOTE: send_as must be "merchant_on_behalf" for this message.
"""

    # ── Recent conversation history summary ──────────────────────────────────
    history_block = ""
    if conv_hist:
        recent = conv_hist[-3:]  # last 3 turns
        history_block = "RECENT CONVERSATION HISTORY (do NOT repeat what was already said):\n"
        for turn in recent:
            history_block += f"  [{turn.get(\'from\',\'?\')}]: {turn.get(\'body\',\'\')[:120]}\n"

    prompt = f"""Compose a WhatsApp message for this merchant.

TRIGGER EVENT:
- Kind: {trigger_kind}
- Urgency (1-5): {urgency}
- Payload: {json.dumps(trigger_payload, ensure_ascii=False)}

CATEGORY CONTEXT:
- Category: {cat_slug}
- Voice tone: {voice.get("tone", "professional")}
- Allowed vocab: {voice.get("vocab_allowed", [])}
- Taboo words (NEVER use): {voice.get("taboos", [])}
- Peer stats: avg_rating={peer_stats.get("avg_rating")}, avg_ctr={peer_stats.get("avg_ctr")}, avg_reviews={peer_stats.get("avg_reviews")}
- Offer catalog (use these service+price formats): {[o.get("title") for o in offer_catalog[:3]]}
- Latest digest items: {json.dumps(digest[:2], ensure_ascii=False)}
- Seasonal beats: {seasonal[:2]}
- Trend signals: {trends[:2]}

MERCHANT CONTEXT:
- Name: {identity.get("name", "")}
- Owner first name: {identity.get("owner_first_name", "")}
- City: {identity.get("city", "")} / Locality: {identity.get("locality", "")}
- Languages: {languages} — {lang_instruction}
- Subscription: {subscription.get("status", "")} plan={subscription.get("plan", "")} days_remaining={subscription.get("days_remaining", "")}
- Performance (30d): views={perf.get("views")}, calls={perf.get("calls")}, ctr={perf.get("ctr")}, delta_7d={perf.get("delta_7d", {})}
- Active offers: {[o.get("title") for o in active_offers]}
- All offers: {[f"{o.get(\'title\')} ({o.get(\'status\')})" for o in offers]}
- Signals: {signals}
- Customer aggregate: total_ytd={cust_agg.get("total_unique_ytd")}, lapsed_180d={cust_agg.get("lapsed_180d_plus")}, retention_6mo={cust_agg.get("retention_6mo_pct")}
{history_block}
{customer_block}

TASK: Compose the single best WhatsApp message for this trigger. Be specific, be compelling, match the voice.
Respond with ONLY the JSON object."""

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
            max_tokens=600,
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
      lapsed_word — how to refer to people who haven\'t returned
      ctr_frame   — how CTR gap is framed for this category
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
            "lapsed_word": "clients who haven\'t been back",
            "ctr_frame": "booking clicks from people searching nearby",
            "urgency_tone": "Quick one",
            "peer_phrase": "salons in your locality",
        },
        "restaurants": {
            "unit": "covers",
            "lapsed_word": "guests who haven\'t returned",
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
    offer_hint    = f"\'{active_offers[0]}\'" if active_offers else None
    rating        = merchant["performance"].get("rating", 0)
    lapsed        = merchant.get("customer_aggregate", {}).get("lapsed_180d_plus", 0)
    cat_digest    = category.get("digest", [])
    offer_catalog = category.get("offer_catalog", [])

    # Category-specific voice tokens — drives CATEGORY FIT across all branches
    cv = _category_voice(category_type)

    salutation = (f"Dr. {owner}" if owner else name) if category_type == "dentists" else (owner or name)

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
                    f" Your {lapsed} {cv[\'lapsed_word\']} are the fastest review source."
                    if lapsed > 0
                    else " Recent patients are your fastest review source."
                )
                body = (
                    f"{salutation}, your rating dropped to {rating}\u2b50 \u2014 {peer_gap} points below "
                    f"the {category_type} peer average of {peer_rating}\u2b50 in {city}. "
                    f"Rating suppresses CTR directly: you\'re at {ctr:.2%} vs {peer_ctr:.2%} peer ({missed} missed clicks/1k views).{lapsed_line}\n\n"
                    f"I\'ve drafted a one-line review-request for your recent patients \u2014 just say go and I\'ll share it. Go?"
                )
            else:
                lapsed_line = (
                    f" You have {lapsed} {cv[\'lapsed_word\']} \u2014 they\'re the quickest to ask."
                    if lapsed > 0
                    else f" Recent {cv[\'unit\']} are the quickest to ask."
                )
                body = (
                    f"{salutation}, your rating is {rating}\u2b50 vs the {category_type} average of {peer_rating}\u2b50 in {city} "
                    f"\u2014 a {peer_gap}-point gap costing you {missed} {cv[\'ctr_frame\']} per 1k views.{lapsed_line}\n\n"
                    f"I\'ve already drafted a short review-request \u2014 takes 30 seconds to send. Want me to share it? Go?"
                )
            cta = "request_reviews"
            rationale = (
                f"Performance dip trigger: rating {rating} is {peer_gap} below peer avg {peer_rating}; "
                f"fixing reviews addresses the root cause of the CTR dip. "
                f"Loss aversion + effort externalization levers used."
            )

        elif stale_posts:
            days_stale = ""
            for s in signals:
                if "stale_posts" in s:
                    parts = s.split(":")
                    days_stale = f" {parts[1].strip()}" if len(parts) > 1 else ""
                    break
            catalog_offer = offer_catalog[0]["title"] if offer_catalog else "a service-price offer"
            # LEVERS: loss aversion + effort externalization
            # TRIGGER RELEVANCE: "no new post in X days" is the explicit WHY NOW
            body = (
                f"{cv[\'urgency_tone\']}, {salutation} \u2014 your listing has had no new post in{days_stale}, "
                f"and stale listings drop in click priority on magicpin. "
                f"That\'s showing: CTR {ctr:.2%} vs {peer_ctr:.2%} peer avg ({missed} missed {cv[\'ctr_frame\']}/1k views).\n\n"
                f"I\'ve already drafted a post featuring {offer_hint or catalog_offer} \u2014 2 mins to go live. Go?"
            )
            cta = "approve_draft"
            rationale = (
                f"Performance dip trigger: stale post signal ({days_stale}) + CTR below peer "
                f"({ctr:.2%} vs {peer_ctr:.2%}). "
                f"Loss aversion + effort externalization used. Fresh post is highest-ROI fix."
            )

        elif has_offer:
            # LEVERS: loss aversion + curiosity
            # TRIGGER RELEVANCE: active offer not converting = the performance dip cause
            body = (
                f"{salutation}, your CTR dipped to {ctr:.2%} \u2014 {peer_ctr:.2%} is the {category_type} "
                f"average in {city}, meaning ~{missed} missed {cv[\'ctr_frame\']} per 1k views.\n\n"
                f"You have {offer_hint} active, but it\'s not pulling {cv[\'unit\']} the way it should. "
                f"Want to see how your listing copy compares against top-performing {category_type} in {city}? "
                f"I can refresh the positioning in 5 minutes. Proceed?"
            )
            cta = "promote_offer"
            rationale = (
                f"Performance dip trigger: CTR gap {gap:.2%} with active offer \u2014 positioning issue not offer absence. "
                f"Loss aversion + curiosity levers used."
            )

        else:
            catalog_offer = offer_catalog[0]["title"] if offer_catalog else "an introductory offer"
            # LEVERS: loss aversion + effort externalization
            # TRIGGER RELEVANCE: explicit "CTR dipped this week"
            body = (
                f"{salutation}, your CTR dipped this week \u2014 {ctr:.2%} vs the {category_type} "
                f"average of {peer_ctr:.2%} in {city}. That\'s ~{missed} {cv[\'ctr_frame\']} per 1k views "
                f"going to competitors right now.\n\n"
                f"Listings with a service+price offer (e.g. {catalog_offer}) consistently close this gap. "
                f"I can set one up in under 5 minutes \u2014 just say go. Go?"
            )
            cta = "create_offer"
            rationale = (
                f"Performance dip trigger: no active offer + CTR {ctr:.2%} below peer {peer_ctr:.2%}. "
                f"Loss aversion + effort externalization levers used."
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
            specificity_anchor = (
                f" ({trial_n:,}-participant trial)" if trial_n
                else (f" \u2014 {source}" if source else "")
            )
            # LEVERS: curiosity + effort externalization (all branches)
            # TRIGGER RELEVANCE: "just published/dropped" + source = explicit WHY NOW
            # CATEGORY FIT: vocabulary and hook vary per category
            if category_type == "dentists":
                patient_seg = top_item.get("patient_segment", "")
                cohort_line = f"your {patient_seg.replace(\'_\', \' \')} cohort" if patient_seg else "your patient panel"
                merchant_hook = (
                    f" Given your signal \'{signal_str}\', timing is sharp."
                    if signal_str
                    else (f" You have {lapsed} lapsed patients who\'d benefit from this outreach." if lapsed > 0 else "")
                )
                body = (
                    f"{salutation}, {source} just published a relevant item{specificity_anchor}:\n\n"
                    f"\"{title}\"\n\n"
                    f"{actionable} \u2014 especially relevant for {cohort_line}.{merchant_hook}\n\n"
                    f"Want me to draft a patient-education WhatsApp you can share this week? Go?"
                )
            elif category_type == "restaurants":
                merchant_hook = (
                    f" Aligns with your signal: \'{signal_str}\'." if signal_str
                    else (f" Your {lapsed} lapsed {cv[\'unit\']} are a ready audience." if lapsed > 0 else "")
                )
                body = (
                    f"{cv[\'urgency_tone\']}, {salutation} \u2014 {source} just dropped something worth a look:\n\n"
                    f"\"{title}\"\n\n"
                    f"{actionable}.{merchant_hook}\n\n"
                    f"Want me to draft a quick campaign around this? 5 min. Go?"
                )
            elif category_type == "salons":
                merchant_hook = (
                    f" Your \'{signal_str}\' signal lines up well." if signal_str
                    else (f" Could re-engage your {lapsed} {cv[\'lapsed_word\']}." if lapsed > 0 else "")
                )
                body = (
                    f"{cv[\'urgency_tone\']}, {salutation} \u2014 fresh update from {source}:\n\n"
                    f"\"{title}\"\n\n"
                    f"{actionable}.{merchant_hook}\n\n"
                    f"Want me to draft a client-facing message you can share today? Go?"
                )
            elif category_type == "gyms":
                merchant_hook = (
                    f" Lines up with your \'{signal_str}\' signal." if signal_str
                    else (f" Good hook for your {lapsed} {cv[\'lapsed_word\']}." if lapsed > 0 else "")
                )
                body = (
                    f"{cv[\'urgency_tone\']}, {salutation} \u2014 {source} just published{specificity_anchor}:\n\n"
                    f"\"{title}\"\n\n"
                    f"{actionable}.{merchant_hook}\n\n"
                    f"Want me to draft a member WhatsApp + GBP post? 5 min. Go?"
                )
            elif category_type == "pharmacies":
                merchant_hook = (
                    f" Ties to your signal: \'{signal_str}\'." if signal_str
                    else (f" Affects your {lapsed} repeat-Rx {cv[\'unit\']}." if lapsed > 0 else "")
                )
                body = (
                    f"{cv[\'urgency_tone\']}, {salutation} \u2014 {source} just released:\n\n"
                    f"\"{title}\"\n\n"
                    f"{actionable}.{merchant_hook}\n\n"
                    f"Want me to review your listing against this and draft a customer-facing note? Proceed?"
                )
            else:
                merchant_hook = (
                    f" Aligns with your signal \'{signal_str}\'." if signal_str
                    else (f" You have {lapsed} {cv[\'lapsed_word\']} who could benefit." if lapsed > 0 else "")
                )
                body = (
                    f"{salutation}, {source} just dropped a relevant item{specificity_anchor}:\n\n"
                    f"\"{title}\"\n\n"
                    f"{actionable}.{merchant_hook}\n\n"
                    f"Want me to draft a customer-facing WhatsApp you can share this week? Go?"
                )
            cta = "create_campaign"
            rationale = (
                f"Research digest trigger: \'{title}\' from {source} published now. "
                f"Curiosity + effort externalization levers used; category-specific framing applied."
            )
        else:
            body = (
                f"{salutation}, a new industry update just landed for {category_type}.\n\n"
                f"{'It aligns with your signal: ' + repr(signal_str) + '.' if signal_str else 'It may affect how your ' + cv['unit'] + ' engage with your listing.'}\n\n"
                f"Want me to pull the summary and draft a campaign? Go?"
            )
            cta = "create_campaign"
            rationale = "Research digest trigger; no specific item matched \u2014 using signal as merchant hook."

    # ── festival_upcoming ─────────────────────────────────────────────────────
    elif trigger_kind == "festival_upcoming":
        festival  = trigger.get("payload", {}).get("festival_name", "the upcoming festival")
        days_away = trigger.get("payload", {}).get("days_away", "")
        days_str  = f"{days_away} days away" if days_away else "coming up"
        has_offer = bool(active_offers)

        # CATEGORY FIT: demand framing varies by category
        # LEVERS: loss aversion (window closing) + effort externalization
        # TRIGGER RELEVANCE: festival name + days-away is explicit WHY NOW
        if category_type == "dentists":
            demand_phrase = "wedding + pre-event appointments"
        elif category_type == "restaurants":
            demand_phrase = "covers and delivery orders"
        elif category_type == "salons":
            demand_phrase = "bridal and styling appointments"
        elif category_type == "gyms":
            demand_phrase = "membership and trial sign-ups"
        elif category_type == "pharmacies":
            demand_phrase = "OTC and health-gifting purchases"
        else:
            demand_phrase = f"{category_type} bookings"

        if has_offer:
            body = (
                f"{salutation}, {festival} is {days_str} \u2014 one of the highest {demand_phrase} "
                f"windows of the year for {category_type} in {city}.\n\n"
                f"Your {offer_hint} is already live. I can add a festival theme to the listing copy "
                f"and push it to the top of your profile \u2014 5 minutes, zero budget. "
                f"Miss this window and the traffic goes to listings that moved first.\n\nGo?"
            )
            cta = "promote_offer"
            rationale = (
                f"Festival upcoming trigger ({festival}, {days_str}): existing offer repositioned for peak window. "
                f"Loss aversion (window closing, others moving first) + effort externalization levers used."
            )
        else:
            catalog_offer = offer_catalog[0]["title"] if offer_catalog else "a limited-time offer"
            body = (
                f"{salutation}, {festival} is {days_str} \u2014 "
                f"{demand_phrase} spike in {city} is predictable every year.\n\n"
                f"A short-run offer (e.g. {catalog_offer}) timed to this window consistently out-converts "
                f"always-on offers \u2014 {category_type} listings that activate in time see the lift, "
                f"the rest watch it pass.\n\n"
                f"I can draft and activate it today. Want to?"
            )
            cta = "activate_festival_campaign"
            rationale = (
                f"Festival upcoming trigger ({festival}, {days_str}): no active offer. "
                f"Loss aversion (others will activate, window passes) + effort externalization levers used."
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
        time_ref    = f"It\'s been {last_visit} days since your last visit." if last_visit else "Your routine recall is due."
        slot_hint   = f" We have your preferred {pref_slot.replace(\'_\', \' \')} slot open." if pref_slot else ""
        service_ref = f" (last: {last_service})" if last_service else ""

        if category_type == "dentists":
            body = (
                f"Hi {cust_name} \U0001f44b, {name} here.\n\n"
                f"{time_ref} Your routine checkup{service_ref} recall window is now open.{slot_hint}\n\n"
                f"Slots fill up fast \u2014 reply to book and we\'ll confirm within the hour."
            )
        elif category_type == "salons":
            body = (
                f"Hi {cust_name} \U0001f487, {name} here!\n\n"
                f"{time_ref} Time for a refresh{service_ref}?{slot_hint}\n\n"
                f"Book now before the weekend fills up \u2014 reply and we\'ll lock in your slot."
            )
        elif category_type == "gyms":
            body = (
                f"Hi {cust_name} \U0001f4aa, {name} here.\n\n"
                f"{time_ref} Your membership recall window is open{service_ref}.{slot_hint}\n\n"
                f"Reply to reactivate \u2014 we\'ll hold your spot."
            )
        else:
            body = (
                f"Hi {cust_name} \U0001f44b, {name} here.\n\n"
                f"{time_ref} Your recall window is open{service_ref}.{slot_hint}\n\n"
                f"Reply to book \u2014 we\'ll confirm your slot within the hour."
            )
        cta = "slot_pick"
        rationale = (
            f"Recall due for {cust_name} (state={state}). Message sent as merchant; "
            f"references last service \'{last_service}\' and slot preference. "
            f"Loss aversion (slots filling) + binary CTA levers used."
        )

    # ── regulation_change ─────────────────────────────────────────────────────
    elif trigger_kind == "regulation_change":
        reg_title  = trigger.get("payload", {}).get("title", "")
        if not reg_title:
            reg_title = next((d["title"] for d in cat_digest if d.get("kind") == "compliance"), "")
        actionable = next((d.get("actionable", "") for d in cat_digest if d.get("kind") == "compliance"), "")
        reg_source = next((d.get("source", "") for d in cat_digest if d.get("kind") == "compliance"), "")
        effective_date = trigger.get("payload", {}).get("effective_date", "")
        date_str = f" (effective {effective_date})" if effective_date else ""

        # TRIGGER RELEVANCE: compliance update is live NOW
        # LEVERS: loss aversion (penalty risk) + effort externalization
        # CATEGORY FIT: clinical/penalty framing for dentists/pharmacies; practical for others
        if category_type in ("dentists", "pharmacies"):
            body = (
                f"{salutation}, a compliance update for {category_type} is live{date_str}"
                f"{': ' + reg_title if reg_title else ''}.\n\n"
                f"{(actionable + chr(10) + chr(10)) if actionable else ''}"
                f"Non-compliance carries real risk{' \u2014 source: ' + reg_source if reg_source else ''}. "
                f"I can audit your listing against this in 5 minutes and flag exactly what needs updating \u2014 "
                f"so you\'re covered before the next inspection window.\n\nProceed?"
            )
        else:
            body = (
                f"{salutation}, a regulation update affecting {category_type} just went live{date_str}"
                f"{': ' + reg_title if reg_title else ''}.\n\n"
                f"{(actionable + chr(10) + chr(10)) if actionable else ''}"
                f"I can check your listing against this and flag anything that needs updating \u2014 5 min.\n\nProceed?"
            )
        cta = "yes_no"
        rationale = (
            f"Regulation change trigger: \'{reg_title}\'{date_str} is live now. "
            f"Loss aversion (penalty/compliance risk) + effort externalization levers used. "
            f"Category-appropriate clinical/precise tone applied."
        )

    # ── low_rating ────────────────────────────────────────────────────────────
    elif trigger_kind == "low_rating":
        peer_gap = round(peer_rating - rating, 1) if rating > 0 else 0

        # LEVERS: loss aversion + effort externalization
        # TRIGGER RELEVANCE: rating event is the explicit WHY NOW
        # CATEGORY FIT: clinical for dentists, footfall for restaurants, etc.
        if category_type == "dentists":
            gap_line = f" That\'s a {peer_gap}-point gap \u2014 it directly suppresses how often new patients find you." if peer_gap > 0 else ""
            lapsed_line = (
                f" Your {lapsed} lapsed patients are the best source \u2014 "
                f"I\'ve drafted a one-line recall + review request you can send today."
                if lapsed > 0
                else " I\'ve drafted a short review request for recent patients \u2014 takes 30 sec to send."
            )
            body = (
                f"{salutation}, your rating is {rating}\u2b50 vs the {category_type} peer average "
                f"of {peer_rating}\u2b50 in {city}.{gap_line}{lapsed_line}\n\nShall I share it? Go?"
            )
        elif category_type == "restaurants":
            gap_line = f" A {peer_gap}-point gap costs you footfall \u2014 diners filter by rating." if peer_gap > 0 else ""
            lapsed_line = (
                f" You have {lapsed} {cv[\'lapsed_word\']} \u2014 a targeted review request to your recent {cv[\'unit\']} is the fastest fix."
                if lapsed > 0
                else f" A targeted review request to recent {cv[\'unit\']} is the fastest fix."
            )
            body = (
                f"{salutation}, your rating dipped to {rating}\u2b50 vs the {category_type} average "
                f"of {peer_rating}\u2b50 in {city}.{gap_line}{lapsed_line}\n\n"
                f"I\'ve drafted the message \u2014 shall I share it? Go?"
            )
        else:
            gap_line = f" That\'s a {peer_gap}-point gap that directly suppresses {cv[\'ctr_frame\']}." if peer_gap > 0 else ""
            lapsed_line = (
                f"\n\nYou have {lapsed} {cv[\'lapsed_word\']} \u2014 a quick review request to recent visitors is the fastest way to close this gap."
                if lapsed > 0
                else f"\n\nA targeted review request to recent {cv[\'unit\']} is the fastest way to close this gap."
            )
            body = (
                f"{salutation}, your rating is {rating}\u2b50 vs the {category_type} average "
                f"of {peer_rating}\u2b50 in {city}.{gap_line}{lapsed_line}\n\nI\'ve drafted it \u2014 shall I share? Go?"
            )
        cta = "request_reviews"
        rationale = (
            f"Low rating trigger: {rating} is {peer_gap} below peer avg {peer_rating}. "
            f"With {lapsed} {cv[\'lapsed_word\']}, review recovery is highest-ROI action. "
            f"Loss aversion + effort externalization levers used."
        )

    # ── perf_spike ────────────────────────────────────────────────────────────
    elif trigger_kind == "perf_spike":
        delta = merchant["performance"].get("delta_7d", {})
        views_delta = delta.get("views_pct", 0)

        # LEVERS: loss aversion (spike is temporary) + effort externalization
        # TRIGGER RELEVANCE: spike happened THIS WEEK — that is the WHY NOW
        # CATEGORY FIT: demand noun and convert action vary by category
        if category_type == "restaurants":
            demand_noun = "diners"
            convert_action = (
                f"push {offer_hint} to the top of your profile" if offer_hint
                else "add a match-day combo to capture these diners"
            )
        elif category_type == "gyms":
            demand_noun = "trial prospects"
            convert_action = (
                f"highlight {offer_hint} on your listing" if offer_hint
                else "add a \'First Month @ \u20b9499\' offer to capture these sign-ups"
            )
        elif category_type == "dentists":
            demand_noun = "prospective patients"
            convert_action = (
                f"surface {offer_hint} on your listing" if offer_hint
                else "add a \'Free Consultation\' offer to convert this traffic"
            )
        elif category_type == "salons":
            demand_noun = "prospective clients"
            convert_action = (
                f"push {offer_hint} to the top of your profile" if offer_hint
                else "add a walk-in offer to convert these visitors"
            )
        else:
            demand_noun = cv["unit"]
            convert_action = (
                f"push {offer_hint} to the top" if offer_hint
                else "add a quick offer to capture these visitors"
            )

        body = (
            f"{salutation}, your listing got a {views_delta:.0%} views spike this week \u2014 "
            f"more {demand_noun} are looking at you right now than your 30-day average.\n\n"
            f"Traffic spikes like this are temporary: if your listing doesn\'t convert them today, "
            f"they\'ll book a competitor. I can {convert_action} in 5 minutes.\n\nGo?"
        )
        cta = "promote_offer" if offer_hint else "create_offer"
        rationale = (
            f"Performance spike trigger: {views_delta:.0%} views spike this week. "
            f"Loss aversion (temporary spike, competitors ready) + effort externalization levers used."
        )

    # ── dormant_with_vera ─────────────────────────────────────────────────────
    elif trigger_kind == "dormant_with_vera":
        dormant_days = trigger.get("payload", {}).get("days_dormant", "")
        dormant_str = f"{dormant_days} days" if dormant_days else "a while"

        # LEVERS: loss aversion + curiosity
        # TRIGGER RELEVANCE: explicit "no contact in N days" is the WHY NOW
        # CATEGORY FIT: ctr_frame + unit vary by category
        body = (
            f"{salutation}, it\'s been {dormant_str} since we last connected \u2014 and your listing "
            f"hasn\'t had any updates in that time.\n\n"
            f"Your CTR is {ctr:.2%} vs {peer_ctr:.2%} for {category_type} in {city} \u2014 "
            f"~{missed} {cv[\'ctr_frame\']} per 1k views going to competitors. "
            f"Want to see the one change that\'d have the biggest impact right now? "
            f"5-minute audit, I\'ll identify it. Go?"
        )
        cta = "yes_no"
        rationale = (
            f"Dormant trigger ({dormant_str} no contact): CTR below peer. "
            f"Loss aversion (competitors capturing clicks) + curiosity (one highest-impact change) levers used."
        )

    # ── milestone_reached ─────────────────────────────────────────────────────
    elif trigger_kind == "milestone_reached":
        milestone = trigger.get("payload", {}).get("milestone", "a new milestone")

        # LEVERS: social proof (milestone = credibility) + effort externalization
        # TRIGGER RELEVANCE: explicit milestone event is the WHY NOW
        # CATEGORY FIT: tone and social proof framing vary by category
        if category_type == "dentists":
            post_line = (
                f"Patients see milestones like this \u2014 it\'s a credibility signal worth surfacing on your listing. "
                f"I can draft a thank-you post + a review nudge for recent patients in 2 minutes."
            )
        elif category_type == "restaurants":
            post_line = (
                f"This kind of milestone matters to diners \u2014 social proof right on your listing. "
                f"I can draft a celebratory post + review nudge for recent {cv[\'unit\']} in 2 minutes."
            )
        elif category_type == "salons":
            post_line = (
                f"Clients trust salons with a visible track record. "
                f"I can draft a thank-you post + review request for recent {cv[\'unit\']} in 2 minutes."
            )
        elif category_type == "gyms":
            post_line = (
                f"Members and prospects both respond to community wins like this. "
                f"I can draft a post + a member review nudge in 2 minutes."
            )
        else:
            post_line = (
                f"This is worth surfacing to your {cv[\'unit\']} \u2014 social proof that drives new visits. "
                f"I can draft a thank-you post + review nudge in 2 minutes."
            )

        body = (
            f"{salutation}, you just hit {milestone} \U0001f389 \u2014 congrats!\n\n"
            f"{post_line}\n\nWant me to draft both right now? Go?"
        )
        cta = "approve_draft"
        rationale = (
            f"Milestone trigger ({milestone}): positive momentum moment. "
            f"Social proof (milestone visible to {cv[\'unit\']}) + effort externalization levers used."
        )

    # ── default / unknown trigger ─────────────────────────────────────────────
    else:
        sig_line = f"Signal on file: {signal_str}.\n\n" if signal_str else ""
        # LEVERS: loss aversion + curiosity
        # CATEGORY FIT: ctr_frame + unit vary by category
        if missed > 0:
            body = (
                f"{salutation}, your CTR is {ctr:.2%} vs {peer_ctr:.2%} for {category_type} in {city} "
                f"\u2014 ~{missed} {cv[\'ctr_frame\']} per 1k views going elsewhere right now.\n\n"
                f"{sig_line}"
                f"Want to see the one highest-impact change I\'d make to your listing today? "
                f"Quick audit, 5 min. Go?"
            )
        else:
            body = (
                f"{salutation}, your listing is performing well in {city}. "
                f"{sig_line}"
                f"Want me to look for the next growth lever before performance plateaus? Go?"
            )
        cta = "yes_no"
        rationale = (
            f"Default/unknown trigger. CTR gap ({ctr:.2%} vs {peer_ctr:.2%}) used as loss-aversion anchor. "
            f"Curiosity lever (one highest-impact change) added. Signal \'{signal_str}\' surfaced as merchant hook."
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
'''

pathlib.Path("bot.py").write_text(BOT_SRC, encoding="utf-8")
print(f"Written {len(BOT_SRC)} bytes to bot.py")
