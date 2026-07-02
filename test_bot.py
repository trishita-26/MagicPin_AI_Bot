import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from bot import compose

cat = {
    "slug": "dentists",
    "peer_stats": {"avg_ctr": 0.030, "avg_rating": 4.4, "avg_review_count": 62},
    "digest": [
        {"id": "d_001", "kind": "research",
         "title": "3-month fluoride recall cuts caries 38% better",
         "source": "JIDA Oct 2026, p.14", "trial_n": 2100,
         "actionable": "Reassess recall interval for high-risk adults"},
        {"id": "d_comp", "kind": "compliance",
         "title": "DCI radiograph dose limits revised",
         "source": "DCI circular 2026-11-04",
         "actionable": "Audit your X-ray setup before Dec 15"},
    ],
    "offer_catalog": [{"id": "den_001", "title": "Dental Cleaning @ Rs 299"}]
}
m = {
    "identity": {"name": "Dr. Meera Clinic", "city": "Delhi",
                 "owner_first_name": "Meera", "languages": ["en", "hi"]},
    "performance": {"ctr": 0.021, "rating": 3.8, "views": 2410, "calls": 18},
    "signals": ["stale_posts:22d", "ctr_below_peer_median"],
    "offers": [{"title": "Dental Cleaning @ Rs 299", "status": "active"}],
    "customer_aggregate": {"lapsed_180d_plus": 78, "retention_6mo_pct": 0.38}
}
cust = {
    "identity": {"name": "Priya"},
    "last_visit_days_ago": 152,
    "state": "lapsed_soft",
    "relationship": {"services_received": ["cleaning", "whitening", "cleaning"]},
    "preferences": {"preferred_slots": "weekday_evening"}
}

KEYS = {"body", "cta", "send_as", "suppression_key", "rationale"}
cases = [
    ("perf_dip",     {"kind": "perf_dip", "suppression_key": "s1"}, None),
    ("research",     {"kind": "research_digest", "suppression_key": "s2", "payload": {"top_item_id": "d_001"}}, None),
    ("festival",     {"kind": "festival_upcoming", "suppression_key": "s3", "payload": {"festival_name": "Diwali"}}, None),
    ("recall",       {"kind": "recall_due", "suppression_key": "s4"}, cust),
    ("regulation",   {"kind": "regulation_change", "suppression_key": "s5", "payload": {"title": "DCI update"}}, None),
    ("low_rating",   {"kind": "low_rating", "suppression_key": "s6"}, None),
    ("default",      {"kind": "unknown_trigger", "suppression_key": "s7"}, None),
]

all_ok = True
for lbl, trg, cu in cases:
    r = compose(cat, m, trg, cu)
    miss = KEYS - set(r.keys())
    rat  = bool(r.get("rationale", "").strip())
    bod  = bool(r.get("body", "").strip())
    st   = "PASS" if (not miss and rat and bod) else "FAIL"
    if st == "FAIL":
        all_ok = False
    print(f"[{st}] {lbl} | cta={r['cta']} | rationale={rat} | missing_keys={miss}")

print()
print("ALL PASS" if all_ok else "SOME FAILURES")
