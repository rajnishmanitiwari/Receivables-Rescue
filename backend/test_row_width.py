"""Recognized header rows cannot silently lose nonempty extra cells."""
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


def text(delimiter, extra, valid_prefix=False):
    out = io.StringIO()
    writer = csv.writer(out, delimiter=delimiter)
    writer.writerow(['Customer', 'Invoice No', 'Amount', 'Due Date'])
    if valid_prefix:
        writer.writerow(['Valid', 'I1', '100.49', '2026-10-15'])
    writer.writerow(['Acme', 'I55', '5', '000.49', '2026-10-15'] if extra else ['Acme', 'I55', '5,000.49', '2026-10-15'])
    return out.getvalue()


@pytest.mark.parametrize('delimiter', [',', '\t', ';', '|'])
@pytest.mark.parametrize('prefix', [False, True])
def test_nonempty_extra_cell_rejects_whole_input(delimiter, prefix):
    data = text(delimiter, True, prefix)
    with pytest.raises(engine.ParseError, match='more fields than the header'):
        engine.parse_invoices(data)
    with TestClient(server.app) as client:
        extracted = client.post('/api/extract', files=[('files', ('wide.csv', data, 'text/csv'))])
        analysed = client.post('/api/analyse', json={'data': data})
    assert extracted.status_code == 200 and extracted.json()['rows'] == []
    assert 'more fields than the header' in str(extracted.json())
    assert analysed.status_code == 422 and 'report' not in analysed.json()


@pytest.mark.parametrize('delimiter', [',', '\t', ';', '|'])
def test_quoted_amount_and_empty_trailing_padding_still_work(delimiter):
    data = text(delimiter, False).rstrip('\r\n') + delimiter * 2 + '\n'
    rows, _ = engine.parse_invoices(data)
    assert len(rows) == 1 and rows[0].amount == 5000.49
    assert rows[0].due_date.isoformat() == '2026-10-15'


def test_short_row_stays_undated_not_rejected():
    rows, _ = engine.parse_invoices('Customer,Invoice No,Amount,Due Date\nAcme,I55,100.49')
    assert len(rows) == 1 and rows[0].due_date is None


def test_headerless_fallback_unchanged():
    rows, _ = engine.parse_invoices('Acme,I55,100.49,2026-10-15,acme@example.invalid,+919876543210')
    assert len(rows) == 1 and rows[0].amount == 100.49
