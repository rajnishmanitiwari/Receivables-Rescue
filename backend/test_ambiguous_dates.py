"""Ambiguous numeric due dates are never confirmed by column inference.

A date like 05/06/2026 reads as 5 June day-first or 6 May month-first. One
unambiguous row elsewhere in the column does not prove how another person
typed the ambiguous rows, so an ambiguous date is always a guess: kept
visible for the review screen (in the column's proven direction when one
exists, day-first otherwise) but never confirmed. Only an unambiguous value
or the user's explicit confirmation lets a date drive totals, tiers or chase
drafts - the same contract as positional and terms-computed dates.
"""
import asyncio
from datetime import date

import engine
import extract
import messages

TODAY = date(2026, 11, 18)

HEADER = "Customer,Invoice No,Amount,Due Date\n"


def _parse(data):
    return engine.parse_invoices(data, today=TODAY)


def _neutral_row(report, customer):
    return next(r for r in report["priority"] if r["customer"] == customer)


def _assert_neutral(row):
    assert row["days_overdue"] is None
    assert row["tier"] == ""
    assert row["probability"] is None
    assert row["bucket"] == "No confirmed due date"


def test_ambiguous_unconfirmed_even_with_day_first_evidence():
    data = HEADER + (
        "Acme,INV-1,1000,25/06/2026\n"   # day-first only (25 cannot be a month)
        "Beta,INV-2,2000,05/06/2026\n"   # ambiguous: shown as 5 June, unconfirmed
    )
    invoices, warnings = _parse(data)
    acme, beta = {i.customer: i for i in invoices}.values()
    assert acme.date_source == "column"
    assert acme.due_date == date(2026, 6, 25)
    assert beta.date_source == "ambiguous"
    assert beta.due_date == date(2026, 6, 5)
    assert any("day-first" in w and "matching the rest of the column" in w for w in warnings)


def test_ambiguous_unconfirmed_even_with_month_first_evidence():
    data = HEADER + (
        "Acme,INV-1,1000,06/25/2026\n"   # month-first only
        "Beta,INV-2,2000,05/06/2026\n"   # ambiguous: shown as 6 May, unconfirmed
    )
    invoices, warnings = _parse(data)
    beta = next(i for i in invoices if i.customer == "Beta")
    assert beta.date_source == "ambiguous"
    assert beta.due_date == date(2026, 5, 6)
    assert any("month-first" in w and "matching the rest of the column" in w for w in warnings)


def test_all_ambiguous_column_guesses_day_first_unconfirmed():
    data = HEADER + (
        "Acme,INV-1,1000,05/06/2026\n"
        "Beta,INV-2,2000,07/08/2026\n"
    )
    invoices, warnings = _parse(data)
    assert {i.customer: i.due_date for i in invoices} == {
        "Acme": date(2026, 6, 5), "Beta": date(2026, 8, 7),
    }
    assert all(i.date_source == "ambiguous" for i in invoices)
    assert any("no other date in the column settles which" in w for w in warnings)


def test_mixed_conventions_keep_certain_rows_and_flag_rest():
    data = HEADER + (
        "Acme,INV-1,1000,13/06/2026\n"   # day-first only
        "Beta,INV-2,2000,06/14/2026\n"   # month-first only (14 June)
        "Cory,INV-3,3000,05/06/2026\n"   # ambiguous, no safe reading
    )
    invoices, warnings = _parse(data)
    by_name = {i.customer: i for i in invoices}
    # Individually certain dates stay confirmed as written: a month above 12
    # is impossible, so these are certainties, not inferences.
    assert by_name["Acme"].due_date == date(2026, 6, 13)
    assert by_name["Acme"].date_source == "column"
    assert by_name["Beta"].due_date == date(2026, 6, 14)
    assert by_name["Beta"].date_source == "column"
    assert by_name["Cory"].date_source == "ambiguous"
    assert by_name["Cory"].due_date == date(2026, 6, 5)
    assert any("BOTH date formats" in w for w in warnings)


