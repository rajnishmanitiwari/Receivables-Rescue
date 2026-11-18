"""Drafts must not assert owner actions the product never recorded:
no held work, no copied finance team, no professional referral, no work
suspension. Urgency, deadlines and payment-date requests stay."""
import unittest

import messages

INV = {"invoice_no": "INV-1", "customer": "Acme Traders", "amount": 1000,
       "days_overdue": 70, "due_date": "2026-09-09", "tier": None,
       "email": "", "phone": ""}

FORBIDDEN = ["holding new work", "pause all work", "pausing new work",
             "hand this to a professional", "copying your finance",
             "pause new work",
             # no statutory/legal assertions in sendable text while MSMED
             # eligibility is unverified
             "msmed", "samadhaan", "section 16", "statutory interest",
             "register the claim", "i am not pursuing",
             # no invented deadline: the final tier leaves the date to the owner
             "within 7 days"]


def all_drafts():
    out = {}
    for tier in ("reminder", "firm", "escalation", "final"):
        inv = dict(INV, tier=tier)
        built = messages.build_messages([inv], sender="Me", company="MyCo",
                                        currency="INR", limit=1)[0]
        out[tier] = built
    return out


class TestDraftTruthfulness(unittest.TestCase):
    def test_no_unrecorded_actions_any_tier_any_channel(self):
        for tier, m in all_drafts().items():
            for field in ("whatsapp", "email", "subject", "why"):
                text = m[field].lower()
                for phrase in FORBIDDEN:
                    self.assertNotIn(phrase, text, f"{tier}.{field} asserts '{phrase}'")

    def test_final_tier_keeps_urgency_and_owner_chosen_deadline(self):
        final = all_drafts()["final"]
        self.assertIn("final notice", final["whatsapp"].lower())
        self.assertIn("[date you choose]", final["whatsapp"])
        self.assertIn("payment", final["whatsapp"].lower())
        self.assertIn("[date you choose]", final["email"])
        self.assertIn("time-sensitive", final["email"])

    def test_escalation_asks_for_date_or_reason(self):
        esc = all_drafts()["escalation"]
        self.assertIn("date", esc["whatsapp"])
        self.assertIn("payment date", esc["email"])


if __name__ == "__main__":
    unittest.main()
