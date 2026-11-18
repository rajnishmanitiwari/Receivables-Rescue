"""An invoice date is never presented as a payment due date.

Rows with an invoice date but no due date keep an unknown due date: they stay
unscheduled (neutral in the report, no chase draft) and no draft names the
invoice date as the date payment was due.
"""
from datetime import date
import engine
import messages

TODAY = date(2026, 11, 18)


def test_invoice_date_is_not_used_as_due_date():
    data = "customer, invoice no, amount, invoice date\nAcme, INV-1, 45000, 2026-01-01"
    invoices, warnings = engine.parse_invoices(data, today=TODAY)
    assert len(invoices) == 1
    inv = invoices[0]
    assert inv.due_date is None
    assert any("no readable due date" in w for w in warnings)

    report = engine.analyse(invoices, today=TODAY)
    row = report["priority"][0]
    assert row["days_overdue"] is None
    assert row["tier"] == ""
    assert row["probability"] is None
    assert row["bucket"] == "No confirmed due date"
    # No sendable draft exists for a row whose due date is unknown.
    built = messages.build_messages([row], sender="R", company="Co", limit=1)
    assert built == []


def test_real_due_date_still_drives_lateness():
    data = "customer, invoice no, amount, due date, invoice date\nAcme, INV-1, 45000, 2026-10-01, 2026-09-01"
    invoices, warnings = engine.parse_invoices(data, today=TODAY)
    assert invoices[0].due_date == date(2026, 10, 1)
    assert invoices[0].date_source == "column"
    report = engine.analyse(invoices, today=TODAY)
    assert report["priority"][0]["days_overdue"] == 48
    assert not any("no readable due date" in w for w in warnings)
