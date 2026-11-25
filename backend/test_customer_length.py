"""Never truncate debtor identity and silently merge distinct customers."""
import csv
import io
import pytest
from fastapi.testclient import TestClient
import engine
import server


@pytest.fixture(autouse=True)
def isolated_rate_limit_state():
    server._hits.clear()
    yield
    server._hits.clear()


def text(delimiter, numbers):
    out = io.StringIO()
    writer = csv.writer(out, delimiter=delimiter)
    writer.writerow(['Customer', 'Invoice No', 'Amount', 'Due Date'])
    for number in numbers:
        writer.writerow([number, 'I54', '100.49', '2026-10-15'])
    return out.getvalue()


@pytest.mark.parametrize('delimiter', [',', '\t', ';', '|'])
@pytest.mark.parametrize('numbers', [
    ['I' * 120 + 'A', 'I' * 120 + 'B'],
    ['Valid', 'I' * 121],
    ['I' * 121],
])
def test_long_customer_never_imported_or_analysed(delimiter, numbers):
    data = text(delimiter, numbers)
    with pytest.raises(engine.ParseError, match='longer than 120 characters'):
        engine.parse_invoices(data)
    with TestClient(server.app) as client:
        extracted = client.post('/api/extract', files=[('files', ('customers.csv', data, 'text/csv'))])
        analysed = client.post('/api/analyse', json={'data': data})
    assert extracted.status_code == 200 and extracted.json()['rows'] == []
    assert 'longer than 120 characters' in str(extracted.json())
    assert analysed.status_code == 422 and 'report' not in analysed.json()
    assert 'longer than 120 characters' in analysed.json()['detail']


@pytest.mark.parametrize('delimiter', [',', '\t', ';', '|'])
def test_boundary_customers_retained_and_distinct(delimiter):
    numbers = ['I' * 119 + 'A', 'I' * 119 + 'B']
    rows, notes = engine.parse_invoices(text(delimiter, numbers))
    assert [r.customer for r in rows] == numbers
    assert sum(r.amount for r in rows) == 200.98
    assert not any('duplicate' in note for note in notes)


def test_boundary_exact_duplicate_still_counted_once():
    rows, notes = engine.parse_invoices(text(',', ['I' * 120] * 2))
    assert len(rows) == 1 and rows[0].customer == 'I' * 120
    assert any('counted once' in note for note in notes)


def test_headerless_long_customer_rejected():
    with pytest.raises(engine.ParseError, match='longer than 120 characters'):
        engine.parse_invoices('I' * 121 + ',I54,100.49,2026-10-15')
