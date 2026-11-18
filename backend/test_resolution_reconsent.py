"""Matrix for owner-recorded "resolved" and "reconsent" events.

Chronology rule: a restriction is cleared only when BOTH its day is on or
before the clearing event's day AND it appears earlier in the events list;
same-day ties are settled by list order. If the signals disagree the
restriction stands with its usual kind and the reason says why.
Re-consent is an owner attestation, never inferred from reply text; it clears
opt-outs only - never disputes - and resumption is never silent.
"""
import unittest
from datetime import date, timedelta

from fastapi.testclient import TestClient

import server
from followup_planner import (
    Kind, Label, Event, Invoice, next_action, classify_reply, reply_flags,
)

D = date(2026, 11, 18)
INV = Invoice("T", 5000.0, D - timedelta(days=29))   # 29 days overdue -> firm when drafting


def optout(day):
    return Event(day, "reply", Label.DONT_CONTACT, flags=frozenset({"optout"}))


def dispute(day):
    return Event(day, "reply", Label.DISPUTE, flags=frozenset({"dispute"}))


class ReconsentChronology(unittest.TestCase):
    def test_reconsent_dated_before_optout_listed_after_stays_stopped(self):
        # reviewer case (a): reconsent day1, opt-out day2, order [optout, reconsent]
        e = [optout(D - timedelta(days=1)), Event(D - timedelta(days=2), "reconsent")]
        a = next_action(INV, e, D)
        self.assertEqual(a.kind, Kind.STOP)
        self.assertIn("could not be ordered", a.reason)

    def test_optout_dated_after_reconsent_listed_before_stays_stopped(self):
        # reviewer case (b): same configuration named from the other end
        e = [optout(D - timedelta(days=1)), Event(D - timedelta(days=2), "reconsent")]
        self.assertEqual(next_action(INV, e, D).kind, Kind.STOP)

    def test_backdated_optout_listed_after_reconsent_stays_stopped(self):
        # reviewer case (c): opt-out day1 listed after reconsent day2 (backdated paste)
        e = [Event(D - timedelta(days=1), "reconsent"), optout(D - timedelta(days=2))]
        a = next_action(INV, e, D)
        self.assertEqual(a.kind, Kind.STOP)
        self.assertIn("could not be ordered", a.reason)

    def test_same_day_optout_then_reconsent_clears(self):
        # reviewer case (d) first half: same date, list order decides
        e = [optout(D), Event(D, "reconsent")]
        a = next_action(INV, e, D)
        self.assertEqual(a.kind, Kind.DRAFT)
        self.assertEqual(a.tier, "firm")

    def test_same_day_reconsent_then_optout_stays_stopped(self):
        # reviewer case (d) second half
        e = [Event(D, "reconsent"), optout(D)]
        self.assertEqual(next_action(INV, e, D).kind, Kind.STOP)

    def test_optout_reconsent_later_optout_stays_stopped(self):
        # reviewer case (e)
        e = [optout(D - timedelta(days=3)), Event(D - timedelta(days=2), "reconsent"),
             optout(D - timedelta(days=1))]
        self.assertEqual(next_action(INV, e, D).kind, Kind.STOP)

    def test_clear_order_optout_then_reconsent_resumes(self):
        e = [optout(D - timedelta(days=2)), Event(D - timedelta(days=1), "reconsent")]
        a = next_action(INV, e, D)
        self.assertEqual(a.kind, Kind.DRAFT)

    def test_resumption_is_never_silent(self):
        # history shows both dates in the resumed output
        e = [optout(D - timedelta(days=2)), Event(D - timedelta(days=1), "reconsent")]
        a = next_action(INV, e, D)
        self.assertIn("opted out " + (D - timedelta(days=2)).isoformat(), a.reason)
        self.assertIn("re-consent recorded " + (D - timedelta(days=1)).isoformat(), a.reason)

    def test_reconsent_without_earlier_optout_is_visible_noop(self):
        e = [Event(D - timedelta(days=1), "reconsent")]
        a = next_action(INV, e, D)
        self.assertEqual(a.kind, Kind.DRAFT)   # not an error, not a state change
        self.assertIn("had no earlier opt-out to clear", a.reason)

    def test_reconsent_never_closes_dispute(self):
        e = [dispute(D - timedelta(days=2)), Event(D - timedelta(days=1), "reconsent")]
        self.assertEqual(next_action(INV, e, D).kind, Kind.PAUSE)


