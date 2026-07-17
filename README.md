# Magicpin AI Bot — Vera

An LLM-powered merchant growth assistant built for the **magicpin AI Challenge**.  
Vera talks to merchants and customers on WhatsApp, composes data-driven messages,  
and drives growth actions across 9 trigger kinds.

---

## Architecture

```
Judge → POST /v1/context   → stores in CONTEXTS dict (scope, context_id, version)
Judge → POST /v1/tick      → compose(category, merchant, trigger, customer?)
                               │
                               ├─ Groq LLM (llama-3.3-70b-versatile, temp=0)
                               │    ├─ Trigger-aware anchor injector
                               │    ├─ Specificity quality gate + retry
                               │    └─ 320-char hard cap enforced
                               │
                               └─ Rule-based fallback (if Groq fails/times out)
                                    └─ 9 trigger kinds handled deterministically

Judge → POST /v1/reply     → pulls CONVERSATIONS[conv_id] for history
                               ├─ Auto-reply / STOP detection (no LLM)
                               ├─ Groq LLM with role-split prompt (merchant vs customer)
                               └─ Rule-based fallback with grounded tech responses
```

---

## API Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/v1/healthz` | GET | Returns `uptime_seconds` + `contexts_loaded` counts |
| `/v1/metadata` | GET | Bot identity and approach |
| `/v1/context` | POST | Receives category / merchant / customer / trigger contexts |
| `/v1/tick` | POST | Processes triggers → composed actions with `conversation_id`, `template_name`, `template_params` |
| `/v1/reply` | POST | Context-aware multi-turn reply handler |
| `/v1/teardown` | POST | Wipes in-memory state at test end |

---

## Key Design Decisions

### Specificity (target: 9/10)
- **Trigger-aware anchor injector** (`_build_anchor()`) computes the single most-impactful data point per trigger kind (lapsed count, CTR gap, spike %, festival days) and injects it as `PRIMARY ANCHOR — use in sentence 1` at the top of every Groq prompt.
- **Specificity quality gate** (`_validate_specificity()`) rejects LLM output with no real numbers and retries once with a stricter prompt before falling back to the deterministic composer.
- **320-char hard cap** (`_trim_body()`) enforced on every outgoing body — cuts at sentence boundary and preserves the trailing CTA.

### Category Fit (target: 10/10)
- Per-category voice profile (tone, allowed vocab, taboo words) injected into the system prompt.
- 9 supported categories: dentists, salons, restaurants, gyms, clinics, pharmacies, jewellers, spas, and a generic fallback.

### Merchant Fit (target: 8/10)
- Full merchant state (CTR, lapsed count, active offers, conversation history, customer aggregate) passed in every Groq call.
- Anchor injector front-loads the trigger-relevant fact so the LLM uses the right number, not just any number.

### Engagement Compulsion (target: 9/10)
- System prompt enumerates all 8 engagement levers: loss aversion, social proof, curiosity, effort externalization, authority signal, scarcity, direct question, and binary CTA.
- Hindi-English code-mix auto-enabled when `identity.languages` includes `"hi"`.

### Multi-turn Reply
- **Role-split prompt**: `from_role=customer` → Vera speaks as the merchant; `from_role=merchant` → Vera speaks as herself.
- **Customer branches**: booking with exact slot echo, reschedule, info questions (price/duration/procedure), Hindi replies.
- **Merchant branches**: short commit → immediate draft; technical context (D-speed, RVG, CBCT, autoclave, Schedule H) → grounded one-liner before re-anchoring to the draft task.
- Auto-reply and STOP detection are handled deterministically (no LLM cost) on the fast path.

### Reliability
- Groq failures / timeouts → deterministic rule-based fallback, always responds in < 1s.
- `SENT_SUPPRESSIONS` set prevents re-sending the same trigger twice in a test window.
- `CONVERSATIONS` dict persists merchant / trigger / history across the 5-turn replay test.
- Groq JSON mode (`response_format={"type": "json_object"}`) prevents markdown wrapping.

---

## Running Locally

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set env variable
# Create a .env file or export directly:
GROQ_API_KEY=your_groq_api_key_here

# 3. Start the server
python -m uvicorn main:app --reload --port 8080

# 4. Run the judge simulator
python judge_simulator.py
```

---

## Testing

```bash
# Unit tests (bot compose logic)
python -m pytest test_bot.py -v

# Integration tests (FastAPI endpoints)
python -m pytest test_integration.py -v

# Full judge simulator run
python judge_simulator.py
```

---

## Score Breakdown (v3)

| Dimension | Score | Notes |
|---|---|---|
| Decision Quality | 9/10 | Correct action at every turn |
| Specificity | ~8/10 | Anchor injector + quality gate |
| Category Fit | 10/10 | Voice profile per category |
| Merchant Fit | ~8/10 | Trigger-aware anchor front-loads right fact |
| Engagement Compulsion | 8/10 | All 8 levers in system prompt |
| **Estimated Total** | **~83–87** | Up from original score of 69 |

---

## Project Structure

```
MagicPin_AI_Bot/
├── bot.py                  # Vera compose engine (Groq LLM + rule-based fallback)
├── main.py                 # FastAPI app — all 6 endpoints + reply handler
├── judge_simulator.py      # Local judge harness (provided by magicpin)
├── requirements.txt        # Dependencies
├── test_bot.py             # Unit tests for compose logic
├── test_integration.py     # FastAPI endpoint integration tests
├── test_judge_sim.py       # Judge simulator test suite
├── dataset/                # Merchant + category context fixtures
├── examples/               # Example trigger payloads
└── .env                    # GROQ_API_KEY (not committed)
```

---

## Author

**Trisita Ghosh**  
B.Tech CSE (AI & ML)
