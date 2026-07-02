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

## Scoring criteria (be excellent on ALL 5):
1. SPECIFICITY — anchor on concrete verifiable facts: real numbers, dates, peer stats, source citations. NEVER say "increase your sales" or "Flat 30% off".
2. CATEGORY FIT — match voice/tone to category. Dentists = peer/clinical tone ("fluoride varnish", "caries"). Salons = friendly. Restaurants = appetite-driven. Never promotional hype for medical categories.
3. MERCHANT FIT — personalize to THIS merchant's exact state: their CTR, their offers, their city, their lapsed count, their signals. Honor language preference.
4. TRIGGER RELEVANCE — the message must clearly explain WHY NOW — what event triggered this message.
5. ENGAGEMENT COMPULSION — use at least 2 of these levers:
   - Loss aversion: "you're missing X"
   - Social proof: "3 dentists in your area did Y this month"
   - Curiosity: "want to see who?"
   - Effort externalization: "I've already drafted it — just say go"
   - Asking the merchant: "what's your most-asked treatment this week?"
   - Single binary CTA: Reply YES / Reply STOP

## Rules:
- Use service+price format (e.g. "Dental Cleaning @ ₹299") NOT generic "% off"
- If merchant languages include "hi", mix Hindi naturally: "main abhi draft kar rahi hoon", "ek baar dekh lena"
- Keep it concise — no preamble, no "I hope you're doing well"
- Single CTA at the END of the message
- Never fabricate data not present in the context
- Never use taboo words from category voice rules
- rationale must be 1-2 sentences explaining WHY this message was chosen