class ResolvedChronology(unittest.TestCase):
    def test_dispute_dated_after_resolved_listed_before_stays_paused(self):
        # reviewer case (f) mirror of (b)
        e = [dispute(D - timedelta(days=1)), Event(D - timedelta(days=2), "resolved")]
        a = next_action(INV, e, D)
        self.assertEqual(a.kind, Kind.PAUSE)
        self.assertIn("could not be ordered", a.reason)

    def test_backdated_dispute_listed_after_resolved_stays_paused(self):
        # reviewer case (f) mirror of (c)
        e = [Event(D - timedelta(days=1), "resolved"), dispute(D - timedelta(days=2))]
        a = next_action(INV, e, D)
        self.assertEqual(a.kind, Kind.PAUSE)
        self.assertIn("could not be ordered", a.reason)

    def test_same_day_dispute_then_resolved_clears(self):
        e = [dispute(D), Event(D, "resolved")]
        self.assertEqual(next_action(INV, e, D).kind, Kind.DRAFT)

    def test_same_day_resolved_then_dispute_stays_paused(self):
        e = [Event(D, "resolved"), dispute(D)]
        self.assertEqual(next_action(INV, e, D).kind, Kind.PAUSE)

    def test_clear_order_dispute_then_resolved_resumes(self):
        # plain-dispute branch now honors resolved (was inconsistent with dual-intent)
        e = [dispute(D - timedelta(days=2)), Event(D - timedelta(days=1), "resolved")]
        self.assertEqual(next_action(INV, e, D).kind, Kind.DRAFT)

    def test_resolved_never_lifts_optout(self):
        e = [optout(D - timedelta(days=2)), Event(D - timedelta(days=1), "resolved")]
        self.assertEqual(next_action(INV, e, D).kind, Kind.STOP)

    def test_dual_intent_stays_stopped_after_resolution(self):
        e = [Event(D - timedelta(days=3), "reply", Label.DONT_CONTACT,
                   flags=frozenset({"optout", "dispute"})),
             Event(D - timedelta(days=2), "resolved")]
        self.assertEqual(next_action(INV, e, D).kind, Kind.STOP)

    def test_resolved_with_nothing_to_resolve_is_noop(self):
        e = [Event(D - timedelta(days=1), "resolved")]
        a = next_action(INV, e, D)
        self.assertEqual(a.kind, Kind.DRAFT)   # no error, no state change
        self.assertNotIn("could not be ordered", a.reason)

    def test_resolving_unknown_returns_to_normal_cadence_only(self):
        # tier ladder still applies after review: sent reminder 6 days ago, 29 days
        # overdue -> firm (one rung up), not a skipped tier
        e = [Event(D - timedelta(days=6), "sent", tier="reminder"),
             Event(D - timedelta(days=2), "reply", Label.UNKNOWN),
             Event(D - timedelta(days=1), "resolved")]
        a = next_action(INV, e, D)
        self.assertEqual((a.kind, a.tier), (Kind.DRAFT, "firm"))

    def test_resolving_unknown_does_not_skip_minimum_gap(self):
        e = [Event(D - timedelta(days=2), "sent", tier="firm"),
             Event(D - timedelta(days=1), "reply", Label.UNKNOWN),
             Event(D, "resolved")]
        a = next_action(INV, e, D)
        self.assertEqual(a.kind, Kind.HOLD)
        self.assertIn("minimum gap", a.reason)


class ReverseUnsubscribeRoutesToHuman(unittest.TestCase):
    def test_reverse_unsubscribe_phrases_are_not_optouts(self):
        for t in ["i didnt unsubscribe", "i never unsubscribed",
                  "please dont unsubscribe me", "we did not unsubscribe"]:
            self.assertEqual(classify_reply(t), Label.UNKNOWN, t)
            self.assertNotIn("optout", reply_flags(t), t)

    def test_reverse_unsubscribe_routes_to_human_on_fresh_thread(self):
        ev = Event(D, "reply", classify_reply("i didnt unsubscribe"),
                   flags=reply_flags("i didnt unsubscribe"))
        a = next_action(INV, [ev], D)
        self.assertEqual(a.kind, Kind.HUMAN)

    def test_reverse_unsubscribe_never_resumes_after_real_optout(self):
        # sticky opt-out preempts: reply text can never lift it, only an
        # owner-recorded reconsent event can
        e = [optout(D - timedelta(days=2)),
             Event(D - timedelta(days=1), "reply", classify_reply("i didnt unsubscribe"),
                   flags=reply_flags("i didnt unsubscribe"))]
        self.assertEqual(next_action(INV, e, D).kind, Kind.STOP)

    def test_existing_optouts_still_stick(self):
        for t in ["stop contacting me", "do not email me", "unsubscribe",
                  "please remove me from your list"]:
            ev = Event(D, "reply", classify_reply(t), flags=reply_flags(t))
            self.assertEqual(next_action(INV, [ev], D).kind, Kind.STOP, t)


class ApiValidation(unittest.TestCase):
    BASE = {"number": "T-1", "amount": 5000, "due": "2026-10-20", "today": "2026-11-18"}

    def setUp(self):
        self.c = TestClient(server.app)

    def post(self, **kw):
        return self.c.post("/api/next-action", json={**self.BASE, **kw})

    def test_future_resolved_rejected(self):
        r = self.post(events=[{"day": "2026-11-19", "type": "resolved"}])
        self.assertEqual(r.status_code, 422)

    def test_future_reconsent_rejected(self):
        r = self.post(events=[{"day": "2026-11-19", "type": "reconsent"}])
        self.assertEqual(r.status_code, 422)

    def test_same_day_resolved_and_reconsent_accepted(self):
        r = self.post(events=[{"day": "2026-11-18", "type": "resolved"},
                              {"day": "2026-11-18", "type": "reconsent"}])
        self.assertEqual(r.status_code, 200)

    def test_reconsent_note_accepted_and_never_parsed(self):
        r = self.post(events=[{"day": "2026-11-17", "type": "reconsent",
                               "text": "stop contacting me"}])  # note, not a reply
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["kind"], "draft")   # note was not classified as opt-out

    def test_api_resume_shows_history(self):
        r = self.post(events=[
            {"day": "2026-11-10", "type": "reply", "text": "stop contacting me"},
            {"day": "2026-11-15", "type": "reconsent", "text": "called, asked to resume"}])
        j = r.json()
        self.assertEqual(j["kind"], "draft")
        self.assertIn("opted out 2026-11-10", j["reason"])
        self.assertIn("re-consent recorded 2026-11-15", j["reason"])

    def test_api_plain_dispute_resumes_after_review(self):
        r = self.post(events=[
            {"day": "2026-11-10", "type": "reply", "text": "this amount is wrong"},
            {"day": "2026-11-15", "type": "resolved"}])
        self.assertEqual(r.json()["kind"], "draft")


if __name__ == "__main__":
    unittest.main()
