"""
Simulate the judge scoring across multiple trigger types.
Tests: research_digest, perf_dip, festival_upcoming, recall_due, regulation_change, perf_spike
"""
import requests
import json

base = 'http://localhost:8081'

# ── Base contexts ─────────────────────────────────────────────────────────────
category_dentists = {
    'slug': 'dentists',
    'offer_catalog': [
        {'title': 'Dental Cleaning @ Rs.299'},
        {'title': 'Teeth Whitening @ Rs.1499'},
        {'title': 'Free Consultation'},
    ],
    'voice': {
        'tone': 'peer_clinical',
        'vocab_allowed': ['fluoride varnish', 'caries', 'bruxism', 'recall'],
        'taboos': ['cure', 'guaranteed', 'best dentist']
    },
    'peer_stats': {'avg_rating': 4.4, 'avg_ctr': 0.030, 'avg_reviews': 62},
    'digest': [
        {
            'id': 'd1',
            'kind': 'research',
            'title': '3-mo fluoride recall cuts caries recurrence 38% better than 6-mo',
            'source': 'JIDA Oct 2026, p.14',
            'trial_n': 2100,
            'patient_segment': 'high_risk_adults',
            'actionable': 'Shift high-risk adult recall intervals to 3 months'
        }
    ],
    'seasonal_beats': [
        {'month_range': 'Nov-Feb', 'note': 'exam-stress bruxism spike'},
        {'month_range': 'Oct-Dec', 'note': 'wedding whitening peak'}
    ],
    'trend_signals': [
        {'query': 'clear aligners delhi', 'delta_yoy': 0.62, 'segment_age': '28-45'}
    ]
}

merchant_drmeera = {
    'merchant_id': 'm_001_drmeera',
    'category_slug': 'dentists',
    'identity': {
        'name': "Dr. Meera's Dental Clinic",
        'owner_first_name': 'Meera',
        'city': 'Delhi',
        'locality': 'Lajpat Nagar',
        'languages': ['en', 'hi'],
        'verified': True
    },
    'subscription': {'status': 'active', 'plan': 'Pro', 'days_remaining': 82},
    'performance': {
        'views': 2410, 'calls': 18, 'ctr': 0.021,
        'rating': 3.8,
        'delta_7d': {'views_pct': 0.05, 'calls_pct': -0.12}
    },
    'offers': [{'id': 'o1', 'title': 'Dental Cleaning @ Rs.299', 'status': 'active'}],
    'signals': ['stale_posts:22d', 'ctr_below_peer_median', 'high_risk_adult_cohort'],
    'customer_aggregate': {'total_unique_ytd': 540, 'lapsed_180d_plus': 78, 'retention_6mo_pct': 0.38},
    'conversation_history': []
}

merchant_salon = {
    'merchant_id': 'm_002_salon',
    'category_slug': 'salons',
    'identity': {
        'name': "Studio11 Family Salon",
        'owner_first_name': 'Priya',
        'city': 'Hyderabad',
        'locality': 'Banjara Hills',
        'languages': ['en', 'hi'],
        'verified': True
    },
    'subscription': {'status': 'active', 'plan': 'Basic', 'days_remaining': 14},
    'performance': {
        'views': 1850, 'calls': 9, 'ctr': 0.018,
        'rating': 4.9,
        'delta_7d': {'views_pct': 0.28, 'calls_pct': 0.15}
    },
    'offers': [],
    'signals': ['ctr_below_peer_median'],
    'customer_aggregate': {'total_unique_ytd': 280, 'lapsed_180d_plus': 45, 'retention_6mo_pct': 0.55},
    'conversation_history': []
}

category_salons = {
    'slug': 'salons',
    'offer_catalog': [
        {'title': 'Haircut @ Rs.99'},
        {'title': 'Hair Color @ Rs.499'},
        {'title': 'Bridal Package @ Rs.2999'},
    ],
    'voice': {'tone': 'friendly_aspirational', 'vocab_allowed': [], 'taboos': ['cheapest', 'dirty']},
    'peer_stats': {'avg_rating': 4.3, 'avg_ctr': 0.028, 'avg_reviews': 44},
    'digest': [],
    'seasonal_beats': [{'month_range': 'Oct-Dec', 'note': 'wedding season peak'}],
    'trend_signals': []
}

