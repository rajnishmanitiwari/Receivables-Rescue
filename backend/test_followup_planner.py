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
    def test_optout_with_open_dispute_goes_human_then_stays_stopped(self):
        # Dual intent (18 Nov review): no-contact is sticky AND a person must resolve the
        # dispute; after resolution the opt-out still bars chasing without re-consent.
        e = [Event(D - timedelta(days=3), "reply", Label.DONT_CONTACT), Event(D - timedelta(days=9), "reply", Label.DISPUTE)]
        self.assertEqual(next_action(inv(), e, D).kind, Kind.HUMAN)
        e2 = e + [Event(D - timedelta(days=1), "resolved")]
        self.assertEqual(next_action(inv(), e2, D).kind, Kind.STOP)
    def test_optout_alone_stops(self):
        e = [Event(D - timedelta(days=3), "reply", Label.DONT_CONTACT)]
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
            if Label.DONT_CONTACT in labs and Label.DISPUTE in labs: self.assertEqual(a.kind, Kind.HUMAN)
            elif Label.DONT_CONTACT in labs: self.assertEqual(a.kind, Kind.STOP)
            elif Label.DISPUTE in labs: self.assertEqual(a.kind, Kind.PAUSE)
            if a.kind == Kind.DRAFT:
                sent = sorted((e for e in evs if e.type == "sent"), key=lambda e: e.day)
                if sent: self.assertGreaterEqual((D - sent[-1].day).days, MIN_GAP_DAYS)
    def test_property_deterministic(self):
        e = [Event(D - timedelta(days=3), "sent", tier="reminder")]
        self.assertEqual(next_action(inv(40), e, D), next_action(inv(40), list(reversed(e)), D))

if __name__ == "__main__": unittest.main()


