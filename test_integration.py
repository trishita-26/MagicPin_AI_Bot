import requests
import json

base = 'http://localhost:8081'

# Push merchant
requests.post(f'{base}/v1/context', json={
    'scope': 'merchant', 'context_id': 'm_001_drmeera', 'version': 1,
    'payload': {
        'merchant_id': 'm_001_drmeera', 'category_slug': 'dentists',
        'identity': {
            'name': 'Dr. Meera Dental Clinic', 'owner_first_name': 'Meera',
            'city': 'Delhi', 'locality': 'Lajpat Nagar',
            'languages': ['en', 'hi'], 'verified': True
        },
        'subscription': {'status': 'active', 'plan': 'Pro', 'days_remaining': 82},
        'performance': {'views': 2410, 'calls': 18, 'ctr': 0.021, 'delta_7d': {'views_pct': 0.05, 'calls_pct': -0.12}},
        'offers': [{'id': 'o1', 'title': 'Dental Cleaning @ Rs.299', 'status': 'active'}],
        'signals': ['stale_posts:22d', 'ctr_below_peer_median'],
        'customer_aggregate': {'total_unique_ytd': 540, 'lapsed_180d_plus': 78, 'retention_6mo_pct': 0.38},
        'conversation_history': []
    }, 'delivered_at': '2026-07-02T00:00:00Z'
})

# Push trigger
requests.post(f'{base}/v1/context', json={
    'scope': 'trigger', 'context_id': 'trg_research_001', 'version': 1,
    'payload': {
        'id': 'trg_research_001', 'kind': 'research_digest', 'scope': 'merchant',
        'merchant_id': 'm_001_drmeera', 'customer_id': None,
        'payload': {'category': 'dentists', 'top_item_id': 'd1'},
        'urgency': 2, 'suppression_key': 'research:dentists:2026-W17',
        'expires_at': '2026-05-03T00:00:00Z'
    }, 'delivered_at': '2026-07-02T00:00:00Z'
})

# Tick to generate a message
r = requests.post(f'{base}/v1/tick', json={
    'now': '2026-07-02T10:00:00Z',
    'available_triggers': ['trg_research_001']
})
result = r.json()
print('=== TICK RESPONSE ===')
actions = result.get('actions', [])
for action in actions:
    cid = action.get('conversation_id')
    print('conversation_id:', cid)
    print('template_name:', action.get('template_name'))
    print('template_params:', action.get('template_params'))
    print('cta:', action.get('cta'))
    print('rationale:', action.get('rationale'))
    print()
    print('--- BODY ---')
    print(action.get('body'))
    print()

# Test reply
if actions:
    conv_id = actions[0].get('conversation_id')
    mid = actions[0].get('merchant_id')
    r2 = requests.post(f'{base}/v1/reply', json={
        'conversation_id': conv_id,
        'merchant_id': mid,
        'from_role': 'merchant',
        'message': 'Yes please send me the abstract',
        'received_at': '2026-07-02T10:05:00Z',
        'turn_number': 2
    })
    print('=== REPLY RESPONSE ===')
    print(json.dumps(r2.json(), indent=2, ensure_ascii=False))
