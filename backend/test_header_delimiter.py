import csv
import io
from datetime import date
import pytest
from fastapi.testclient import TestClient
import engine
import server

TODAY=date(2026,11,22)

def table(delimiter,competitor):
    out=io.StringIO()
    writer=csv.writer(out,delimiter=delimiter,quoting=csv.QUOTE_ALL)
    writer.writerow(['Customer','Invoice No','Amount','Due Date','Email','Phone'])
    customer='Acme "North" '+competitor.join(['branch']*30)
    invoice='INV-'+competitor.join(['42']*8)
    writer.writerow([customer,invoice,5000.49,'2026-10-15','',''])
    return out.getvalue(),customer,invoice

@pytest.mark.parametrize('delimiter',[',','\t',';','|'])
@pytest.mark.parametrize('competitor',[',','\t',';','|'])
def test_header_beats_delimiters_inside_quoted_identity(delimiter,competitor):
    text,customer,invoice=table(delimiter,competitor)
    assert engine._sniff_dialect(text)==delimiter
    rows,warnings=engine.parse_invoices(text,today=TODAY)
    assert len(rows)==1
    # Existing field length limits are intentionally unchanged.
    assert rows[0].customer==customer[:120]
    assert rows[0].invoice_no==invoice[:60]
    assert rows[0].amount==5000.49
    assert rows[0].due_date==date(2026,10,15)
    assert rows[0].date_source=='column'

def test_headerless_fallback_keeps_existing_choice():
    assert engine._sniff_dialect('Acme,I1,5000,2026-10-15')==','
    assert engine._sniff_dialect('Acme\tI1\t5000\t2026-10-15')=='\t'
    assert engine._sniff_dialect('Acme;I1;5000;2026-10-15')==';'
    assert engine._sniff_dialect('Acme|I1|5000|2026-10-15')=='|'

def test_live_routes_extract_then_analyse_preserve_headered_csv_with_quoted_semicolons():
    text='Customer,Invoice No,Amount,Due Date,Email,Phone\n"Acme;East;West;North;South;Accounts;Branch;HQ;Unit;Site;Region;Team",INV-42,5000.49,2026-10-15,,\n'
    with TestClient(server.app) as client:
        r=client.post('/api/extract',files=[('files',('quoted.csv',text,'text/csv'))])
        assert r.status_code==200
        assert len(r.json()['rows'])==1
        assert r.json()['rows'][0]['customer'].startswith('Acme;East;West')
        a=client.post('/api/analyse',json={'data':text,'today':TODAY.isoformat(),'currency':'INR'})
        assert a.status_code==200
        assert a.json()['report']['total_outstanding']==5000.49
        assert a.json()['messages'][0]['invoice_no']=='INV-42'
        assert a.json()['messages'][0]['due_date']=='2026-10-15'
