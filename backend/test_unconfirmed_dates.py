"""Unknown or unconfirmed due dates stay unknown end to end.

A row only becomes chaseable when its due date came from a named due-date
column (the caller's own header, which the review screen confirms). Dates read
positionally from headerless input are assumptions, and missing dates are
unknown: neither produces lateness, priority, probability, an aging bucket
placement, or a sendable draft.
"""
from datetime import date
import engine
import messages

TODAY = date(2026, 11, 18)


def _analyse(data):
    invoices, warnings = engine.parse_invoices(data, today=TODAY)
    return engine.analyse(invoices, today=TODAY), warnings


def _only(report):
    assert len(report["priority"]) == 1
    return report["priority"][0]


def _assert_neutral(row):
    assert row["days_overdue"] is None
    assert row["tier"] == ""
    assert row["probability"] is None
    assert row["expected_value"] is None
    assert row["slip_30d"] is None
    assert row["bucket"] == "No confirmed due date"


def test_headerless_three_columns_unconfirmed():
    report, warnings = _analyse("Acme,10000,2026-01-10")
    row = _only(report)
    assert row["due_date"] == "2026-01-10"  # what was read stays visible...
    assert row["date_source"] == "positional"
    _assert_neutral(row)  # ...but nothing is derived from an assumption
    assert any("header" in w.lower() and "confirm" in w.lower() for w in warnings)
    assert messages.build_messages(report["priority"], limit=5) == []


def test_headerless_four_columns_unconfirmed():
    report, warnings = _analyse("Acme,I1,100000,2026-01-10")
    row = _only(report)
    assert row["due_date"] == "2026-01-10"
    assert row["date_source"] == "positional"
    _assert_neutral(row)
    assert any("header" in w.lower() and "confirm" in w.lower() for w in warnings)
    built = messages.build_messages(report["priority"], limit=5)
    assert built == []


def test_headerless_six_columns_unconfirmed_but_contacts_kept():
    report, _ = _analyse("Acme,I1,100000,2026-01-10,ap@acme.com,9876500000")
    row = _only(report)
    assert row["date_source"] == "positional"
    assert row["email"] == "ap@acme.com" and row["phone"] == "9876500000"
    _assert_neutral(row)
    assert messages.build_messages(report["priority"], limit=5) == []


def test_headerless_blank_date_is_unknown():
    report, warnings = _analyse("Acme,I1,100000,")
    row = _only(report)
    assert row["due_date"] is None
    _assert_neutral(row)
    assert any("no readable due date" in w for w in warnings)


def test_headed_blank_due_date_is_unknown():
    report, warnings = _analyse("customer, invoice no, amount, due date\nAcme,I1,100000,")
    row = _only(report)
    assert row["due_date"] is None
    _assert_neutral(row)
    assert any("no readable due date" in w for w in warnings)
    assert any("not scheduled" in w for w in warnings)
    assert not any("probably higher" in w for w in warnings)


def test_headed_due_date_is_confirmed_and_scheduled():
    report, _ = _analyse("customer, invoice no, amount, due date\nAcme,I1,100000,2026-01-10")
    row = _only(report)
    assert row["date_source"] == "column"
    assert row["days_overdue"] == 312
    assert row["tier"] in messages.TIER_LABELS
    built = messages.build_messages(report["priority"], limit=5)
    assert len(built) == 1


def test_mixed_confirmed_and_unknown_rows():
    data = (
        "customer, invoice no, amount, due date\n"
        "Dated Co, D1, 50000, 2026-10-01\n"
        "Mystery Co, M1, 80000,"
    )
    report, warnings = _analyse(data)
    dated = next(r for r in report["priority"] if r["customer"] == "Dated Co")
    undated = next(r for r in report["priority"] if r["customer"] == "Mystery Co")
    assert dated["days_overdue"] == 48 and dated["tier"]
    _assert_neutral(undated)
    # Scheduled rows always outrank unscheduled ones.
    assert dated["rank"] < undated["rank"]
    # Unscheduled money stays out of the recovery estimates.
    assert report["expected_recoverable"] == dated["expected_value"]
    assert report["cost_of_waiting_30d"] == dated["slip_30d"]
    assert report["weighted_avg_days_overdue"] == 48.0
    # The neutral bucket carries the amount with no probability claim.
    neutral = next(b for b in report["buckets"] if b["bucket"] == "No confirmed due date")
    assert neutral["amount"] == 80000 and neutral["probability"] is None
    assert all(b["bucket"] == "No confirmed due date" or b["probability"] is not None
               for b in report["buckets"])
    # Risks disclose the unknown instead of claiming nothing is overdue.
    assert any("no confirmed due date" in r for r in report["risks"])
    assert not any("Nothing is overdue" in r for r in report["risks"])
    # One draft, for the dated row only.
    built = messages.build_messages(report["priority"], limit=10)
    assert [m["customer"] for m in built] == ["Dated Co"]
    assert "Mystery Co" not in built[0]["email"]


