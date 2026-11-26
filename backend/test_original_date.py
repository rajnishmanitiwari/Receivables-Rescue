"""Unreadable CSV date text survives extraction for session-only correction."""
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

@pytest.mark.parametrize('delimiter', [',', '\t', ';', '|'])
@pytest.mark.parametrize('raw', ['2026-10-15/2027-01-15', '2026-10-15T99:99:99', '<img src=x onerror=alert(1)>', 'unknown\ncheck invoice', 'x'*1200])
def test_original_unreadable_date_preserved_without_confirming_it(delimiter, raw):
    out=io.StringIO(); writer=csv.writer(out,delimiter=delimiter)
    writer.writerow(['Customer','Invoice No','Amount','Due Date'])
    writer.writerow(['Unknown','X61','5000.49',raw])
    writer.writerow(['Known','I61','300.49','2026-10-15'])
    with TestClient(server.app) as client:
        extracted=client.post('/api/extract',files=[('files',('dates.csv',out.getvalue(),'text/csv'))])
        analysed=client.post('/api/analyse',json={'data':out.getvalue()})
    assert extracted.status_code==analysed.status_code==200
    unknown, known=extracted.json()['rows']
    assert unknown['due_date_raw']==raw and unknown['due_date'] is None
    assert known['due_date_raw']=='' and known['due_date']=='2026-10-15'
    priority=analysed.json()['report']['priority']
    row=next(r for r in priority if r['customer']=='Unknown')
    assert row['days_overdue'] is None and row['tier']==''
    assert all('due_date_raw' not in r for r in priority)
    assert [m['customer'] for m in analysed.json()['messages']]==['Known']

@pytest.mark.parametrize('raw', ['', '2026-10-15', '05/06/2026'])
def test_blank_valid_or_ambiguous_date_not_labelled_unreadable(raw):
    rows,_=engine.parse_invoices('Customer,Amount,Due Date\nAcme,5000.49,'+raw)
    assert rows[0].due_date_raw==''
