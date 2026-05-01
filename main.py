from fastapi import FastAPI
from typing import Dict, Any
from bot import compose

app = FastAPI()

# In-memory storage
CATEGORIES = {}
MERCHANTS = {}
TRIGGERS = {}
CUSTOMERS = {}

# Health check
@app.get("/v1/healthz")
def healthz():
    return {"status": "ok"}

# Metadata
@app.get("/v1/metadata")
def metadata():
    return {
        "team_name": "Trisita_AI",
        "model": "openrouter"
    }

#  Context ingestion
@app.post("/v1/context")
def context(data: Dict[str, Any]):
    scope = data["scope"]
    cid = data["context_id"]
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

# Tick (main scoring call)
@app.post("/v1/tick")
def tick(data: Dict[str, Any]):
    actions = []

    for tid in data.get("available_triggers", []):
        trigger = TRIGGERS.get(tid)
        if not trigger:
            continue

        mid = trigger.get("merchant_id")
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
            "trigger_id": tid,
            "customer_id": cid,
        })

        actions.append(action)

    return {"actions": actions}

#  Reply handling
@app.post("/v1/reply")
def reply(data: Dict[str, Any]):
    msg = data.get("message", "").lower()

    # Auto-reply detection
    if "thank you" in msg or "will respond shortly" in msg:
        return {"action": "end"}

    # Hostile handling
    if "stop" in msg or "spam" in msg:
        return {"action": "end"}

    # INTENT DETECTION (commitment)
    if any(x in msg for x in ["ok", "yes", "let's", "lets", "do it", "what next", "next"]):
        return {
            "action": "send",
            "body": "Great — I’ll draft a high-converting post + offer for you. Give me a moment 👍",
            "cta": "none",
            "send_as": "vera"
        }

    # default
    return {
        "action": "wait",
        "wait_seconds": 5
    }