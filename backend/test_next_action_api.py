from datetime import date
from fastapi.testclient import TestClient
import server

c = TestClient(server.app)
BASE = {"number": "INV-9", "amount": 5000, "due": "2026-10-20", "today": "2026-11-14"}

def post(**kw):
    return c.post("/api/next-action", json={**BASE, **kw}).json()

def test_fresh_overdue_drafts_tier():
    r = post(); assert (r["kind"], r["tier"]) == ("draft", "firm")  # 25 days overdue

def test_dispute_text_pauses():
    r = post(events=[{"day": "2026-11-10", "type": "reply", "text": "This amount is wrong, we dispute it"}])
    assert r["kind"] == "pause"

def test_paid_claim_without_payment_needs_human():
    r = post(events=[{"day": "2026-11-12", "type": "reply", "text": "We already paid last week"}])
    assert r["kind"] == "human"

def test_bad_type_rejected():
    assert c.post("/api/next-action", json={**BASE, "events": [{"day": "2026-11-12", "type": "x"}]}).status_code == 422
