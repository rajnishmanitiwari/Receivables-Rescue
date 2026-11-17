"""Independent reviewer's 25 synthetic probes (18 Nov 2026), pinned verbatim, plus
planner-level guarantees for dual-intent replies. Any regression names itself here."""
import unittest
from datetime import date, timedelta
from followup_planner import (Label, Kind, Event, Invoice, classify_reply, reply_flags, next_action)

# (text, acceptable labels). "dont_contact" is acceptable ONLY for clear opt-outs.
PROBES = [
 ("Please do not stop sending reminders", {Label.UNKNOWN}),
 ("Don't stop sending reminders", {Label.UNKNOWN}),
 ("I will not opt out", {Label.UNKNOWN}),
 ("I won't opt out, keep sending", {Label.UNKNOWN}),
 ("do not email me the invoice, call instead", {Label.UNKNOWN}),
 ("Please stop sending the old invoice, send the corrected one", {Label.UNKNOWN}),
 ("Stop sending reminders to the old address, use this one", {Label.UNKNOWN}),
 ("stop sending reminders on weekends", {Label.UNKNOWN}),
 ("please stop sending me the same invoice", {Label.UNKNOWN}),
 ("do not contact my accountant, contact me", {Label.UNKNOWN}),
 ("don't email me, call me", {Label.UNKNOWN}),
 ("don't stop", {Label.UNKNOWN}),
 ("never email me again", {Label.UNKNOWN, Label.DONT_CONTACT}),
 ("stop sending to this address", {Label.UNKNOWN}),
 ("STOP.", {Label.DONT_CONTACT}),
 ("unsubscribe", {Label.DONT_CONTACT}),
 ("stop contacting me", {Label.DONT_CONTACT}),
 ("don't contact us again", {Label.DONT_CONTACT}),
 ("stop sending me emails", {Label.DONT_CONTACT}),
 ("stop emailing me, the invoice is wrong", {Label.DONT_CONTACT, Label.UNKNOWN}),
 ("this is disputed, do not contact me again", {Label.DONT_CONTACT, Label.UNKNOWN}),
 ("stop sending me emails about this, I never received the goods", {Label.DONT_CONTACT, Label.UNKNOWN}),
 ("invoice is wrong, I already paid", {Label.DISPUTE}),
 ("not paid yet will pay by friday", {Label.PROMISE}),
 ("I did not receive the goods, will pay once delivered", {Label.PROMISE, Label.DISPUTE, Label.UNKNOWN}),
]

D = date(2026, 11, 18)
INV = Invoice("X", 1000.0, D - timedelta(days=20))


class T(unittest.TestCase):
    def test_reviewer_probes(self):
        bad = [(t, classify_reply(t), sorted(o.name for o in ok))
               for t, ok in PROBES if classify_reply(t) not in ok]
        self.assertEqual(bad, [])

    def test_dual_intent_is_human_with_sticky_no_contact(self):
        # "stop emailing me, the invoice is wrong": person resolves the dispute,
        # no-contact never lifts without explicit re-consent, and nothing is ever drafted.
        ev = Event(D, "reply", classify_reply("stop emailing me, the invoice is wrong"),
                   flags=reply_flags("stop emailing me, the invoice is wrong"))
        self.assertEqual(ev.flags, frozenset({"optout", "dispute"}))
        a = next_action(INV, [ev], D)
        self.assertEqual(a.kind, Kind.HUMAN)
        a2 = next_action(INV, [ev, Event(D + timedelta(days=1), "resolved")], D + timedelta(days=1))
        self.assertEqual(a2.kind, Kind.STOP)   # opt-out survives resolution; no resume
        a3 = next_action(INV, [ev, Event(D + timedelta(days=1), "resolved"),
                               Event(D + timedelta(days=2), "sent", tier="firm")], D + timedelta(days=2))
        self.assertNotEqual(a3.kind, Kind.DRAFT)

    def test_plain_optout_stops_immediately(self):
        ev = Event(D, "reply", Label.DONT_CONTACT, flags=reply_flags("stop contacting me"))
        self.assertEqual(next_action(INV, [ev], D).kind, Kind.STOP)

    def test_qualified_optout_never_sticks(self):
        ev = Event(D, "reply", Label.UNKNOWN, flags=reply_flags("stop sending reminders on weekends"))
        self.assertEqual(ev.flags, frozenset())
        a = next_action(INV, [ev], D)
        self.assertNotEqual(a.kind, Kind.STOP)
        self.assertEqual(a.kind, Kind.HUMAN)

    def test_api_dual_intent_end_to_end(self):
        import os
        os.environ.pop("CORS_ORIGINS", None)
        from fastapi.testclient import TestClient
        import server
        c = TestClient(server.app)
        r = c.post("/api/next-action", json={
            "number": "INV-1", "amount": 1000, "due": "2026-10-01",
            "events": [{"day": "2026-11-18", "type": "reply",
                        "text": "stop emailing me, the invoice is wrong"}]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["kind"], "human")
        r2 = c.post("/api/next-action", json={
            "number": "INV-1", "amount": 1000, "due": "2026-10-01",
            "events": [{"day": "2026-11-18", "type": "reply", "text": "stop contacting me"}]})
        self.assertEqual(r2.json()["kind"], "stop")


if __name__ == "__main__":
    unittest.main()