class PromiseDateSuggestion(unittest.TestCase):
    """Reviewer promise-date probes (18 Nov 2026) adapted to the suggestion contract:
    suggest_promise_date returns {date, phrase, reply_day, rule} for the user to
    confirm/edit, or None. Semantic intent unchanged: only unambiguous forms suggest;
    everything else is None (human). The weekday-name same-weekday case
    (Sun Traders will pay by wed) may yield no suggestion, and
    next-week/abbreviations/numeric dates are never suggested."""
    REF = date(2026, 11, 18)  # Wednesday
    D = staticmethod(lambda m, d: date(2026, m, d))

    def _sug(self, t, ref=None):
        if classify_reply(t) != Label.PROMISE:
            return None
        s = suggest_promise_date(t, ref or self.REF)
        return date.fromisoformat(s["date"]) if s else None

    def test_accepted_dates(self):
        self.assertEqual(self._sug("will pay by friday"), self.D(11, 20))
        self.assertEqual(self._sug("will pay tomorrow"), self.D(11, 19))
        self.assertEqual(self._sug("will pay by month end"), self.D(11, 30))

    def test_negated_payment_is_not_promise(self):
        for t in ["I can't pay by friday", "cannot pay by friday, sorry",
                  "we will not pay by friday"]:
            self.assertNotEqual(classify_reply(t), Label.PROMISE, t)
            self.assertIsNone(self._sug(t), t)

    def test_no_suggestion_cases(self):
        cases = ["will pay by friday if you send the corrected invoice",
                 "will pay after friday", "will pay by Friday, otherwise stop",
                 "will pay by friday, no wait, tuesday",
                 "he said he will pay tomorrow but I doubt it",
                 "accounts said they will pay by friday",
                 "will pay tomorrow, not today",
                 "I can't pay today, will pay on friday",
                 "will pay friday next week", "will pay by friday next week",
                 "will pay monday or tuesday", "Sun Traders will pay by wed",
                 "will pay next week", "will pay next friday",
                 "will pay in 2 weeks", "will pay by 25th", "will pay on 25 nov",
                 "will pay by march 5", "will pay by end of next month",
                 "will pay by end of this week", "will pay soon"]
        for t in cases:
            self.assertIsNone(self._sug(t), t)

    def test_same_weekday_ambiguous(self):
        self.assertIsNone(self._sug("will pay by friday", date(2026, 11, 20)))
        self.assertIsNone(self._sug("will pay on monday", date(2026, 11, 16)))

    def test_suggestion_carries_provenance(self):
        s = suggest_promise_date("not paid yet will pay by friday", self.REF)
        self.assertIsNotNone(s)
        self.assertEqual(s["date"], "2026-11-20")
        self.assertEqual(s["phrase"], "by friday")
        self.assertEqual(s["reply_day"], "2026-11-18")
        self.assertEqual(s["rule"], "weekday")

    def test_api_suggests_but_never_applies(self):
        from fastapi.testclient import TestClient
        from server import app
        c = TestClient(app)
        r = c.post("/api/next-action", json={
            "number": "P1", "amount": 100, "due": "2026-11-01",
            "events": [{"day": "2026-11-16", "type": "reply", "text": "not paid yet will pay by friday"}],
            "today": "2026-11-17"})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["kind"], "human", body)
        self.assertEqual(body["reason"], "promise without a date", body)
        self.assertEqual(body["suggested_promise_date"]["date"], "2026-11-20", body)
        self.assertEqual(body["suggested_promise_date"]["phrase"], "by friday", body)

    # Reviewer hedge/partial probes (suggestion_hedge_probes, candidate aaefb593):
    # every one of these must stay human-routed with no suggestion.
    HEDGE_VERBATIM = [
        "will pay before friday", "will pay not before friday", "will pay around friday",
        "hopefully will pay by friday", "will try to pay by friday", "can pay by friday",
        "should be able to pay by friday", "will pay half by friday",
        "will pay part by friday and rest later", "paid yesterday, will pay balance friday",
    ]
    OK_STILL_NONE_VERBATIM = [
        "will pay by friday or saturday", "will pay tomorrow or friday", "will pay by friday, not tomorrow",
        "will pay by Friday EOD", "will pay on friday maybe", "will pay yesterday",
    ]

    def test_reviewer_hedge_probes_all_none(self):
        for t in self.HEDGE_VERBATIM + self.OK_STILL_NONE_VERBATIM:
            lab = classify_reply(t)
            s = suggest_promise_date(t, self.REF) if lab == Label.PROMISE else None
            self.assertIsNone(s, t)

    def test_negated_paid_still_suggests(self):
        s = suggest_promise_date("not paid yet will pay by friday", self.REF)
        self.assertIsNotNone(s)

    def test_explicit_today_honoured_for_fresh_local_events(self):
        # 02:00 IST on 2026-11-18 is 2026-11-17 20:30 UTC: a request carrying the
        # client's local today must not let a UTC server clock drop today's events
        # (an opt-out in a fresh reply must STOP, not fall through to draft).
        from fastapi.testclient import TestClient
        from server import app
        c = TestClient(app)
        r = c.post("/api/next-action", json={
            "number": "T1", "amount": 100, "due": "2026-11-01", "today": "2026-11-18",
            "events": [{"day": "2026-11-18", "type": "reply", "text": "do not contact me"}]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["kind"], "stop", r.json())

    def test_suggestion_echoes_temporal_target_index(self):
        # List-last is not the target: a backdated second reply must not steal the
        # suggestion from the temporally latest reply, and the response names the
        # source event so the caller confirms onto the same one.
        from fastapi.testclient import TestClient
        from server import app
        c = TestClient(app)
        r = c.post("/api/next-action", json={
            "number": "T2", "amount": 100, "due": "2026-11-01", "today": "2026-11-18",
            "events": [
                {"day": "2026-11-18", "type": "reply", "text": "will pay by friday"},
                {"day": "2026-11-10", "type": "reply", "text": "still chasing accounts"}]})
        body = r.json()
        self.assertEqual(body["suggested_promise_date"]["reply_index"], 0, body)
        self.assertEqual(body["suggested_promise_date"]["reply_day"], "2026-11-18", body)

    def test_suggestion_ignores_future_dated_replies(self):
        from fastapi.testclient import TestClient
        from server import app
        c = TestClient(app)
        r = c.post("/api/next-action", json={
            "number": "T3", "amount": 100, "due": "2026-11-01", "today": "2026-11-18",
            "events": [
                {"day": "2026-11-18", "type": "reply", "text": "will pay by friday"},
                {"day": "2026-12-01", "type": "reply", "text": "will pay by monday"}]})
        body = r.json()
        self.assertEqual(body["suggested_promise_date"]["reply_index"], 0, body)
        self.assertEqual(body["suggested_promise_date"]["date"], "2026-11-20", body)

    def test_label_only_latest_promise_never_borrows_older_text(self):
        # The eligible target is the latest reply among ALL replies. A newer
        # label-only promise must not inherit a suggestion from older text.
        from fastapi.testclient import TestClient
        from server import app
        c = TestClient(app)
        r = c.post("/api/next-action", json={
            "number": "T4", "amount": 100, "due": "2026-11-01", "today": "2026-11-18",
            "events": [
                {"day": "2026-11-10", "type": "reply", "text": "will pay by friday"},
                {"day": "2026-11-18", "type": "reply", "label": "promise"}]})
        body = r.json()
        self.assertEqual(body["reason"], "promise without a date", body)
        self.assertNotIn("suggested_promise_date", body)

    def test_api_vague_promise_has_no_suggestion(self):
        from fastapi.testclient import TestClient
        from server import app
        c = TestClient(app)
        r = c.post("/api/next-action", json={
            "number": "P2", "amount": 100, "due": "2026-11-01",
            "events": [{"day": "2026-11-16", "type": "reply", "text": "will pay soon"}],
            "today": "2026-11-17"})
        body = r.json()
        self.assertEqual(body["kind"], "human", body)
        self.assertNotIn("suggested_promise_date", body)

    def test_explicit_date_wins_no_suggestion(self):
        from fastapi.testclient import TestClient
        from server import app
        c = TestClient(app)
        r = c.post("/api/next-action", json={
            "number": "P3", "amount": 100, "due": "2026-11-01",
            "events": [{"day": "2026-11-16", "type": "reply", "text": "will pay by friday",
                        "promise_date": "2026-11-21"}],
            "today": "2026-11-17"})
        body = r.json()
        self.assertEqual(body["kind"], "hold", body)
        self.assertEqual(body["until"], "2026-11-21", body)
        self.assertNotIn("suggested_promise_date", body)