def test_iso_and_named_dates_do_not_settle_or_get_flagged():
    data = HEADER + (
        "Acme,INV-1,1000,2026-06-05\n"   # ISO: convention-free, confirmed
        "Beta,INV-2,2000,5 Jun 2026\n"   # named month: convention-free, confirmed
        "Cory,INV-3,3000,05/06/2026\n"   # still nothing settles it
    )
    invoices, warnings = _parse(data)
    by_name = {i.customer: i for i in invoices}
    assert by_name["Acme"].date_source == "column"
    assert by_name["Beta"].date_source == "column"
    assert by_name["Cory"].date_source == "ambiguous"


def test_ambiguous_rows_never_drive_lateness_or_drafts():
    for probe in ("25/06/2026", "06/25/2026", "2026-06-05"):
        data = HEADER + (
            f"Acme,INV-1,1000,{probe}\n"
            "Beta,INV-2,2000,05/06/2026\n"
        )
        invoices, _ = _parse(data)
        report = engine.analyse(invoices, today=TODAY)
        _assert_neutral(_neutral_row(report, "Beta"))
        drafts = messages.build_messages(
            report["priority"], sender="X", company="Y", currency="INR"
        )
        assert not any(m.get("customer") == "Beta" for m in drafts)


def test_two_digit_year_is_equally_ambiguous():
    data = HEADER + "Acme,INV-1,1000,05/06/26\n"
    invoices, warnings = _parse(data)
    assert invoices[0].date_source == "ambiguous"
    assert invoices[0].due_date == date(2026, 6, 5)
    assert any("settles which" in w for w in warnings)


def test_positional_mode_unaffected_by_convention_logic():
    # Headerless input is already an assumption; ambiguity changes nothing.
    data = "Acme,INV-1,1000,05/06/2026\nBeta,INV-2,2000,25/06/2026\n"
    invoices, warnings = _parse(data)
    assert all(i.date_source == "positional" for i in invoices)
    assert not any("month-first" in w or "day-first" in w for w in warnings)


def test_unambiguous_numeric_dates_unchanged():
    data = HEADER + (
        "Acme,INV-1,1000,25/06/2026\n"
        "Beta,INV-2,2000,06/25/2026\n"
    )
    invoices, warnings = _parse(data)
    assert all(i.date_source == "column" for i in invoices)
    assert not any("05/06/2026" in w for w in warnings)


def test_extract_marks_ambiguous_dates_as_assumed():
    data = HEADER + (
        "Acme,INV-1,1000,25/06/2026\n"
        "Beta,INV-2,2000,05/06/2026\n"
    )
    out = asyncio.run(extract.extract_file("bills.csv", data.encode()))
    beta = next(r for r in out["rows"] if r["customer"] == "Beta")
    assert beta["date_assumed"] is True
    assert beta["due_date"] == "2026-06-05"
    assert "unconfirmed" in out["note"]


def test_extract_keeps_unambiguous_dates_confirmed():
    data = HEADER + (
        "Acme,INV-1,1000,25/06/2026\n"
        "Beta,INV-2,2000,06/14/2026\n"
    )
    out = asyncio.run(extract.extract_file("bills.csv", data.encode()))
    assert all(r["date_assumed"] is False for r in out["rows"])


def test_zero_components_are_unparseable_not_ambiguous():
    data = HEADER + "Acme,INV-1,1000,00/05/2026\n"
    invoices, warnings = _parse(data)
    assert invoices[0].due_date is None
    assert invoices[0].date_source == ""
    assert any("no readable due date" in w for w in warnings)


def test_ambiguous_guesses_do_not_corrupt_duplicate_identity():
    # Two identical ambiguous rows are still exact duplicates of each other.
    data = HEADER + (
        "Acme,INV-1,1000,05/06/2026\n"
        "Acme,INV-1,1000,05/06/2026\n"
    )
    invoices, warnings = _parse(data)
    assert len(invoices) == 1
    assert any("counted once" in w for w in warnings)


def test_same_day_numerics_stay_confirmed_and_do_not_settle():
    # 07/07/2026 reads identically day-first and month-first: no ambiguity.
    data = HEADER + (
        "Acme,INV-1,1000,07/07/2026\n"
        "Beta,INV-2,2000,05/06/2026\n"
    )
    invoices, warnings = _parse(data)
    by_name = {i.customer: i for i in invoices}
    assert by_name["Acme"].date_source == "column"
    assert by_name["Acme"].due_date == date(2026, 7, 7)
    # A same-day numeric carries no convention evidence either.
    assert by_name["Beta"].date_source == "ambiguous"
    assert any("no other date in the column settles which" in w for w in warnings)


