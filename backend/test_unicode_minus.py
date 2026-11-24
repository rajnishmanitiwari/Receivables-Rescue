"""Explicit Unicode minus must not become a positive chase amount."""
import asyncio
import csv
import io

import pytest
from fastapi.testclient import TestClient
import engine
import extract
import server


@pytest.mark.parametrize('raw,want', [
    ('(−5000.49)', -5000.49), ('(−₹5,000.49)', -5000.49), ('(-5000.49)', -5000.49),
    ('−5000.49', -5000.49), ('−₹5,000.49', -5000.49), ('₹−5,000.49', -5000.49),
    ('−1,25,000.50', -125000.5), ('−5.000,49', -5000.49), ('−0.49', -0.49),
    ('-5000.49', -5000.49), ('(5000.49)', -5000.49),
    ('₹5,000.49', 5000.49), ('1,25,000.50', 125000.5), ('5.000,49', 5000.49),
])
def test_sign_and_supported_positive_formats(raw, want):
    assert engine.parse_amount(raw) == want


def text(delimiter, mixed=True, amount='−5000.49'):
    out = io.StringIO()
    writer = csv.writer(out, delimiter=delimiter)
    writer.writerow(['Customer', 'Invoice No', 'Amount', 'Due Date'])
    writer.writerow(['Credit Party', 'C51', amount, '2026-10-15'])
    if mixed:
        writer.writerow(['Valid', 'I51', '100.49', '2026-10-15'])
    return out.getvalue()


@pytest.mark.parametrize('delimiter', [',', '\t', ';', '|'])
def test_credit_is_skipped_without_becoming_positive_bill(delimiter):
    data = text(delimiter)
    rows, notes = engine.parse_invoices(data)
    assert len(rows) == 1 and rows[0].customer == 'Valid' and rows[0].amount == 100.49
    assert any('Skipped 1 row' in note for note in notes)
    result = asyncio.run(extract.extract_file('credits.csv', data.encode()))
    assert len(result['rows']) == 1 and result['rows'][0]['amount'] == 100.49


def test_negative_only_input_never_generates_analysis():
    with TestClient(server.app) as client:
        extracted = client.post('/api/extract', files=[('files', ('credit.csv', text(',', False), 'text/csv'))])
        analysed = client.post('/api/analyse', json={'data': text(',', False)})
        mixed = client.post('/api/analyse', json={'data': text(',')})
    assert extracted.json()['rows'] == []
    assert analysed.status_code == 422 and 'report' not in analysed.json()
    assert mixed.status_code == 200
    assert mixed.json()['report']['total_outstanding'] == 100.49
    assert all(message['customer'] != 'Credit Party' for message in mixed.json()['messages'])

@pytest.mark.parametrize('amount', ['(−5000.49)', '(−₹5,000.49)', '(-5000.49)'])
def test_parenthesised_explicit_minus_cannot_create_positive_import_or_chase(amount):
    data = text(',', amount=amount)
    extracted = asyncio.run(extract.extract_file('credit.csv', data.encode()))
    assert len(extracted['rows']) == 1 and extracted['rows'][0]['customer'] == 'Valid'
    with TestClient(server.app) as client:
        result = client.post('/api/analyse', json={'data': data})
    assert result.status_code == 200
    assert result.json()['report']['total_outstanding'] == 100.49
    assert all(m['customer'] != 'Credit Party' for m in result.json()['messages'])
