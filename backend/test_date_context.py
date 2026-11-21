from datetime import date
import pytest
from fastapi.testclient import TestClient
import server

client = TestClient(server.app)
DATA = 'customer,invoice_no,amount,due_date\nAcme,INV-35,5000,2026-10-15'

@pytest.fixture(autouse=True)
def isolated_bucket():
    server._hits.clear()
    yield
    server._hits.clear()

def test_analysis_uses_explicit_client_day_and_preserves_exact_due():
    out = client.post('/api/analyse', json=dict(data=DATA, today='2026-11-21')).json()
    assert out['report']['generated_on'] == '2026-11-21'
    assert out['report']['priority'][0]['days_overdue'] == 37
    assert out['messages'][0]['due_date'] == '2026-10-15'
    assert out['messages'][0]['days_overdue'] == 37
    # A new planner day changes lateness, never the original bill's due date.
    m = out['messages'][0]
    plan = client.post('/api/next-action', json=dict(number=m['invoice_no'], amount=m['amount'], due=m['due_date'], today='2026-11-22')).json()
    assert plan['kind'] == 'draft'
    assert '38 days' in plan['message']['whatsapp']

def test_default_day_captured_once_for_parse_and_analysis(monkeypatch):
    class Clock(date):
        reads = 0
        @classmethod
        def today(cls):
            cls.reads += 1
            return date(2026, 11, 20) if cls.reads == 1 else date(2026, 11, 21)
    monkeypatch.setattr(server, 'date', Clock)
    out = client.post('/api/analyse', json=dict(data=DATA)).json()
    assert Clock.reads == 1
    assert out['report']['generated_on'] == '2026-11-20'
    assert out['report']['priority'][0]['days_overdue'] == 36

def test_explicit_day_does_not_consult_server_clock(monkeypatch):
    class Clock(date):
        @classmethod
        def today(cls):
            raise AssertionError('server day used despite explicit client day')
    monkeypatch.setattr(server, 'date', Clock)
    r = client.post('/api/analyse', json=dict(data=DATA, today='2026-11-21'))
    assert r.status_code == 200, r.text
    assert r.json()['report']['generated_on'] == '2026-11-21'

def test_invalid_explicit_day_is_validation_error():
    r = client.post('/api/analyse', json=dict(data=DATA, today='2026-02-30'))
    assert r.status_code == 422