customer_priya = {
    'customer_id': 'c_001_priya',
    'merchant_id': 'm_001_drmeera',
    'identity': {'name': 'Priya', 'language_pref': 'hi-en mix'},
    'relationship': {
        'first_visit': '2025-11-04', 'last_visit': '2026-01-12',
        'visits_total': 4,
        'services_received': ['cleaning', 'cleaning', 'whitening', 'cleaning']
    },
    'last_visit_days_ago': 171,
    'state': 'lapsed_soft',
    'preferences': {'preferred_slots': 'weekday_evening', 'channel': 'whatsapp'},
    'consent': {'opted_in_at': '2025-11-04', 'scope': ['recall_reminders', 'appointment_reminders']}
}

# Push all contexts
def push(scope, cid, payload, version=1):
    r = requests.post(f'{base}/v1/context', json={
        'scope': scope, 'context_id': cid, 'version': version,
        'payload': payload, 'delivered_at': '2026-07-02T00:00:00Z'
    })
    return r.json()

push('category', 'dentists', category_dentists)
push('category', 'salons', category_salons)
push('merchant', 'm_001_drmeera', merchant_drmeera)
push('merchant', 'm_002_salon', merchant_salon)
push('customer', 'c_001_priya', customer_priya)

# ── Test triggers ─────────────────────────────────────────────────────────────
test_cases = [
    {
        'name': 'T1: Research Digest (dentist)',
        'trigger_id': 'trg_t1',
        'payload': {
            'id': 'trg_t1', 'kind': 'research_digest', 'scope': 'merchant',
            'merchant_id': 'm_001_drmeera', 'customer_id': None,
            'payload': {'category': 'dentists', 'top_item_id': 'd1'},
            'urgency': 2, 'suppression_key': 'research:dentists:T1',
            'expires_at': '2026-05-03T00:00:00Z'
        }
    },
    {
        'name': 'T2: Perf Dip (low rating dentist)',
        'trigger_id': 'trg_t2',
        'payload': {
            'id': 'trg_t2', 'kind': 'perf_dip', 'scope': 'merchant',
            'merchant_id': 'm_001_drmeera', 'customer_id': None,
            'payload': {}, 'urgency': 3, 'suppression_key': 'perf_dip:m001:T2',
            'expires_at': '2026-05-10T00:00:00Z'
        }
    },
    {
        'name': 'T3: Festival Upcoming (salon, no offer)',
        'trigger_id': 'trg_t3',
        'payload': {
            'id': 'trg_t3', 'kind': 'festival_upcoming', 'scope': 'merchant',
            'merchant_id': 'm_002_salon', 'customer_id': None,
            'payload': {'festival_name': 'Diwali'},
            'urgency': 4, 'suppression_key': 'festival:diwali:m002:T3',
            'expires_at': '2026-10-30T00:00:00Z'
        }
    },
    {
        'name': 'T4: Customer Recall (dentist patient Priya)',
        'trigger_id': 'trg_t4',
        'payload': {
            'id': 'trg_t4', 'kind': 'recall_due', 'scope': 'customer',
            'merchant_id': 'm_001_drmeera', 'customer_id': 'c_001_priya',
            'payload': {}, 'urgency': 3, 'suppression_key': 'recall:priya:T4',
            'expires_at': '2026-08-01T00:00:00Z'
        }
    },
    {
        'name': 'T5: Perf Spike (salon)',
        'trigger_id': 'trg_t5',
        'payload': {
            'id': 'trg_t5', 'kind': 'perf_spike', 'scope': 'merchant',
            'merchant_id': 'm_002_salon', 'customer_id': None,
            'payload': {}, 'urgency': 2, 'suppression_key': 'perf_spike:m002:T5',
            'expires_at': '2026-07-10T00:00:00Z'
        }
    },
]

results = []
for tc in test_cases:
    push('trigger', tc['trigger_id'], tc['payload'])
    r = requests.post(f'{base}/v1/tick', json={
        'now': '2026-07-02T10:00:00Z',
        'available_triggers': [tc['trigger_id']]
    })
    actions = r.json().get('actions', [])
    if actions:
        a = actions[0]
        results.append({
            'test': tc['name'],
            'cta': a.get('cta'),
            'send_as': a.get('send_as'),
            'rationale': a.get('rationale'),
            'has_conv_id': bool(a.get('conversation_id')),
            'has_template': bool(a.get('template_name')),
            'body': a.get('body', '')
        })
    else:
        results.append({'test': tc['name'], 'body': 'NO ACTION GENERATED'})

print('=' * 70)
for r2 in results:
    print(f"\n{'='*70}")
    print(f"TEST: {r2['test']}")
    print(f"CTA: {r2.get('cta')} | send_as: {r2.get('send_as')} | has_conv_id: {r2.get('has_conv_id')} | has_template: {r2.get('has_template')}")
    print(f"RATIONALE: {r2.get('rationale')}")
    print(f"\nMESSAGE:\n{r2['body']}")
