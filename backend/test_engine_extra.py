"""Extra backend tests added 13 Nov 2026 (private working copy, not yet pushed).

Cover behavior the original 13 tests leave unchecked: tier/bucket boundaries,
MSMED zero cases, Indian-format amount parsing, and the ranking rule that a
mid-age invoice near the collectability cliff can outrank an older one.
"""
from datetime import date, timedelta

import engine
from engine import (analyse, bucket_for, msmed_interest, parse_amount,
                    parse_invoices, tier_for)


def test_tier_boundaries():
    assert tier_for(15) == "reminder"
    assert tier_for(16) == "firm"
    assert tier_for(45) == "firm"
    assert tier_for(46) == "escalation"
    assert tier_for(90) == "escalation"
    assert tier_for(91) == "final"
    assert tier_for(-5) == "reminder"


def test_bucket_boundaries():
    assert bucket_for(-1) == "Not yet due"
    assert bucket_for(0) == "0-30 days"
    assert bucket_for(30) == "0-30 days"
    assert bucket_for(31) == "31-60 days"
    assert bucket_for(181) == "180+ days"


def test_msmed_interest_zero_cases():
    assert msmed_interest(100000, 0, 5.5) == 0.0      # not yet late
    assert msmed_interest(100000, -3, 5.5) == 0.0     # not due at all
    assert msmed_interest(0, 100, 5.5) == 0.0         # no amount
    assert msmed_interest(100000, 100, 0) == 0.0      # feature off


def test_parse_amount_indian_and_negative_formats():
    assert parse_amount("₹1,25,000") == 125000.0
    assert parse_amount("1,25,000.50") == 125000.50
    assert parse_amount("(5000)") == -5000.0          # accounting negative
    assert parse_amount("") is None
    assert parse_amount("abc") is None


def _csv(days_old: int, amount: float, name: str) -> str:
    due = (date.today() - timedelta(days=days_old)).isoformat()
    return f"customer,amount,due_date\n{name},{amount},{due}"


def test_near_cliff_invoice_outranks_older_smaller_slip():
    """A 100k invoice 85 days out (approaching the 90-day cliff) must outrank a
    50k invoice 200 days out: ranking is by cost of waiting, not age."""
    text = _csv(200, 50000, "OldCo") + "\n" + _csv(85, 100000, "CliffCo").split("\n", 1)[1]
    invoices, _ = parse_invoices(text)
    report = analyse(invoices, bank_rate=None)
    assert report["priority"][0]["customer"] == "CliffCo"
    assert report["priority"][0]["rank"] == 1


def test_cost_of_waiting_is_sum_of_slips():
    text = _csv(40, 80000, "A") + "\n" + _csv(70, 120000, "B").split("\n", 1)[1]
    invoices, _ = parse_invoices(text)
    report = analyse(invoices, bank_rate=None)
    slips = round(sum(i["slip_30d"] for i in report["priority"]), 2)
    assert report["cost_of_waiting_30d"] == slips
    assert report["cost_of_waiting_30d"] > 0
