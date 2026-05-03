import random


def compose(category, merchant, trigger, customer=None):

    # ── Identity ───────────────────────────────────────────────────────
    name          = merchant["identity"]["name"]
    city          = merchant["identity"]["city"]
    owner         = merchant["identity"].get("owner_first_name", "")
    category_type = category["slug"]
    trigger_kind  = trigger["kind"]

    # ── Performance ────────────────────────────────────────────────────
    ctr      = merchant["performance"]["ctr"]
    peer_ctr = category.get("peer_stats", {}).get("avg_ctr", 0.03)
    gap      = max(peer_ctr - ctr, 0)
    missed   = int(gap * 1000)                        # missed clicks per 1k views

    # ── Merchant context ───────────────────────────────────────────────
    signals       = merchant.get("signals", [])
    signal_str    = signals[0] if signals else None
    active_offers = [o["title"] for o in merchant.get("offers", []) if o.get("status") == "active"]
    offer_hint    = f"'{active_offers[0]}'" if active_offers else None

    # ── Defaults ───────────────────────────────────────────────────────
    body    = ""
    cta     = "yes_no"
    send_as = "vera"

    # ══════════════════════════════════════════════════════════════════
    # CASE 1 — PERFORMANCE DIP
    # Goal: make the loss feel real, then offer a precise fix
    # ══════════════════════════════════════════════════════════════════
    if trigger_kind == "perf_dip":
        offer_line = (
            f"Aapka existing offer {offer_hint} ek solid base hai — "
            f"sirf positioning aur visual tweak chahiye."
            if offer_hint else
            f"{city} me {category_type} listings me ₹199–₹299 entry offer + "
            f"clear visual consistently 20–30% better CTR deta hai."
        )

        body = (
            f"{name}, ek important update — aapka CTR abhi {ctr:.2%} hai "
            f"jabki {city} me {category_type} category avg {peer_ctr:.2%} hai "
            f"(~{gap*100:.1f}% gap).\n\n"

            f"Real-world mein iska matlab: har 1,000 views me se ~{missed} potential "
            f"customers aap tak aa sakte the — lekin listing dekh ke bounce kar gaye.\n\n"

            f"{offer_line}\n\n"

            f"Main abhi aapke liye ek optimized post + offer draft karke ready kar sakti hoon "
            f"— aaj hi live ja sakta hai, zero extra effort aapki taraf se.\n\n"

            f"Proceed karoon? ✅ / ❌"
        )
        cta = "yes_no"

    # ══════════════════════════════════════════════════════════════════
    # CASE 2 — RESEARCH DIGEST
    # Goal: make the insight feel urgent + tie it to merchant's own data
    # ══════════════════════════════════════════════════════════════════
    elif trigger_kind == "research_digest":
        item   = trigger["payload"]["top_item"]
        title  = item["title"]
        source = item["source"]

        signal_line = (
            f"Aur aapke apne data me bhi '{signal_str}' signal aa raha hai — "
            f"yeh trend aapke liye perfectly timed hai."
            if signal_str else
            f"{city} me is trend pe jo merchants fast move karte hain "
            f"wo typically 2–3x higher engagement capture karte hain."
        )

        body = (
            f"{name}, ek relevant industry update aaya hai — "
            f"{title} ({source}).\n\n"

            f"Key takeaway: preventive + early-stage messaging pe patient/customer response "
            f"strongly spike ho raha hai is quarter.\n\n"

            f"{signal_line}\n\n"

            f"Main is insight ko directly use karke aapke liye ek "
            f"ready-to-send WhatsApp message + listing post draft karti hoon "
            f"— aapko sirf approve karna hoga.\n\n"

            f"Draft kaaron? Yes / No"
        )
        cta = "yes_no"

    # ══════════════════════════════════════════════════════════════════
    # CASE 3 — FESTIVAL UPCOMING
    # Goal: FOMO + early-mover advantage + concrete ask
    # ══════════════════════════════════════════════════════════════════
    elif trigger_kind == "festival_upcoming":
        festival = trigger.get("payload", {}).get("festival_name", "upcoming festival")

        offer_line = (
            f"Aapka {offer_hint} offer is season ke liye great fit hai — "
            f"sirf ek festive angle add karna hoga."
            if offer_hint else
            f"₹199–₹499 price-led festival offers {city} me is window me "
            f"consistently highest clicks laate hain."
        )

        body = (
            f"{name}, {festival} aa raha hai — aur {city} me "
            f"is category me demand already pick up ho rahi hai.\n\n"

            f"Historical data: jo merchants 3–4 din pehle push karte hain "
            f"wo peak traffic ka ~65% capture kar lete hain. "
            f"Last-minute push karne walon ko sirf leftover traffic milta hai.\n\n"

            f"{offer_line}\n\n"

            f"Main abhi ek festival-ready post + offer draft karke schedule kar sakti hoon "
            f"— aapko sirf green light dena hai.\n\n"

            f"Confirm karein? ✅"
        )
        cta = "yes_no"

    # ══════════════════════════════════════════════════════════════════
    # CASE 4 — CUSTOMER RECALL
    # Goal: warm, personal nudge sent on behalf of merchant TO customer
    # ══════════════════════════════════════════════════════════════════
    elif trigger_kind == "recall_due" and customer:
        send_as   = "merchant_on_behalf"
        cust_name = customer["identity"]["name"]
        last_visit = customer.get("last_visit_days_ago")

        time_line = (
            f"Aapka last visit ~{last_visit} din pehle tha — "
            f"routine checkup overdue ho gaya hai."
            if last_visit else
            f"Aapka routine checkup due ho gaya hai."
        )

        body = (
            f"Hi {cust_name} 👋, {name} ki taraf se!\n\n"

            f"{time_line} "
            f"Chhoti si delay bhi silently issues worsen kar sakti hai.\n\n"

            f"Is week humare paas kuch limited slots hain. "
            f"Aapke liye convenient time kaunsa rahega?\n\n"

            f"Bas reply karein — hum slot confirm kar denge. 🦷"
        )
        cta = "slot_pick"

    # ══════════════════════════════════════════════════════════════════
    # CASE 5 — REGULATION CHANGE
    # Goal: position bot as a helpful advisor, not an alarm
    # ══════════════════════════════════════════════════════════════════
    elif trigger_kind == "regulation_change":
        reg_title = trigger.get("payload", {}).get("title", "ek nayi regulatory update")

        body = (
            f"{name}, {city} me {category_type} category ke liye "
            f"ek compliance update aaya hai — {reg_title}.\n\n"

            f"Iska direct impact aapke listing copy aur offer terms pe pad sakta hai. "
            f"Jo merchants proactively update karte hain unhe algorithm me bhi preference milti hai.\n\n"

            f"Main aapke current listing ko is update ke against review karke "
            f"required changes highlight kar sakti hoon — 5 min ka kaam hai.\n\n"

            f"Kaaron? Yes / No"
        )
        cta = "yes_no"

    # ══════════════════════════════════════════════════════════════════
    # CASE 6 — LOW RATING / REVIEW ALERT
    # ══════════════════════════════════════════════════════════════════
    elif trigger_kind == "low_rating":
        rating     = merchant["performance"].get("rating", "?")
        peer_rating = category.get("peer_stats", {}).get("avg_rating", 4.2)

        body = (
            f"{name}, aapki current rating {rating}⭐ hai "
            f"jabki {city} me {category_type} avg {peer_rating}⭐ hai.\n\n"

            f"Rating gap directly listing clicks ko affect karta hai — "
            f"~0.5 star improvement se CTR 15–25% improve ho sakta hai.\n\n"

            f"Main aapke liye ek targeted review generation message draft kar sakti hoon "
            f"jo recent happy customers ko politely nudge kare.\n\n"

            f"Try karein? ✅ / ❌"
        )
        cta = "yes_no"

    # ══════════════════════════════════════════════════════════════════
    # DEFAULT — Unknown trigger kind (data-aware fallback)
    # ══════════════════════════════════════════════════════════════════
    else:
        gap_line = (
            f"Abhi aapka CTR {ctr:.2%} hai vs {peer_ctr:.2%} category avg — "
            f"~{missed} extra clicks per 1k views possible hain."
            if missed > 0 else
            f"Aapki listing {city} me solid position pe hai — "
            f"aur thodi si push se aur upar ja sakti hai."
        )

        body = (
            f"{name}, {gap_line}\n\n"

            f"Main aapke current setup ko quickly audit karke "
            f"ek high-impact improvement identify kar sakti hoon.\n\n"

            f"5 min denge? Main draft ready kar leti hoon."
        )
        cta = "yes_no"

    return {
        "body":           body,
        "cta":            cta,
        "send_as":        send_as,
        "suppression_key": trigger["suppression_key"],
        "rationale": (
            f"Trigger={trigger_kind} | CTR gap={gap*100:.1f}% | "
            f"missed={missed}/1k | offers={'yes' if active_offers else 'none'} | "
            f"signals={'yes' if signals else 'none'}"
        ),
    }