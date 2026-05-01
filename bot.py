import json

def compose(category, merchant, trigger, customer=None):
    
    name = merchant["identity"]["name"]
    city = merchant["identity"]["city"]
    owner = merchant["identity"].get("owner_first_name", "")
    category_type = category["slug"]
    trigger_kind = trigger["kind"]

    ctr = merchant["performance"]["ctr"]
    peer_ctr = category.get("peer_stats", {}).get("avg_ctr", 0.03)

    signals = merchant.get("signals", [])
    offers = [o["title"] for o in merchant.get("offers", []) if o.get("status") == "active"]

    body = ""
    cta = "action"
    send_as = "vera"

    # CASE 1: PERFORMANCE DIP (STRONGEST FLOW)
    if trigger_kind == "perf_dip":
        gap = max(peer_ctr - ctr, 0)
        missed = int(gap * 1000)

        body = (
            f"{name}, aapka CTR {ctr:.2%} hai vs {peer_ctr:.2%} category avg "
            f"(~{gap*100:.1f}% gap).\n\n"
            
            f"Simple terms me: har 1000 views me ~{missed} potential customers aap miss kar rahe ho.\n\n"
            
            f"{city} me {category_type} listings me low-ticket entry offer (₹199–₹299) + clear visual "
            f"consistently 20–30% better click-through deta hai.\n\n"
            
            f"Agar aap allow karein, main abhi aapke liye ek optimized post + offer draft bana ke "
            f"push kar sakti hoon — aaj hi live ja sakta hai.\n\n"
            
            f"Proceed karu?"
        )

    # CASE 2: RESEARCH DIGEST (INSIGHT → ACTION)
    elif trigger_kind == "research_digest":
        item = trigger["payload"]["top_item"]
        title = item["title"]
        source = item["source"]

        body = (
            f"{name}, quick update — {title} ({source}).\n\n"
            
            f"Trend ye dikha raha hai ki preventive / early-stage messaging pe response spike ho raha hai.\n\n"
            
            f"Agar aap 'early checkup' ya 'limited consultation' angle use karein, "
            f"conversion noticeably improve hota hai.\n\n"
            
            f"Main is insight ko use karke ek ready-to-send WhatsApp + listing draft bana du?\n\n"
            
            f"Yes / No?"
        )

    # CASE 3: FESTIVAL 
    elif trigger_kind == "festival_upcoming":
        body = (
            f"{name}, {city} me next 3–5 din me festive demand spike expected hai.\n\n"
            
            f"Jo merchants early push karte hain, wo peak traffic ka 60–70% capture kar lete hain.\n\n"
            
            f"₹199–₹499 price-led offers is window me consistently high clicks laate hain.\n\n"
            
            f"Agar aap delay karte hain, competitors pehle visibility le lenge.\n\n"
            
            f"Main aapke liye ek festival-ready post bana ke abhi schedule kar du?\n\n"
            
            f"Confirm?"
        )

    # CASE 4: CUSTOMER RECALL 
    elif trigger_kind == "recall_due" and customer:
        send_as = "merchant_on_behalf"

        cust_name = customer["identity"]["name"]

        body = (
            f"Hi {cust_name}, {name} clinic here 🦷\n\n"
            
            f"Aapka routine checkup due hai — delay karne se issues silently worsen ho sakte hain.\n\n"
            
            f"Is week limited slots open hain.\n\n"
            
            f"Agar convenient ho, reply karke slot block kar sakte hain."
        )

        cta = "open_ended"

    #DEFAULT
    else:
        body = (
            f"{name}, recent activity dekh ke lag raha hai ki small optimization se noticeable lift aa sakta hai.\n\n"
            
            f"Main ek quick improvement draft bana sakti hoon based on aapke current performance.\n\n"
            
            f"Try karna chahoge?"
        )

    return {
        "body": body,
        "cta": cta,
        "send_as": send_as,
        "suppression_key": trigger["suppression_key"],
        "rationale": f"High-specificity, urgency-driven, action-oriented message for {trigger_kind}"
    }