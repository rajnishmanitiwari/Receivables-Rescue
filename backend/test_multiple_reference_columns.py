"""Competing bill identifiers must not silently merge or quarantine bills."""
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

def table(headers, delimiter=',', second='INV1'):
    out=io.StringIO(); writer=csv.writer(out,delimiter=delimiter)
    writer.writerow(['Customer',*headers,'Amount','Due Date'])
    writer.writerow(['Acme','ORDER1',second,'5000.49','2026-10-15'])
    writer.writerow(['Acme','ORDER1','INV2','5000.49','2026-10-15'])
    return out.getvalue()

@pytest.mark.parametrize('delimiter',[',','\t',';','|'])
@pytest.mark.parametrize('headers',[
    ['Invoice No','Reference'],['Reference','Invoice No'],['Invoice No','Invoice No'],
    ['Bill No','Document No'],['Inv','Invoice ID']])
def test_multiple_exact_reference_aliases_reject_before_deduplication(delimiter,headers):
    text=table(headers,delimiter)
    with pytest.raises(engine.ParseError,match='More than one bill-number column'):
        engine.parse_invoices(text)
    with TestClient(server.app) as client:
        extracted=client.post('/api/extract',files=[('files',('refs.csv',text,'text/csv'))])
        analysed=client.post('/api/analyse',json={'data':text})
    assert extracted.status_code==200 and extracted.json()['rows']==[]
    assert 'refs.csv:' in extracted.json()['notes'][0]
    assert 'No rows from this input' in extracted.json()['notes'][0]
    assert analysed.status_code==422 and 'report' not in analysed.json()

@pytest.mark.parametrize('second',['ORDER1',''])
def test_equal_or_blank_second_reference_still_needs_choice(second):
    with pytest.raises(engine.ParseError,match='More than one bill-number column'):
        engine.parse_invoices(table(['Invoice No','Reference'],second=second))

@pytest.mark.parametrize('header',engine._HEADER_ALIASES['invoice_no'])
def test_one_reference_alias_still_preserves_two_distinct_bills(header):
    text='Customer,'+header+',Amount,Due Date\nAcme,INV1,5000.49,2026-10-15\nAcme,INV2,5000.49,2026-10-15'
    rows,_=engine.parse_invoices(text)
    assert len(rows)==2 and {r.invoice_no for r in rows}=={'INV1','INV2'}
    assert sum(r.amount for r in rows)==10000.98


def test_mixed_upload_keeps_valid_file_and_explicit_reference_correction():
    good='Customer,Invoice No,Amount,Due Date\nAcme,INV1,5000.49,2026-10-15\nAcme,INV2,5000.49,2026-10-15'
    with TestClient(server.app) as client:
        extracted=client.post('/api/extract',files=[('files',('bad.csv',table(['Invoice No','Reference']),'text/csv')),('files',('good.csv',good,'text/csv'))])
        corrected=client.post('/api/analyse',json={'data':good,'today':'2026-11-27'})
    result=extracted.json()
    assert len(result['rows'])==2
    assert len(result['notes'])==1 and result['notes'][0].startswith('bad.csv:')
    assert corrected.status_code==200 and corrected.json()['report']['total_outstanding']==10000.98
    assert {r['invoice_no'] for r in corrected.json()['report']['priority']}=={'INV1','INV2'}
    assert len(corrected.json()['messages'])==2
