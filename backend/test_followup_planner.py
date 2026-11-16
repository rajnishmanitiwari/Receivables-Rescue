import unittest, random
from datetime import date, timedelta
from followup_planner import *

D = date(2026, 11, 14)
def inv(over=20, amount=1000.0, status="open"): return Invoice("INV-1", amount, D - timedelta(days=over), status)

class T(unittest.TestCase):
    def test_not_overdue(self): self.assertEqual(next_action(inv(0), [], D).kind, Kind.NONE)
    def test_first_draft_tier(self): a = next_action(inv(20), [], D); self.assertEqual((a.kind, a.tier), (Kind.DRAFT, "firm"))
    def test_paid_stops(self): self.assertEqual(next_action(inv(status="paid"), [], D).kind, Kind.STOP)
    def test_payments_close(self):
        e = [Event(D - timedelta(days=1), "payment", amount=1000.0)]
        self.assertEqual(next_action(inv(), e, D).kind, Kind.STOP)
    def test_underpayment_not_closed(self):
        e = [Event(D - timedelta(days=1), "payment", amount=400.0)]
        self.assertEqual(next_action(inv(), e, D).kind, Kind.DRAFT)
    def test_dispute_pauses_even_after_later_paid_claim(self):
        e = [Event(D - timedelta(days=9), "reply", Label.DISPUTE), Event(D - timedelta(days=2), "reply", Label.PAID)]
        self.assertEqual(next_action(inv(), e, D).kind, Kind.PAUSE)
    def test_optout_stops_and_beats_dispute(self):
        e = [Event(D - timedelta(days=3), "reply", Label.DONT_CONTACT), Event(D - timedelta(days=9), "reply", Label.DISPUTE)]
        self.assertEqual(next_action(inv(), e, D).kind, Kind.STOP)
    def test_claimed_paid_without_payment_goes_to_human(self):
        self.assertEqual(next_action(inv(), [Event(D - timedelta(days=2), "reply", Label.PAID)], D).kind, Kind.HUMAN)
    def test_promise_held_until_date_then_chased(self):
        e = [Event(D - timedelta(days=2), "reply", Label.PROMISE, promise_date=D + timedelta(days=3))]
        a = next_action(inv(), e, D); self.assertEqual((a.kind, a.until), (Kind.HOLD, D + timedelta(days=3)))
        self.assertEqual(next_action(inv(), e, D + timedelta(days=4)).kind, Kind.DRAFT)
    def test_promise_without_date_needs_human(self):
        self.assertEqual(next_action(inv(), [Event(D, "reply", Label.PROMISE)], D).kind, Kind.HUMAN)
    def test_min_gap(self):
        e = [Event(D - timedelta(days=2), "sent", tier="firm")]
        self.assertEqual(next_action(inv(20), e, D).kind, Kind.HOLD)
    def test_never_repeats_tier_and_steps_one_rung(self):
        e = [Event(D - timedelta(days=6), "sent", tier="reminder")]
        a = next_action(inv(70), e, D); self.assertEqual((a.kind, a.tier), (Kind.DRAFT, "firm"))  # skips no rungs
    def test_same_tier_waits_for_next(self):
        e = [Event(D - timedelta(days=7), "sent", tier="firm")]
        a = next_action(inv(20), e, D); self.assertEqual(a.kind, Kind.HOLD)
    def test_future_events_ignored(self):
        e = [Event(D + timedelta(days=1), "reply", Label.DISPUTE)]
        self.assertEqual(next_action(inv(), e, D).kind, Kind.DRAFT)
    def test_unknown_reply_goes_to_human(self):
        self.assertEqual(next_action(inv(), [Event(D, "reply", Label.UNKNOWN)], D).kind, Kind.HUMAN)
    def test_classifier_precedence(self):
        self.assertEqual(classify_reply("I already paid but the amount is wrong, I dispute this"), Label.DISPUTE)
        self.assertEqual(classify_reply("Please stop emailing me, I already paid"), Label.DONT_CONTACT)
        self.assertEqual(classify_reply("We will pay by Friday"), Label.PROMISE)
        self.assertEqual(classify_reply("ok thanks"), Label.UNKNOWN)
    def test_property_never_draft_after_dispute_or_optout(self):
        rnd = random.Random(7)
        for _ in range(2000):
            evs = []
            for _ in range(rnd.randint(1, 6)):
                day = D - timedelta(days=rnd.randint(0, 40))
                if rnd.random() < .5:
                    evs.append(Event(day, "reply", rnd.choice(list(Label)), promise_date=day + timedelta(days=rnd.randint(-3, 9))))
                else:
                    evs.append(Event(day, "sent", tier=rnd.choice(["reminder", "firm", "escalation", "final"])))
            a = next_action(inv(rnd.randint(1, 90)), evs, D)
            labs = {e.label for e in evs if e.type == "reply"}
            if Label.DONT_CONTACT in labs: self.assertEqual(a.kind, Kind.STOP)
            elif Label.DISPUTE in labs: self.assertEqual(a.kind, Kind.PAUSE)
            if a.kind == Kind.DRAFT:
                sent = sorted((e for e in evs if e.type == "sent"), key=lambda e: e.day)
                if sent: self.assertGreaterEqual((D - sent[-1].day).days, MIN_GAP_DAYS)
    def test_property_deterministic(self):
        e = [Event(D - timedelta(days=3), "sent", tier="reminder")]
        self.assertEqual(next_action(inv(40), e, D), next_action(inv(40), list(reversed(e)), D))

if __name__ == "__main__": unittest.main()
