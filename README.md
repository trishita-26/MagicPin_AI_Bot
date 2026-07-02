# 🚀 Magicpin AI Bot — Vera v2.0

An LLM-powered merchant growth assistant for the magicpin AI Challenge. Vera talks to merchants on WhatsApp, composes data-driven messages, and drives them toward growth actions.

---

## 🎯 Approach

**Primary composer**: Groq LLM (`llama-3.3-70b-versatile`) with a structured 4-context prompt that explicitly targets all 5 evaluation dimensions:

1. **Specificity** — anchors on verifiable numbers from the data (CTR %, peer stats, trial sizes, lapsed counts)
2. **Category fit** — voice profile (tone, taboo words, allowed vocab) injected into system prompt per category
3. **Merchant fit** — full merchant state (offers, signals, customer aggregate, conversation history) in prompt
4. **Trigger relevance** — trigger kind + payload passed directly; LLM explains "why now"
5. **Engagement compulsion** — system prompt enumerates all 8 levers; Hindi-English mix enabled per `identity.languages`

**Fallback**: Deterministic rule-based composer (no LLM) activates if Groq fails or times out — handles 9 trigger kinds.

**Multi-turn**: `/v1/reply` passes conversation history + merchant context to Groq for context-aware replies. Auto-reply and STOP detection happen first (no LLM needed) for speed.

---

## 🔌 API Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /v1/healthz` | Returns `uptime_seconds` + `contexts_loaded` counts per scope |
| `GET /v1/metadata` | Bot identity and approach |
| `POST /v1/context` | Receives category/merchant/customer/trigger contexts; version-idempotent |
| `POST /v1/tick` | Processes triggers → returns composed actions with `conversation_id`, `template_name`, `template_params` |
| `POST /v1/reply` | Context-aware multi-turn reply handler |
| `POST /v1/teardown` | Wipes in-memory state at test end |

---

## 🧠 Architecture

```
Judge → /v1/context  → stores in CONTEXTS dict (scope, context_id) → version
Judge → /v1/tick     → compose(category, merchant, trigger, customer)
                           ↓ Groq LLM (primary)
                           ↓ Rule-based (fallback)
                     → returns actions[] with full spec schema
Judge → /v1/reply    → pulls CONVERSATIONS[conv_id] for history
                     → Groq LLM with full context
                     → returns send/wait/end
```

---

## 💡 Key Design Decisions

- **LLM for quality, rules for reliability** — Groq at temperature=0 gives deterministic LLM outputs; the rule-based fallback ensures <30s responses even under API failure
- **JSON mode** — `response_format={"type": "json_object"}` prevents Groq from wrapping output in markdown
- **Suppression dedup** — `SENT_SUPPRESSIONS` set prevents re-sending the same trigger twice per test window
- **Conversation state** — `CONVERSATIONS` dict persists merchant/trigger/history across the 5-turn replay test
- **Hindi-English code-mix** — activated automatically when `identity.languages` includes `"hi"`

---

## 🚀 Running Locally

```bash
pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8080
```

Set your env:
```
GROQ_API_KEY=your_groq_api_key
```

Test:
```bash
python judge_simulator.py
```

---

## 📈 What Improved vs v1

| Area | v1 | v2 |
|---|---|---|
| Composer | Rule-based only | Groq LLM + rule fallback |
| Category voice | Ignored | Enforced via system prompt |
| Hindi support | None | Auto-detected from `languages` |
| `/v1/healthz` | Missing `contexts_loaded` | Full spec compliant |
| `/v1/context` | No version check | 409 on stale version |
| `/v1/tick` | Missing `conversation_id`, `template_name` | Full spec compliant |
| `/v1/reply` | Stateless keyword matching | Context-aware Groq + conversation history |
| Trigger coverage | 6 kinds | 9 kinds + generic fallback |
| Compulsion levers | 2 (loss aversion, effort ext.) | All 8 in system prompt |

---

## 👤 Author

Trisita Ghosh  
B.Tech CSE (AI & ML)
