"""The plan API returns the message for the decided tier, so the card's draft
never goes stale relative to the current plan; restricted kinds return none."""
import unittest

from fastapi.testclient import TestClient

import server


class TestPlanMessage(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(server.app)

    def post(self, events=None, **kw):
        body = {"number": "INV-1", "amount": 1000, "due": "2026-10-11",
                "today": "2026-11-18", "events": events or []}
        body.update(kw)
        r = self.client.post("/api/next-action", json=body)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_draft_decision_returns_message_for_decided_tier(self):
        out = self.post(customer="Acme Traders", sender="Me", company="MyCo")
        self.assertEqual(out["kind"], "draft")
        self.assertEqual(out["tier"], "escalation")   # 38 days overdue
        m = out["message"]
        self.assertEqual(m["tier"], "escalation")
        self.assertEqual(m["tier_label"], "Escalation")
        self.assertIn("Acme", m["whatsapp"])
        self.assertIn("Me, MyCo", m["whatsapp"])

    def test_escalation_after_ignored_firm_send(self):
        out = self.post(events=[{"day": "2026-11-10", "type": "sent", "tier": "firm"}],
                        customer="Acme")
        self.assertEqual(out["kind"], "draft")
        self.assertEqual(out["message"]["tier"], "escalation")

    def test_restricted_kinds_return_no_message(self):
        stopped = self.post(events=[{"day": "2026-11-10", "type": "reply",
                                     "text": "please stop contacting me"}])
        self.assertEqual(stopped["kind"], "stop")
        self.assertNotIn("message", stopped)
        paused = self.post(events=[{"day": "2026-11-10", "type": "reply",
                                    "text": "this amount is wrong"}])
        self.assertEqual(paused["kind"], "pause")
        self.assertNotIn("message", paused)

    def test_context_fields_optional(self):
        out = self.post()   # no customer/sender/etc: placeholders, no crash
        self.assertEqual(out["kind"], "draft")
        self.assertIn("message", out)


if __name__ == "__main__":
    unittest.main()
