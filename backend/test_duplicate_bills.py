"""Bill-number identity for duplicates and conflicts.

Exact duplicates (same customer, bill number, amount and due date) are one
bill entered twice: counted once, one chase draft. A real bill number with
conflicting amounts or dates is quarantined: not counted in totals, not
chased, loudly flagged, because we cannot tell one bill from two. Placeholder
"numbers" (N/A, dash, none) are not identities and never merge distinct bills.
"""
from datetime import date, timedelta

import engine
import messages as msg

DUE = (date.today() - timedelta(days=40)).isoformat()


def _analyse(data):
    invoices, warnings = engine.parse_invoices(data, today=date.today())
    report = engine.analyse(invoices, today=date.today())
    return report, warnings


def test_exact_duplicate_collapses_with_warning():
    data = (
        "customer,invoice,amount,due_date\n"
        f"Acme,INV-1,50000,{DUE}\n"
        f"Acme,INV-1,50000,{DUE}\n"
    )
    report, warnings = _analyse(data)
    assert report["invoice_count"] == 1
    assert report["total_outstanding"] == 50000.0
    assert any("duplicate" in w.lower() and "counted once" in w for w in warnings)


def test_duplicate_produces_one_chase_draft_not_two():
    data = (
        "customer,invoice,amount,due_date\n"
        f"Acme,INV-1,50000,{DUE}\n"
        f"Acme,INV-1,50000,{DUE}\n"
    )
    report, _ = _analyse(data)
    followups = msg.build_messages(report["priority"], limit=10)
    assert len(followups) == 1


def test_duplicate_detection_folds_case_and_outer_space_only():
    data = (
        "customer,invoice,amount,due_date\n"
        f"Acme Traders,INV-1,50000,{DUE}\n"
        f"acme traders,  INV-1 ,50000,{DUE}\n"
    )
    report, warnings = _analyse(data)
    assert report["invoice_count"] == 1
    assert any("duplicate" in w.lower() for w in warnings)


def test_internal_spaces_make_bill_numbers_distinct():
    for a, b in (("INV 1", "INV1"), ("1 2", "12")):
        data = (
            "customer,invoice,amount,due_date\n"
            f"Acme,{a},50000,{DUE}\n"
            f"Acme,{b},50000,{DUE}\n"
        )
        report, warnings = _analyse(data)
        assert report["invoice_count"] == 2, (a, b)
        assert report["total_outstanding"] == 100000.0, (a, b)
        assert not any("duplicate" in w.lower() or "conflicting" in w for w in warnings), (a, b)


def test_conflicting_amounts_quarantined_from_totals_and_chases():
    data = (
        "customer,invoice,amount,due_date\n"
        f"Acme,INV-1,50000,{DUE}\n"
        f"Acme,INV-1,75000,{DUE}\n"
        f"Bluepeak,INV-2,30000,{DUE}\n"
    )
    report, warnings = _analyse(data)
    # Neither conflicting version is counted; the clean row is untouched.
    assert report["invoice_count"] == 1
    assert report["total_outstanding"] == 30000.0
    assert not msg.build_messages(report["priority"], limit=10) or all(
        m["customer"] == "Bluepeak" for m in msg.build_messages(report["priority"], limit=10))
    w = next(w for w in warnings if "conflicting records" in w)
    assert "INV-1" in w and "50,000.00" in w and "75,000.00" in w


def test_all_rows_conflicting_fails_with_explanation_not_empty_report():
    import pytest
    other = (date.today() - timedelta(days=70)).isoformat()
    data = (
        "customer,invoice,amount,due_date\n"
        f"Acme,INV-1,50000,{DUE}\n"
        f"Acme,INV-1,50000,{other}\n"
    )
    # Nothing trustworthy remains: the error names the conflict instead of
    # showing an empty "you are owed 0" report.
    with pytest.raises(engine.ParseError, match="conflicting records"):
        engine.parse_invoices(data, today=date.today())


