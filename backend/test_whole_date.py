"""Date cells must be read in full before a due date is confirmed."""
import csv
import io
from datetime import date

import pytest
from fastapi.testclient import TestClient
import engine
import server


@pytest.fixture(autouse=True)
def isolated_rate_limit_state():
    server._hits.clear()
    yield
    server._hits.clear()


@pytest.mark.parametrize('raw', [
    '2026-10-15/2027-01-15', '2026-10-15 to 2026-11-15',
    '2026-10-15 overdue', '2026-10-15?', '2026-10-150',
    '2026-10-15T99:99:99', '2026-10-15T12:99:00Z',
    '2026-10-15T12:00:00Z junk', '2026-10-15T',
    '2026-10-15T12:00:00+05:99', '2026-02-30T12:00:00Z', '2026-10-15T12:00:00+99:00',
])
def test_partial_or_invalid_date_is_unknown(raw):
    assert engine.parse_date(raw) is None


@pytest.mark.parametrize('raw', [
    '2026-10-15', '2026-10-15 12:30:00', '2026-10-15T12:30:00Z',
    '2026-10-15T12:30', '2026-10-15T12:30:00.123456+05:30',
    '2026-10-15T23:30:00-04:00', '15/10/2026', '15 October 2026',
])
def test_supported_whole_dates_keep_stated_day(raw):
    assert engine.parse_date(raw) == date(2026, 10, 15)


def test_non_padded_iso_date_stays_supported():
    assert engine.parse_date('2026-1-5') == date(2026, 1, 5)


@pytest.mark.parametrize('delimiter', [',', '\t', ';', '|'])
@pytest.mark.parametrize('mixed', [False, True])
def test_unreadable_due_date_stays_unscheduled_in_extract_and_analysis(delimiter, mixed):
    out = io.StringIO()
    writer = csv.writer(out, delimiter=delimiter)
    writer.writerow(['Customer', 'Invoice No', 'Amount', 'Due Date'])
    writer.writerow(['Unclear date', 'X60', '5000.49', '2026-10-15/2027-01-15'])
    if mixed:
        writer.writerow(['Confirmed', 'I60', '300.49', '2026-10-15'])
    with TestClient(server.app) as client:
        extracted = client.post('/api/extract', files=[('files', ('dates.csv', out.getvalue(), 'text/csv'))])
        analysed = client.post('/api/analyse', json={'data': out.getvalue()})
    assert extracted.status_code == analysed.status_code == 200
    unknown = next(row for row in extracted.json()['rows'] if row['customer'] == 'Unclear date')
    assert not unknown['due_date']
    report = analysed.json()['report']
    row = next(row for row in report['priority'] if row['customer'] == 'Unclear date')
    assert row['due_date'] is None and row['date_source'] == ''
    assert row['days_overdue'] is None and row['tier'] == ''
    assert row['probability'] is None and row['expected_value'] is None
    assert report['total_outstanding'] == (5300.98 if mixed else 5000.49)
    assert [m['customer'] for m in analysed.json()['messages']] == (['Confirmed'] if mixed else [])


@pytest.mark.parametrize('width', range(1, 7))
@pytest.mark.parametrize('zone', ['', 'Z', '+05:30', '-04:00'])
def test_iso_fraction_widths_supported_on_python310(width, zone):
    raw = '2026-10-15T12:30:00.' + '1' * width + zone
    assert engine.parse_date(raw) == date(2026, 10, 15)
