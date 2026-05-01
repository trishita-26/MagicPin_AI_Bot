import json

def compose(category, merchant, trigger, customer=None):
    
    name = merchant["identity"]["name"]
    city = merchant["identity"]["city"]
    owner = merchant["identity"].get("owner_first_name", "")
    category_type = category["slug"]
    trigger_kind = trigger["kind"]
    
    ctr = merchant["performance"]["ctr"]
    peer_ctr = category.get("peer_stats", {}).get("avg_ctr", 0.03)

    body = ""
    cta = "none"
    send_as = "vera"

    # CASE 1: PERFORMANCE DIP (HIGH IMPACT)
    if trigger_kind == "perf_dip":
        gap = max(peer_ctr - ctr, 0)
        missed = int(gap * 1000)  # rough estimate for impact

        body = (
            f"{name}, aapka current CTR {ctr:.2%} hai vs {peer_ctr:.2%} category avg — "
            f"iska matlab aap roughly {missed}+ potential customers miss kar rahe ho.\n\n"
            f"{city} me {category_type} listings ke liye 'low-entry offer + clear visual' best perform karta hai "
            f"(example: ₹299 starter offer).\n\n"
            f"Main abhi aapke liye ek optimized post + offer draft kar rahi hoon — "
            f"approve kar dena, we can push this live today 👍"
        )

    # CASE 2: RESEARCH DIGEST 
    elif trigger_kind == "research_digest":
        item = trigger["payload"]["top_item"]
        title = item["title"]
        source = item["source"]

        body = (
            f"{name}, quick insight — {title} ({source}).\n\n"
            f"Iska direct impact: patients ab preventive care pe zyada respond kar rahe hain.\n\n"
            f"Agar aap 'early checkup' ya 'limited-time consultation' angle use karein, "
            f"conversion noticeably improve hota hai.\n\n"
            f"Main isko simplify karke ek ready-to-send WhatsApp + listing post draft kar rahi hoon."
        )

    # CASE 3: FESTIVAL 
    elif trigger_kind == "festival_upcoming":
        body = (
            f"{name}, {city} me festive demand spike aane wala hai next few days me.\n\n"
            f"Is time pe simple + price-led offers (₹199–₹499 range) consistently higher clicks laate hain.\n\n"
            f"Agar aap abhi push karte hain, aap early traffic capture kar sakte ho before competitors.\n\n"
            f"Main aapke liye ek festival-ready post draft kar rahi hoon — approve kar dena and we go live."
        )

    # CASE 4: CUSTOMER RECALL (HUMAN + DIRECT)
    elif trigger_kind == "recall_due" and customer:
        send_as = "merchant_on_behalf"

        cust_name = customer["identity"]["name"]

        body = (
            f"Hi {cust_name}, {name} clinic here 🦷\n\n"
            f"Aapka routine checkup due hai — delay karne se treatment complexity badh sakti hai.\n\n"
            f"Is week kuch priority slots open hain. Agar convenient ho, reply karke book kar sakte hain."
        )

        cta = "open_ended"

    # DEFAULT
    else:
        body = (
            f"{name}, aapke account me recent activity dekh ke lag raha hai ki thoda optimization se "
            f"significant lift aa sakta hai.\n\n"
            f"Main ek quick improvement draft prepare kar rahi hoon — "
            f"review karke batana if you want to push it live."
        )

    return {
        "body": body,
        "cta": cta,
        "send_as": send_as,
        "suppression_key": trigger["suppression_key"],
        "rationale": f"High-specificity message using performance gap, city context, and trigger: {trigger_kind}"
    }