## Output format — respond with ONLY valid JSON, no markdown:
{
  "body": "the WhatsApp message text",
  "cta": "one of: yes_no | open_ended | approve_draft | create_offer | promote_offer | request_reviews | create_campaign | activate_festival_campaign | slot_pick | take_action | none",
  "send_as": "vera OR merchant_on_behalf (only for customer-facing recall messages)",
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
        cust_id   = customer.get("identity", {})
        cust_rel  = customer.get("relationship", {})
        cust_pref = customer.get("preferences", {})
        cust_state = customer.get("state", "")
        customer_block = f"""
CUSTOMER CONTEXT (message is sent on behalf of the merchant TO this customer):
- Name: {cust_id.get('name', '')}
- Language preference: {cust_id.get('language_pref', 'en')}
- State: {cust_state}
- Last visit: {cust_rel.get('last_visit', 'unknown')} ({customer.get('last_visit_days_ago', '?')} days ago)
- Services received: {cust_rel.get('services_received', [])}
- Preferred slots: {cust_pref.get('preferred_slots', 'any')}
- Consent scope: {customer.get('consent', {}).get('scope', [])}
NOTE: send_as must be "merchant_on_behalf" for this message.
"""

    # ── Recent conversation history summary ──────────────────────────────────
    history_block = ""
    if conv_hist:
        recent = conv_hist[-3:]  # last 3 turns
        history_block = "RECENT CONVERSATION HISTORY (do NOT repeat what was already said):\n"
        for turn in recent:
            history_block += f"  [{turn.get('from','?')}]: {turn.get('body','')[:120]}\n"

    prompt = f"""Compose a WhatsApp message for this merchant.

TRIGGER EVENT:
- Kind: {trigger_kind}
- Urgency (1-5): {urgency}
- Payload: {json.dumps(trigger_payload, ensure_ascii=False)}

CATEGORY CONTEXT:
- Category: {cat_slug}
- Voice tone: {voice.get('tone', 'professional')}
- Allowed vocab: {voice.get('vocab_allowed', [])}
- Taboo words (NEVER use): {voice.get('taboos', [])}
- Peer stats: avg_rating={peer_stats.get('avg_rating')}, avg_ctr={peer_stats.get('avg_ctr')}, avg_reviews={peer_stats.get('avg_reviews')}
- Offer catalog (use these service+price formats): {[o.get('title') for o in offer_catalog[:3]]}
- Latest digest items: {json.dumps(digest[:2], ensure_ascii=False)}
- Seasonal beats: {seasonal[:2]}
- Trend signals: {trends[:2]}

MERCHANT CONTEXT:
- Name: {identity.get('name', '')}
- Owner first name: {identity.get('owner_first_name', '')}
- City: {identity.get('city', '')} / Locality: {identity.get('locality', '')}
- Languages: {languages} — {lang_instruction}
- Subscription: {subscription.get('status', '')} plan={subscription.get('plan', '')} days_remaining={subscription.get('days_remaining', '')}
- Performance (30d): views={perf.get('views')}, calls={perf.get('calls')}, ctr={perf.get('ctr')}, delta_7d={perf.get('delta_7d', {})}
- Active offers: {[o.get('title') for o in active_offers]}
- All offers: {[f"{o.get('title')} ({o.get('status')})" for o in offers]}
- Signals: {signals}
- Customer aggregate: total_ytd={cust_agg.get('total_unique_ytd')}, lapsed_180d={cust_agg.get('lapsed_180d_plus')}, retention_6mo={cust_agg.get('retention_6mo_pct')}
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
# RULE-BASED FALLBACK (kept from v1, used only if Groq fails)
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
    offer_hint    = f"'{active_offers[0]}'" if active_offers else None
    rating        = merchant["performance"].get("rating", 0)
    lapsed        = merchant.get("customer_aggregate", {}).get("lapsed_180d_plus", 0)
    cat_digest    = category.get("digest", [])
    offer_catalog = category.get("offer_catalog", [])

    salutation = (f"Dr. {owner}" if owner else name) if category_type == "dentists" else (owner or name)

    body      = ""
    cta       = "take_action"
    send_as   = "vera"
    rationale = ""

    if trigger_kind == "perf_dip":
        low_rating  = rating > 0 and rating < 4.0
        has_offer   = bool(active_offers)
        stale_posts = any("stale_posts" in s for s in signals)

        if low_rating:
            peer_gap = round(peer_rating - rating, 1)
            body = (
                f"{salutation}, your rating is {rating}⭐ — {peer_gap} points below the "
                f"{category_type} peer average of {peer_rating}⭐ in {city}. "
                f"Reviews are the primary driver of CTR on magicpin listings.\n\n"
                f"Shall I draft a review-request message for your recent customers?"
            )
            cta = "request_reviews"
            rationale = (
                f"Rating {rating} is {peer_gap} below peer avg {peer_rating}; "
                f"fixing reviews addresses the root cause of the CTR dip before offer spend."
            )

        elif stale_posts:
            days_stale = ""
            for s in signals:
                if "stale_posts" in s:
                    parts = s.split(":")
                    days_stale = f" ({parts[1]})" if len(parts) > 1 else ""
                    break
            catalog_offer = offer_catalog[0]["title"] if offer_catalog else "a service-price offer"
            body = (
                f"{salutation}, your listing has no new post in{days_stale} — "
                f"stale listings lose click priority. "
                f"CTR: {ctr:.2%} vs {peer_ctr:.2%} peer avg ({missed} missed clicks/1k views).\n\n"
                f"I can draft a post featuring {offer_hint or catalog_offer} right now — 2 mins to go live. Go?"
            )
            cta = "approve_draft"
            rationale = (
                f"Stale post signal + CTR below peer ({ctr:.2%} vs {peer_ctr:.2%}). "
                f"A fresh post with offer anchor is the highest-ROI fix without new budget."
            )

        elif has_offer:
            body = (
                f"{salutation}, CTR is {ctr:.2%} vs {peer_ctr:.2%} for {category_type} in {city} "
                f"— ~{missed} missed clicks per 1,000 views.\n\n"
                f"You have {offer_hint} active but it needs a visibility push. "
                f"Want me to refresh the listing copy to lead with this offer?"
            )
            cta = "promote_offer"
            rationale = (
                f"CTR gap of {gap:.2%} with an active offer suggests a positioning issue, not offer absence. "
                f"Refreshing copy costs zero and has fastest impact."
            )

        else:
            catalog_offer = offer_catalog[0]["title"] if offer_catalog else "an introductory offer"
            body = (
                f"{salutation}, your CTR is {ctr:.2%} — {category_type} average in {city} is {peer_ctr:.2%}. "
                f"That is ~{missed} clicks/1k views left on the table.\n\n"
                f"Listings with a service+price offer (e.g. {catalog_offer}) consistently outperform blank ones. "
                f"Shall I set one up?"
            )
            cta = "create_offer"
            rationale = (
                f"No active offer + CTR {ctr:.2%} below peer {peer_ctr:.2%}. "
                f"Adding a catalog-style service+price offer is the highest-leverage first move."
            )

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
            specificity_anchor = f" ({trial_n:,}-participant trial)" if trial_n else (f" — {source}" if source else "")
            merchant_hook = (
                f" Your data already shows '{signal_str}' — this is timed well." if signal_str
                else (f" You have {lapsed} lapsed patients who could benefit from this." if lapsed > 0 else "")
            )
            body = (
                f"{salutation}, {source} just dropped a relevant item{specificity_anchor}:\n\n"
                f'"{title}"\n\n'
                f"{actionable}.{merchant_hook}\n\n"
                f"Want me to draft a patient-facing WhatsApp you can share this week?"
            )
            cta = "create_campaign"
            rationale = (
                f"Digest item '{title}' from {source} is directly actionable for this category. "
                f"Tying to patient content positions Vera as a knowledge partner."
            )
        else:
            body = (
                f"{salutation}, a new industry update just landed for {category_type}.\n\n"
                f"{'It aligns with your signal: ' + repr(signal_str) + '.' if signal_str else 'It may affect how your customers engage with your listing.'}\n\n"
                f"Want me to pull the summary and draft a campaign?"
            )
            cta = "create_campaign"
            rationale = "Research digest trigger; no specific item matched — using signal as merchant hook."

    elif trigger_kind == "festival_upcoming":
        festival  = trigger.get("payload", {}).get("festival_name", "the upcoming festival")
        has_offer = bool(active_offers)
        if has_offer:
            body = (
                f"{salutation}, {festival} is coming up \u2014 demand for {category_type} spikes this window.\n\n"
                f"Your {offer_hint} is already live. I can add a festival theme to the listing copy "
                f"and push it to the top of your profile \u2014 5 mins, zero budget.\n\nGo ahead?"
            )
            cta = "promote_offer"
            rationale = f"Existing offer {offer_hint} repositioned for {festival} with zero new spend. Festival window creates timing urgency."
        else:
            catalog_offer = offer_catalog[0]["title"] if offer_catalog else "a limited-time offer"
            body = (
                f"{salutation}, {festival} is coming \u2014 one of the highest-traffic windows for {category_type} listings.\n\n"
                f"A short-run offer (e.g. {catalog_offer}) timed to the festival consistently outperforms "
                f"always-on offers in this window. I can draft and activate it today.\n\nWant to?"
            )
            cta = "activate_festival_campaign"
            rationale = f"No active offer + festival upcoming. Festival-timed catalog offer is the highest-ROI action for this window."

    elif trigger_kind == "recall_due" and customer:
        send_as    = "merchant_on_behalf"
        cust_name  = customer["identity"]["name"]
        last_visit = customer.get("last_visit_days_ago")
        state      = customer.get("state", "lapsed_soft")
        services   = customer.get("relationship", {}).get("services_received", [])
        pref_slot  = customer.get("preferences", {}).get("preferred_slots", "")
        last_service = services[-1] if services else None
        time_ref   = f"It's been {last_visit} days since your last visit." if last_visit else "Your routine recall is due."
        slot_hint  = f" We have {pref_slot.replace('_', ' ')} slots open." if pref_slot else ""
        service_ref = f" (last: {last_service})" if last_service else ""
        body = (
            f"Hi {cust_name} \U0001f44b, {name} here.\n\n"
            f"{time_ref} Your routine checkup{service_ref} recall window is open.{slot_hint}\n\n"
            f"Reply to book \u2014 we'll confirm your slot within the hour."
        )
        cta = "slot_pick"
        rationale = (
            f"Recall due for {cust_name} (state={state}). "
            f"Message sent as merchant; references last service '{last_service}' and slot preference."
        )

    elif trigger_kind == "regulation_change":
        reg_title  = trigger.get("payload", {}).get("title", "")
        if not reg_title:
            reg_title = next((d["title"] for d in cat_digest if d.get("kind") == "compliance"), "")
        actionable = next((d.get("actionable", "") for d in cat_digest if d.get("kind") == "compliance"), "")
        body = (
            f"{salutation}, a compliance update for {category_type} is live"
            f"{': ' + reg_title if reg_title else ''}.\n\n"
            f"{actionable + chr(10) + chr(10) if actionable else ''}"
            f"I can review your listing against this and flag what needs updating \u2014 5 min.\n\nProceed?"
        )
        cta = "yes_no"
        rationale = f"Regulation change affecting {category_type}: '{reg_title}'. Proactive compliance review protects listing."

    elif trigger_kind == "low_rating":
        peer_gap = round(peer_rating - rating, 1) if rating > 0 else 0
        body = f"{salutation}, your rating is {rating}\u2b50 vs the {category_type} average of {peer_rating}\u2b50 in {city}."
        if peer_gap > 0:
            body += f" That's a {peer_gap}-point gap that directly suppresses click-through."
        if lapsed > 0:
            body += (
                f" You have {lapsed} customers who haven't returned in 6+ months \u2014 "
                f"a review request to recent visitors is the fastest fix.\n\n"
            )
        else:
            body += "\n\nA targeted review request to recent visitors is the fastest way to close this gap.\n\n"
        body += "Shall I draft the message?"
        cta = "request_reviews"
        rationale = f"Rating {rating} is {peer_gap} below peer avg {peer_rating}. With {lapsed} lapsed customers, review recovery is highest-ROI action."

    elif trigger_kind == "perf_spike":
        delta = merchant["performance"].get("delta_7d", {})
        views_delta = delta.get("views_pct", 0)
        body = (
            f"{salutation}, your listing got a {views_delta:.0%} views spike this week — "
            f"this is the perfect window to convert that traffic into bookings.\n\n"
            f"{'You have ' + offer_hint + ' active. Want me to push it to the top of your profile?' if offer_hint else 'Want me to add a quick offer to capture these visitors before traffic normalizes?'}"
        )
        cta = "promote_offer" if offer_hint else "create_offer"
        rationale = f"Views spike {views_delta:.0%} — high-traffic window. Converting visibility to bookings is highest-ROI move right now."

    elif trigger_kind == "dormant_with_vera":
        body = (
            f"{salutation}, it's been a while since we last connected.\n\n"
            f"Your CTR is {ctr:.2%} vs {peer_ctr:.2%} for {category_type} in {city} — "
            f"~{missed} potential visitors/month going to competitors.\n\n"
            f"Want me to run a quick listing audit? 5 min, I'll identify the one highest-impact change."
        )
        cta = "yes_no"
        rationale = f"Dormant merchant + CTR below peer. Re-engagement with a concrete value proposition (audit) is the best first move."

    elif trigger_kind == "milestone_reached":
        milestone = trigger.get("payload", {}).get("milestone", "a new milestone")
        body = (
            f"{salutation}, you just hit {milestone} 🎉 — congrats!\n\n"
            f"This is a great moment to add a 'thank you' post and nudge customers for a review. "
            f"Want me to draft both in 2 minutes?"
        )
        cta = "approve_draft"
        rationale = f"Milestone reached ({milestone}) — positive momentum moment to drive reviews and visibility."

    else:
        sig_line = f"Signal: {signal_str}.\n\n" if signal_str else ""
        if missed > 0:
            body = (
                f"{salutation}, your CTR is {ctr:.2%} vs {peer_ctr:.2%} for {category_type} in {city} "
                f"\u2014 ~{missed} clicks/1k views going elsewhere.\n\n"
                f"{sig_line}"
                f"Quick listing audit \u2014 I'll identify the one change with highest impact. 5 min. Go?"
            )
        else:
            body = (
                f"{salutation}, your listing is performing well in {city}. "
                f"{sig_line}"
                f"Want me to look for the next growth lever before performance plateaus?"
            )
        cta = "yes_no"
        rationale = (
            f"Default/unknown trigger. CTR gap ({ctr:.2%} vs {peer_ctr:.2%}) used as specificity anchor. "
            f"Signal '{signal_str}' surfaced as merchant hook."
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