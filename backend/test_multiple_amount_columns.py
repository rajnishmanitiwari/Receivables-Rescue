"""Never silently pick original invoice value over an outstanding balance."""
import asyncio
import csv
import io

import pytest
from fastapi.testclient import TestClient
import engine
import extract
import server


def table(headers, delimiter=','):
    out = io.StringIO()
    writer = csv.writer(out, delimiter=delimiter)
    writer.writerow(['Customer', 'Invoice No', *headers, 'Due Date'])
    writer.writerow(['Acme', 'I50', *(['5000.49', '100.49'][:len(headers)]), '2026-10-15'])
    return out.getvalue()


@pytest.mark.parametrize('delimiter', [',', '\t', ';', '|'])
@pytest.mark.parametrize('headers', [['Invoice Amount', 'Outstanding'], ['Outstanding', 'Invoice Amount'], ['Amount', 'Amount'], ['Balance Due', 'Total']])
def test_multiple_exact_amount_aliases_reject_regardless_order_or_delimiter(delimiter, headers):
    text = table(headers, delimiter)
    with pytest.raises(engine.ParseError, match='More than one amount column'):
        engine.parse_invoices(text)
    result = asyncio.run(extract.extract_file('ambiguous.csv', text.encode()))
    assert result['rows'] == [] and 'No rows from this input' in result['note']
    assert '5000.49' not in result['note']


@pytest.mark.parametrize('header', engine._HEADER_ALIASES['amount'])
def test_single_supported_amount_alias_keeps_working(header):
    rows, _ = engine.parse_invoices(table([header]))
    assert len(rows) == 1 and rows[0].amount == 5000.49


def test_correction_uses_only_the_amount_explicitly_kept():
    text = 'Customer,Invoice No,Amount,Due Date\nAcme,I50,100.49,2026-10-15'
    rows, _ = engine.parse_invoices(text)
    assert rows[0].amount == 100.49
    with TestClient(server.app) as client:
        response = client.post('/api/analyse', json={'data': table(['Invoice Amount', 'Outstanding'])})
    assert response.status_code == 422
    assert 'More than one amount column' in response.json()['detail']
    assert 'report' not in response.json()


def test_mixed_files_preserve_unambiguous_file():
    with TestClient(server.app) as client:
        response = client.post('/api/extract', files=[('files', ('bad.csv', table(['Amount', 'Balance']), 'text/csv')), ('files', ('good.csv', table(['Amount']), 'text/csv'))])
    result = response.json()
    assert len(result['rows']) == 1 and result['rows'][0]['amount'] == 5000.49
    assert len(result['notes']) == 1 and result['notes'][0].startswith('bad.csv:')
