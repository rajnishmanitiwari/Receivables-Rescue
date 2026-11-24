"""Overflowing amount cells cannot enter invoices or break JSON responses."""
import csv
import io
import math

import pytest
from fastapi.testclient import TestClient
import engine
import server

HUGE = '9' * 400


@pytest.fixture(autouse=True)
def isolated_rate_limit_state():
    # TestClient cases share one synthetic IP. Keep this module's request
    # count isolated without weakening the application's rate limit.
    server._hits.clear()
    yield
    server._hits.clear()


@pytest.mark.parametrize('raw', [HUGE, '-' + HUGE, '−' + HUGE, '(' + HUGE + ')', float('inf'), float('-inf'), float('nan')])
def test_nonfinite_amount_is_unusable(raw):
    assert engine.parse_amount(raw) is None


@pytest.mark.parametrize('raw,want', [('100.49', 100.49), ('1' + '0' * 30, 1e30), ('−5000.49', -5000.49), ('(−5000.49)', -5000.49)])
def test_finite_formats_unchanged(raw, want):
    assert engine.parse_amount(raw) == want
    assert math.isfinite(engine.parse_amount(raw))


def text(delimiter, mixed):
    out = io.StringIO()
    writer = csv.writer(out, delimiter=delimiter)
    writer.writerow(['Customer', 'Invoice No', 'Amount', 'Due Date'])
    writer.writerow(['Overflow', 'X52', HUGE, '2026-10-15'])
    if mixed:
        writer.writerow(['Valid', 'I52', '100.49', '2026-10-15'])
    return out.getvalue()


@pytest.mark.parametrize('delimiter', [',', '\t', ';', '|'])
@pytest.mark.parametrize('mixed', [False, True])
def test_overflow_extract_and_analysis_keep_existing_unusable_row_behavior(delimiter, mixed):
    data = text(delimiter, mixed)
    with TestClient(server.app) as client:
        extracted = client.post('/api/extract', files=[('files', ('overflow.csv', data, 'text/csv'))])
        analysed = client.post('/api/analyse', json={'data': data})
    assert extracted.status_code == 200
    rows = extracted.json()['rows']
    assert len(rows) == (1 if mixed else 0)
    if mixed:
        assert rows[0]['customer'] == 'Valid' and rows[0]['amount'] == 100.49
        assert analysed.status_code == 200
        assert analysed.json()['report']['total_outstanding'] == 100.49
        assert all(m['customer'] != 'Overflow' for m in analysed.json()['messages'])
    else:
        assert analysed.status_code == 422
        assert 'report' not in analysed.json()
