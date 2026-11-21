from fastapi.testclient import TestClient
import server
import pytest

@pytest.fixture(autouse=True)
def isolated_rate_bucket():
    server._hits.clear()
    yield
    server._hits.clear()

client = TestClient(server.app)
BASE = dict(number='INV-34', amount=5000, due='2026-10-15', today='2026-11-21', customer='Acme')

def post(events):
    r = client.post('/api/next-action', json={**BASE, 'events': events})
    assert r.status_code == 200, r.text
    return r.json()

def payment(amount, day='2026-11-21'):
    return dict(type='payment', amount=amount, day=day)

def test_partial_payment_cannot_return_original_amount_chase():
    out = post([payment(1000)])
    assert out['kind'] == 'human'
    assert 'balance review' in out['reason']
    assert 'message' not in out

def test_partial_payment_during_send_gap_also_has_no_message():
    out = post([payment(1000), dict(type='sent', day='2026-11-21', tier='escalation')])
    assert out['kind'] == 'human'
    assert 'message' not in out

def test_full_and_overpayment_keep_paid_stop():
    for events in ([payment(1000), payment(4000)], [payment(7000)]):
        out = post(events)
        assert out['kind'] == 'stop'
        assert 'message' not in out

def test_dispute_and_optout_not_weakened_by_payment():
    for text, expected in [('this amount is wrong', 'pause'), ('stop contacting me', 'stop')]:
        out = post([payment(1000), dict(type='reply', text=text, day='2026-11-21')])
        assert out['kind'] == expected
        assert 'message' not in out

def test_zero_or_future_payment_does_not_change_current_unpaid_draft():
    for events in ([], [payment(0)], [payment(1000, '2026-11-22')]):
        out = post(events)
        assert out['kind'] == 'draft'
        assert 'message' in out
