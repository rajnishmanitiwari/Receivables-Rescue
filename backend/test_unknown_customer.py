"""Blank customer cells must never become an "Unnamed customer" placeholder.

A placeholder merges distinct unknown debtors into one pseudo-customer:
by-customer totals combine bills owed by different people, and chase drafts
(including final notices) would address them as one debtor. Unknown means
unknown, so analysis is rejected with a useful validation response instead.
"""
from datetime import date

import pytest
from fastapi.testclient import TestClient

import engine
import server

TODAY = date(2026, 8, 27)


def test_blank_customer_row_rejected():
    text = "Customer,Invoice No,Amount,Due Date\n,INV-9,5000,2026-01-01\n"
    with pytest.raises(engine.ParseError, match="no customer name"):
        engine.parse_invoices(text, today=TODAY)


def test_blank_customer_count_in_message():
    text = (
        "Customer,Invoice No,Amount,Due Date\n"
        "Acme,INV-1,1000,2026-01-01\n"
        ",INV-2,2000,2026-01-01\n"
        "  ,INV-3,3000,2026-01-01\n"
    )
    with pytest.raises(engine.ParseError) as exc:
        engine.parse_invoices(text, today=TODAY)
    assert "2 bill(s)" in str(exc.value)
    assert "never guessed" in str(exc.value)


def test_blank_customer_without_amount_stays_skipped():
    # Rows with no usable amount are already skipped; they never reach the
    # customer check, so they do not block analysis of the valid rows.
    text = "Customer,Invoice No,Amount,Due Date\n,INV-9,,2026-01-01\nAcme,INV-1,1000,2026-01-01\n"
    invoices, warnings = engine.parse_invoices(text, today=TODAY)
    assert [i.customer for i in invoices] == ["Acme"]
    assert any("no usable amount" in w for w in warnings)


def test_named_rows_unaffected():
    text = "Customer,Invoice No,Amount,Due Date\nAcme,INV-1,1000,2026-01-01\n"
    invoices, _ = engine.parse_invoices(text, today=TODAY)
    assert invoices[0].customer == "Acme"


def test_analyse_api_returns_useful_422():
    c = TestClient(server.app)
    r = c.post("/api/analyse", json={
        "data": "Customer,Invoice No,Amount,Due Date\n,INV-9,5000,2026-01-01\n",
    })
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "no customer name" in detail
    assert "1 bill(s)" in detail
