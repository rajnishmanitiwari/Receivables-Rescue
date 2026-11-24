"""A detected quote syntax error must not quietly drop later financial records."""
import asyncio
import csv
import io
from datetime import date

import pytest
from fastapi.testclient import TestClient
import engine
import extract
import server


@pytest.mark.parametrize('delimiter', [',', '\t', ';', '|'])
@pytest.mark.parametrize('bad', ['"Broken', '"Broken"trailing'])
def test_quote_syntax_error_rejects_whole_input_including_valid_prefix(delimiter, bad):
    text = delimiter.join(['Customer', 'Invoice No', 'Amount', 'Due Date']) + '\n'
    text += delimiter.join(['Valid', 'I1', '100.49', '2026-10-15']) + '\n'
    text += delimiter.join([bad, 'I2', '5000.49', '2026-10-15'])
    with pytest.raises(engine.ParseError, match='CSV text could not be read safely'):
        engine.parse_invoices(text)
    result = asyncio.run(extract.extract_file('bad.csv', text.encode()))
    assert result['rows'] == [] and 'No rows from this input' in result['note']
    assert 'Broken' not in result['note'] and '5000.49' not in result['note']


@pytest.mark.parametrize('delimiter', [',', '\t', ';', '|'])
def test_valid_quoted_multiline_and_escaped_quote_identity_remain_supported(delimiter):
    out = io.StringIO()
    writer = csv.writer(out, delimiter=delimiter)
    writer.writerow(['Customer', 'Invoice No', 'Amount', 'Due Date'])
    writer.writerow(['Acme "North"\nBranch', 'I"49', '5000.49', '2026-10-15'])
    rows, _ = engine.parse_invoices(out.getvalue())
    assert len(rows) == 1 and rows[0].customer == 'Acme "North"\nBranch'
    assert rows[0].invoice_no == 'I"49' and rows[0].amount == 5000.49
    assert rows[0].due_date == date(2026, 10, 15)


def test_analysis_route_rejects_syntax_error_without_partial_report():
    text = 'Customer,Invoice No,Amount,Due Date\nValid,I1,100.49,2026-10-15\n"Broken,I2,5000.49,2026-10-15'
    with TestClient(server.app) as client:
        response = client.post('/api/analyse', json={'data': text})
    assert response.status_code == 422
    assert 'CSV text could not be read safely' in response.json()['detail']
    assert 'report' not in response.json()
