"""Final-notice copy reads correctly whether or not a due date is known.

/api/next-action hands the real due date to the template, so a sendable final
notice names it. When no date exists the sentence drops the clause entirely
instead of falling back to a placeholder that reads broken.
"""
from datetime import date
from fastapi.testclient import TestClient
import messages
import server

c = TestClient(server.app)

FINAL = {"number": "INV-9", "amount": 80000, "due": "2026-09-01",
         "today": "2026-11-18", "customer": "Acme", "sender": "R", "company": "Co"}


def _final_email(inv):
    return messages._email_body("final", inv, "R", "Co", "INR")


def test_next_action_final_notice_names_real_due_date():
    r = c.post("/api/next-action", json=FINAL)
    assert r.status_code == 200, r.text
    email = r.json()["message"]["email"]
    assert "against a due date of 2026-09-01" in email
    assert "the agreed date" not in email


def test_final_notice_without_date_drops_the_clause():
    email = _final_email({"invoice_no": "INV-1", "customer": "Acme",
                          "amount": 1000, "days_overdue": 70})
    assert "now 70 days overdue." in email
    assert "against a due date" not in email
    assert "the agreed date" not in email


def test_final_notice_with_date_keeps_the_clause():
    email = _final_email({"invoice_no": "INV-1", "customer": "Acme",
                          "amount": 1000, "days_overdue": 70,
                          "due_date": "2026-09-01"})
    assert "now 70 days overdue against a due date of 2026-09-01." in email


def test_next_action_firm_notice_names_real_due_date():
    r = c.post("/api/next-action", json={"number": "INV-1", "amount": 5000,
                                         "due": "2026-11-01", "today": "2026-11-18",
                                         "customer": "Acme", "sender": "R", "company": "Co"})
    assert "was due on 2026-11-01" in r.json()["message"]["email"]