def test_unscheduled_rows_do_not_eat_the_message_limit():
    lines = ["customer, invoice no, amount, due date",
             "Dated A, A1, 1000, 2026-10-01",
             "Dated B, B1, 1000, 2026-10-02"]
    lines += [f"Mystery {n}, M{n}, 1000," for n in range(12)]
    report, _ = _analyse("\n".join(lines))
    built = messages.build_messages(report["priority"], limit=10)
    assert {m["customer"] for m in built} == {"Dated A", "Dated B"}


def test_build_messages_never_fabricates_a_due_date():
    # A tiered row without a due date gets no draft: templates name real dates only.
    row = {"invoice_no": "I1", "customer": "Acme", "amount": 1000,
           "days_overdue": 0, "tier": "reminder", "email": "", "phone": ""}
    assert messages.build_messages([row], limit=1) == []


def test_nothing_overdue_claim_only_when_all_dates_known():
    report, _ = _analyse("customer, invoice no, amount, due date\nAcme,I1,1000,2026-12-01")
    assert any("Nothing is overdue" in r for r in report["risks"])
    report2, _ = _analyse("customer, invoice no, amount\nAcme,I1,1000")
    assert not any("Nothing is overdue" in r for r in report2["risks"])
    assert any("no confirmed due date" in r for r in report2["risks"])


def test_concentration_risk_states_concentration_only():
    data = "customer, invoice no, amount\nMystery Co, M1, 80000"
    report, _ = _analyse(data)
    line = next(r for r in report["risks"] if "61.5%" in r or "% of everything" in r)
    assert "late payer" not in line
    assert "pays late" not in line
    assert "riding on one customer" in line


def test_extract_pdf_text_computed_due_is_flagged_assumed():
    import extract
    # No due date stated: due computed from invoice date + default terms is an
    # assumption the review screen must surface, not a confirmed due date.
    row = extract.parse_invoice_text("Invoice INV-9\nDate: 01/10/2026\nTotal: Rs 45,000\nBilled to Acme")
    if row["due_date"] is not None:
        assert row["date_assumed"] is True


def test_extract_pdf_text_explicit_due_is_not_assumed():
    import extract
    row = extract.parse_invoice_text(
        "Invoice INV-9\nDate: 01/10/2026\nDue Date: 15/11/2026\nTotal: Rs 45,000\nBilled to Acme")
    assert row["due_date"] == "2026-11-15"
    assert row["date_assumed"] is False


def test_extract_stated_terms_honoured_not_capped():
    import extract
    # "Net 60" means 60 days: a stated credit period must never be shortened.
    # Chasing 15 days before the agreed date harms the customer's trust.
    row = extract.parse_invoice_text(
        "Invoice INV-9\nDate: 01/10/2026\nTerms: Net 60\nTotal: Rs 45,000\nBilled to Acme")
    assert row["due_date"] == "2026-11-30"
    assert row["date_assumed"] is True  # still computed, still needs confirmation


def test_extract_stated_terms_shorter_than_default_honoured():
    import extract
    row = extract.parse_invoice_text(
        "Invoice INV-9\nDate: 01/10/2026\nTerms: Net 30\nTotal: Rs 45,000\nBilled to Acme")
    assert row["due_date"] == "2026-10-31"
    assert row["date_assumed"] is True


def test_extract_no_terms_falls_back_to_45_day_estimate():
    import extract
    row = extract.parse_invoice_text(
        "Invoice INV-9\nDate: 01/10/2026\nTotal: Rs 45,000\nBilled to Acme")
    assert row["due_date"] == "2026-11-15"
    assert row["date_assumed"] is True
