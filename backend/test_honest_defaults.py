"""Defaults must not show an unverified interest figure or fake a waitlist save."""
from fastapi.testclient import TestClient
import server

c = TestClient(server.app)

def test_interest_is_off_until_a_rate_is_supplied():
    d = "Acme, INV-1, 45000, 2026-01-01"
    r = c.post("/api/analyse", json={"data": d}).json()["report"]
    assert not r["statutory_interest_total"]
    assert r["assumptions"]["msmed"]["enabled"] is False
    r2 = c.post("/api/analyse", json={"data": d, "bank_rate": 5.0}).json()["report"]
    assert r2["statutory_interest_total"] > 0

def test_health_does_not_prefill_a_bank_rate():
    assert c.get("/api/health").json()["default_bank_rate"] is None

def test_waitlist_refuses_when_nothing_can_be_stored():
    if server._db is None:
        assert c.post("/api/waitlist", json={"email": "a@b.co"}).status_code == 503