def test_extract_rows_carry_the_assumed_reason():
    data = HEADER + (
        "Acme,INV-1,1000,25/06/2026\n"
        "Beta,INV-2,2000,05/06/2026\n"
    )
    out = asyncio.run(extract.extract_file("bills.csv", data.encode()))
    acme = next(r for r in out["rows"] if r["customer"] == "Acme")
    beta = next(r for r in out["rows"] if r["customer"] == "Beta")
    assert acme["date_assumed_reason"] == ""
    assert beta["date_assumed_reason"] == "ambiguous"

    positional = asyncio.run(extract.extract_file(
        "bills.csv", b"Acme,INV-1,1000,25/06/2026\n"))
    assert positional["rows"][0]["date_assumed_reason"] == "positional"


def _pdf_row(text):
    return extract.parse_invoice_text(text)


def test_pdf_stated_due_date_ambiguous_stays_unconfirmed():
    row = _pdf_row("Invoice No: INV-9\nTotal: Rs 1,000\nDue Date: 05/06/2026\n")
    assert row["due_date"] == "2026-06-05"   # day-first guess, shown
    assert row["date_assumed"] is True        # ...but never silently confirmed
    assert row["date_assumed_reason"] == "ambiguous"


def test_pdf_stated_due_date_unambiguous_stays_confirmed():
    row = _pdf_row("Invoice No: INV-9\nTotal: Rs 1,000\nDue Date: 25/06/2026\n")
    assert row["due_date"] == "2026-06-25"
    assert row["date_assumed"] is False


def test_pdf_same_day_due_date_stays_confirmed():
    row = _pdf_row("Invoice No: INV-9\nTotal: Rs 1,000\nDue Date: 07/07/2026\n")
    assert row["due_date"] == "2026-07-07"
    assert row["date_assumed"] is False


def test_pdf_iso_due_date_stays_confirmed():
    row = _pdf_row("Invoice No: INV-9\nTotal: Rs 1,000\nDue Date: 2026-06-05\n")
    assert row["due_date"] == "2026-06-05"
    assert row["date_assumed"] is False


def test_pdf_computed_due_date_reason_is_computed():
    row = _pdf_row("Invoice No: INV-9\nTotal: Rs 1,000\nInvoice Date: 2026-06-01\nTerms: Net 60\n")
    assert row["due_date"] == "2026-07-31"
    assert row["date_assumed"] is True
    assert row["date_assumed_reason"] == "computed"


def test_pdf_computed_due_on_ambiguous_base_is_visibly_unconfirmed():
    # Base date 05/06/2026 reads day-first (5 Jun) or month-first (6 May), so a
    # due date computed from it can be a month off. It must not present as an
    # ordinary computed estimate: it gets the visibly unconfirmed treatment.
    row = _pdf_row("Invoice No: INV-9\nTotal: Rs 1,000\nInvoice Date: 05/06/2026\nTerms: Net 30\n")
    assert row["due_date"] == "2026-07-05"  # day-first base + 30 days
    assert row["date_assumed"] is True
    assert row["date_assumed_reason"] == "ambiguous-computed"


def test_pdf_computed_due_on_unambiguous_base_stays_computed():
    # 25/06/2026 can only read day-first: an ordinary computed estimate.
    row = _pdf_row("Invoice No: INV-9\nTotal: Rs 1,000\nInvoice Date: 25/06/2026\nTerms: Net 30\n")
    assert row["due_date"] == "2026-07-25"
    assert row["date_assumed"] is True
    assert row["date_assumed_reason"] == "computed"


def test_pdf_computed_due_on_same_day_base_stays_computed():
    # 07/07/2026 reads identically both ways: no ambiguity to surface.
    row = _pdf_row("Invoice No: INV-9\nTotal: Rs 1,000\nInvoice Date: 07/07/2026\nTerms: Net 30\n")
    assert row["due_date"] == "2026-08-06"
    assert row["date_assumed"] is True
    assert row["date_assumed_reason"] == "computed"
