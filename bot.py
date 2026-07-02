
def compose(category, merchant, trigger, customer=None):

    # ── Identity ───────────────────────────────────────────────────────
    name          = merchant["identity"]["name"]
    city          = merchant["identity"]["city"]
    owner         = merchant["identity"].get("owner_first_name", "")
    category_type = category["slug"]
    trigger_kind  = trigger["kind"]

    # ── Performance ────────────────────────────────────────────────────
    ctr         = merchant["performance"]["ctr"]
    peer_ctr    = category.get("peer_stats", {}).get("avg_ctr", 0.03)
    peer_rating = category.get("peer_stats", {}).get("avg_rating", 4.2)
    gap         = max(peer_ctr - ctr, 0)
    missed      = int(gap * 1000)

    # ── Merchant context ───────────────────────────────────────────────
    signals       = merchant.get("signals", [])
    signal_str    = signals[0] if signals else None
    active_offers = [o["title"] for o in merchant.get("offers", []) if o.get("status") == "active"]
    offer_hint    = f"'{active_offers[0]}'" if active_offers else None
    rating        = merchant["performance"].get("rating", 0)
    lapsed        = merchant.get("customer_aggregate", {}).get("lapsed_180d_plus", 0)
    cat_digest    = category.get("digest", [])
    offer_catalog = category.get("offer_catalog", [])

    salutation = (f"Dr. {owner}" if owner else name) if category_type == "dentists" else (owner or name)

    # ── Defaults ───────────────────────────────────────────────────────
    body      = ""
    cta       = "take_action"
    send_as   = "vera"
    rationale = ""

    # ══════════════════════════════════════════════════════════════════
    # CASE 1 — PERFORMANCE DIP
    # ══════════════════════════════════════════════════════════════════
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

    # ══════════════════════════════════════════════════════════════════
    # CASE 2 — RESEARCH DIGEST
    # ══════════════════════════════════════════════════════════════════
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
                specificity_anchor = f" ({trial_n:,}-participant trial)"
            elif source:
                specificity_anchor = f" — {source}"
            else:
                specificity_anchor = ""

            if signal_str:
                merchant_hook = f" Your data already shows '{signal_str}' — this is timed well."
            elif lapsed > 0:
                merchant_hook = f" You have {lapsed} lapsed patients who could benefit from this."
            else:
                merchant_hook = ""

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
            if signal_str:
                body = (
                    f"{salutation}, a new industry update just landed for {category_type}.\n\n"
                    f"It aligns with your signal: '{signal_str}'.\n\n"
                    f"Want me to pull the summary and draft a campaign?"
                )
            else:
                body = (
                    f"{salutation}, a new industry update just landed for {category_type}.\n\n"
                    f"It may affect how your customers engage with your listing.\n\n"
                    f"Want me to pull the summary and draft a campaign?"
                )
            cta = "create_campaign"
            rationale = "Research digest trigger; no specific item matched — using signal as merchant hook."

    # ══════════════════════════════════════════════════════════════════
    # CASE 3 — FESTIVAL UPCOMING
    # ══════════════════════════════════════════════════════════════════
    elif trigger_kind == "festival_upcoming":
        festival  = trigger.get("payload", {}).get("festival_name", "the upcoming festival")
        has_offer = bool(active_offers)

        if has_offer:
            body = (
                f"{salutation}, {festival} is coming up \u2014 demand for {category_type} spikes this window.\n\n"
                f"Your {offer_hint} is already live. I can add a festival theme to the listing copy "
                f"and push it to the top of your profile \u2014 5 mins, zero budget.\n\n"
                f"Go ahead?"
            )
            cta = "promote_offer"
            rationale = (
                f"Existing offer {offer_hint} repositioned for {festival} with zero new spend. "
                f"Festival window creates timing urgency."
            )

        else:
            catalog_offer = offer_catalog[0]["title"] if offer_catalog else "a limited-time offer"
            body = (
                f"{salutation}, {festival} is coming \u2014 one of the highest-traffic windows for {category_type} listings.\n\n"
                f"A short-run offer (e.g. {catalog_offer}) timed to the festival consistently outperforms "
                f"always-on offers in this window. I can draft and activate it today.\n\n"
                f"Want to?"
            )
            cta = "activate_festival_campaign"
            rationale = (
                f"No active offer + festival upcoming. Festival-timed catalog offer is the "
                f"highest-ROI action for this window."
            )

    # ══════════════════════════════════════════════════════════════════
    # CASE 4 — CUSTOMER RECALL
    # ══════════════════════════════════════════════════════════════════
    elif trigger_kind == "recall_due" and customer:
        send_as    = "merchant_on_behalf"
        cust_name  = customer["identity"]["name"]
        last_visit = customer.get("last_visit_days_ago")
        state      = customer.get("state", "lapsed_soft")
        services   = customer.get("relationship", {}).get("services_received", [])
        pref_slot  = customer.get("preferences", {}).get("preferred_slots", "")

        last_service = services[-1] if services else None
        time_ref     = f"It's been {last_visit} days since your last visit." if last_visit else "Your routine recall is due."
        slot_hint    = f" We have {pref_slot.replace('_', ' ')} slots open." if pref_slot else ""
        service_ref  = f" (last: {last_service})" if last_service else ""

        body = (
            f"Hi {cust_name} \U0001f44b, {name} here.\n\n"
            f"{time_ref} Your routine checkup{service_ref} recall window is open.{slot_hint}\n\n"
            f"Reply to book \u2014 we'll confirm your slot within the hour."
        )
        cta = "slot_pick"
        rationale = (
            f"Recall due for {cust_name} (state={state}). "
            f"Message sent as merchant; references last service '{last_service}' "
            f"and slot preference for personalization."
        )

    # ══════════════════════════════════════════════════════════════════
    # CASE 5 — REGULATION CHANGE
    # ══════════════════════════════════════════════════════════════════
    elif trigger_kind == "regulation_change":
        reg_title  = trigger.get("payload", {}).get("title", "")
        if not reg_title:
            reg_title = next((d["title"] for d in cat_digest if d.get("kind") == "compliance"), "")
        actionable = next((d.get("actionable", "") for d in cat_digest if d.get("kind") == "compliance"), "")

        body = (
            f"{salutation}, a compliance update for {category_type} is live"
            f"{': ' + reg_title if reg_title else ''}.\n\n"
            f"{actionable + chr(10) + chr(10) if actionable else ''}"
            f"I can review your listing against this and flag what needs updating \u2014 5 min.\n\n"
            f"Proceed?"
        )
        cta = "yes_no"
        rationale = (
            f"Regulation change affecting {category_type}: '{reg_title}'. "
            f"Proactive compliance review protects listing from algorithmic demotion."
        )

    # ══════════════════════════════════════════════════════════════════
    # CASE 6 — LOW RATING / REVIEW ALERT
    # ══════════════════════════════════════════════════════════════════
    elif trigger_kind == "low_rating":
        peer_gap = round(peer_rating - rating, 1) if rating > 0 else 0

        body = (
            f"{salutation}, your rating is {rating}\u2b50 vs the {category_type} average of {peer_rating}\u2b50 in {city}."
        )
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
        rationale = (
            f"Rating {rating} is {peer_gap} below peer avg {peer_rating}. "
            f"With {lapsed} lapsed customers, review recovery is highest-ROI action."
        )

    # ══════════════════════════════════════════════════════════════════
    # DEFAULT — Unknown trigger kind (data-aware fallback)
    # ══════════════════════════════════════════════════════════════════
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