def test_placeholder_numbers_never_merge_distinct_bills():
    for placeholder in ("N/A", "-", "na", "none"):
        data = (
            "customer,invoice,amount,due_date\n"
            f"Acme,{placeholder},50000,{DUE}\n"
            f"Acme,{placeholder},75000,{DUE}\n"
        )
        report, warnings = _analyse(data)
        assert report["invoice_count"] == 2, placeholder
        assert report["total_outstanding"] == 125000.0, placeholder
        assert not any("duplicate" in w.lower() for w in warnings), placeholder


def test_placeholder_numbers_do_not_conflict_either():
    data = (
        "customer,invoice,amount,due_date\n"
        f"Acme,N/A,50000,{DUE}\n"
        f"Acme,N/A,50000,{(date.today() - timedelta(days=70)).isoformat()}\n"
    )
    report, warnings = _analyse(data)
    assert report["invoice_count"] == 2
    assert not any("conflicting" in w for w in warnings)


def test_rows_without_bill_number_are_never_collapsed():
    data = (
        "customer,invoice,amount,due_date\n"
        f"Acme,,50000,{DUE}\n"
        f"Acme,,50000,{DUE}\n"
    )
    report, warnings = _analyse(data)
    assert report["invoice_count"] == 2
    assert not any("duplicate" in w.lower() for w in warnings)


def test_triplicate_collapses_to_one():
    data = (
        "customer,invoice,amount,due_date\n"
        f"Acme,INV-1,50000,{DUE}\n"
        f"Acme,INV-1,50000,{DUE}\n"
        f"Acme,INV-1,50000,{DUE}\n"
    )
    report, _ = _analyse(data)
    assert report["invoice_count"] == 1
    assert report["expected_recoverable"] <= 50000.0


def test_same_number_different_customers_stays_independent():
    data = (
        "customer,invoice,amount,due_date\n"
        f"Acme,INV-1,50000,{DUE}\n"
        f"Bluepeak,INV-1,75000,{DUE}\n"
    )
    report, _ = _analyse(data)
    assert report["invoice_count"] == 2
    assert report["total_outstanding"] == 125000.0


def test_punctuation_makes_bill_numbers_distinct():
    # "1-2" and "12" are different bills; punctuation is part of the identity.
    data = (
        "customer,invoice,amount,due_date\n"
        f"Acme,1-2,50000,{DUE}\n"
        f"Acme,12,50000,{DUE}\n"
    )
    report, warnings = _analyse(data)
    assert report["invoice_count"] == 2
    assert report["total_outstanding"] == 100000.0
    assert not any("duplicate" in w.lower() or "conflicting" in w for w in warnings)


def test_separator_variants_are_not_merged():
    data = (
        "customer,invoice,amount,due_date\n"
        f"Acme,INV/2026/01,50000,{DUE}\n"
        f"Acme,INV-2026-01,50000,{DUE}\n"
    )
    report, warnings = _analyse(data)
    assert report["invoice_count"] == 2
    assert not any("duplicate" in w.lower() for w in warnings)


def test_quarantined_group_emits_no_counted_once_warning():
    data = (
        "customer,invoice,amount,due_date\n"
        f"Acme,INV-1,50000,{DUE}\n"
        f"Acme,INV-1,50000,{DUE}\n"
        f"Acme,INV-1,75000,{DUE}\n"
        f"Bluepeak,INV-2,30000,{DUE}\n"
    )
    report, warnings = _analyse(data)
    # The whole INV-1 group (including its exact duplicate) is quarantined;
    # only the clean row counts, and nothing claims INV-1 was "counted once".
    assert report["invoice_count"] == 1
    assert report["total_outstanding"] == 30000.0
    assert not any("counted once" in w for w in warnings)
    w = next(w for w in warnings if "conflicting records" in w)
    assert "50,000.00" in w and "75,000.00" in w


def test_date_only_conflict_warning_shows_both_dates():
    other = (date.today() - timedelta(days=70)).isoformat()
    data = (
        "customer,invoice,amount,due_date\n"
        f"Acme,INV-1,50000,{DUE}\n"
        f"Acme,INV-1,50000,{other}\n"
        f"Bluepeak,INV-2,30000,{DUE}\n"
    )
    report, warnings = _analyse(data)
    assert report["total_outstanding"] == 30000.0
    w = next(w for w in warnings if "conflicting records" in w)
    assert DUE in w and other in w
