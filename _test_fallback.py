"""Fallback path test."""
import os
os.environ["GROQ_API_KEY"] = ""
import bot
bot._groq_client = None

cat = {
    "slug": "dentists",
    "voice": {"tone": "peer_clinical", "vocab_allowed": ["fluoride", "caries"], "taboos": []},
    "peer_stats": {"avg_ctr": 0.030, "avg_rating": 4.4, "avg_review_count": 62},
    "digest": [{"id": "d_001", "kind": "research", "title": "3-month fluoride recall cuts caries 38%",
                "source": "JIDA Oct 2026, p.14", "trial_n": 2100,
                "patient_segment": "high_risk_adults", "actionable": "Reassess recall interval"}],
    "offer_catalog": [{"id": "den_001", "title": "Dental Cleaning @ Rs 299"}],
    "seasonal_beats": [], "trend_signals": []
}
m = {
    "identity": {"name": "Dr. Meera Clinic", "city": "Delhi",
                 "owner_first_name": "Meera", "languages": ["en", "hi"], "locality": "Lajpat Nagar"},
    "performance": {"ctr": 0.021, "rating": 3.8, "views": 2410, "calls": 18, "delta_7d": {"views_pct": 0.35}},
    "subscription": {"status": "active", "plan": "Pro", "days_remaining": 82},
    "signals": ["stale_posts:22d", "ctr_below_peer_median"],
    "offers": [{"title": "Dental Cleaning @ Rs 299", "status": "active"}],
    "customer_aggregate": {"lapsed_180d_plus": 78, "total_unique_ytd": 540, "retention_6mo_pct": 0.38},
    "conversation_history": []
}

triggers = [
    {"kind": "perf_dip",          "suppression_key": "s1", "payload": {}},
    {"kind": "research_digest",   "suppression_key": "s2", "payload": {"top_item_id": "d_001"}},
    {"kind": "festival_upcoming", "suppression_key": "s3", "payload": {"festival_name": "Diwali", "days_away": 4}},
    {"kind": "regulation_change", "suppression_key": "s5", "payload": {"title": "DCI update", "effective_date": "2026-12-15"}},
    {"kind": "low_rating",        "suppression_key": "s6", "payload": {}},
    {"kind": "perf_spike",        "suppression_key": "s8", "payload": {}, "urgency": 3},
    {"kind": "dormant_with_vera", "suppression_key": "s9", "payload": {"days_dormant": 14}},
    {"kind": "milestone_reached", "suppression_key": "s10", "payload": {"milestone": "100 reviews"}},
]

KEYS = {"body", "cta", "send_as", "suppression_key", "rationale"}
all_ok = True
for trg in triggers:
    r = bot._compose_fallback(cat, m, trg, None)
    miss = KEYS - set(r.keys())
    ok = "PASS" if not miss and r.get("body") else "FAIL"
    if ok == "FAIL":
        all_ok = False
    k = trg["kind"]
    print(f"[{ok}] {k:25s} cta={r['cta']:25s} body_len={len(r.get('body',''))}")

print()
print("Dentist perf_dip body snippet:")
r0 = bot._compose_fallback(cat, m, {"kind": "perf_dip", "suppression_key": "x1", "payload": {}}, None)
print(r0["body"][:400])
print()

# Restaurant test
cat2 = {
    "slug": "restaurants",
    "voice": {"tone": "warm_busy_practical", "vocab_allowed": ["footfall","covers","AOV"], "taboos": []},
    "peer_stats": {"avg_ctr": 0.025, "avg_rating": 4.2, "avg_review_count": 142},
    "digest": [{"id": "r_001", "kind": "trend", "title": "IPL match nights up 18% covers",
                "source": "magicpin data Apr 2026", "actionable": "Push match combos on Tue/Wed/Thu"}],
    "offer_catalog": [{"id": "res_003", "title": "Weekday Lunch Thali @ Rs149"}],
    "seasonal_beats": [], "trend_signals": []
}
m2 = {
    "identity": {"name": "Pizza Junction", "city": "Delhi", "owner_first_name": "Rahul",
                 "languages": ["en"], "locality": "Connaught Place"},
    "performance": {"ctr": 0.018, "rating": 4.3, "views": 4200, "calls": 35, "delta_7d": {"views_pct": 0.28}},
    "subscription": {"status": "active", "plan": "Pro", "days_remaining": 45},
    "signals": ["stale_posts:15d"],
    "offers": [],
    "customer_aggregate": {"lapsed_180d_plus": 120, "total_unique_ytd": 800, "retention_6mo_pct": 0.18},
    "conversation_history": []
}
trg2 = {"kind": "research_digest", "suppression_key": "r1", "payload": {"top_item_id": "r_001"}}
r2 = bot._compose_fallback(cat2, m2, trg2, None)
print("RESTAURANT research_digest body:")
print(r2["body"])

print()
print("ALL PASS" if all_ok else "SOME FAILURES — check above")
