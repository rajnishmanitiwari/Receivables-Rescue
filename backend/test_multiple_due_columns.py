"""Multiple explicit due dates require a choice, never silent first-column use."""
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

def table(headers, delimiter=',', second='2027-01-15'):
    out=io.StringIO(); writer=csv.writer(out,delimiter=delimiter)
    writer.writerow(['Customer','Invoice No','Amount',*headers])
    writer.writerow(['Acme','I62','5000.49','2026-10-15',second])
    return out.getvalue()

@pytest.mark.parametrize('delimiter',[',','\t',';','|'])
@pytest.mark.parametrize('headers',[
    ['Due Date','Due On'],['Due On','Due Date'],['Due Date','Due Date'],
    ['Payment Due','Maturity'],['Due','DueDate']])
def test_multiple_exact_due_aliases_reject_in_extract_and_analysis(delimiter,headers):
    text=table(headers,delimiter)
    with pytest.raises(engine.ParseError,match='More than one due-date column'):
        engine.parse_invoices(text)
    with TestClient(server.app) as client:
        extracted=client.post('/api/extract',files=[('files',('dates.csv',text,'text/csv'))])
        analysed=client.post('/api/analyse',json={'data':text})
    assert extracted.status_code==200 and extracted.json()['rows']==[]
    assert 'dates.csv:' in extracted.json()['notes'][0]
    assert 'No rows from this input' in extracted.json()['notes'][0]
    assert analysed.status_code==422 and 'report' not in analysed.json()

@pytest.mark.parametrize('second',['2026-10-15',''])
def test_repeated_columns_still_need_explicit_choice_when_equal_or_blank(second):
    with pytest.raises(engine.ParseError,match='More than one due-date column'):
        engine.parse_invoices(table(['Due Date','Due On'],second=second))

@pytest.mark.parametrize('header',engine._HEADER_ALIASES['due_date'])
def test_one_due_alias_with_invoice_date_still_confirms_only_due(header):
    text='Customer,Invoice No,Amount,Invoice Date,'+header+'\nAcme,I62,5000.49,2026-09-01,2026-10-15'
    rows,_=engine.parse_invoices(text)
    assert rows[0].due_date.isoformat()=='2026-10-15' and rows[0].date_source=='column'


def test_mixed_upload_preserves_valid_file_and_explicit_correction():
    bad=table(['Due Date','Due On'])
    good='Customer,Invoice No,Amount,Due Date\nValid,G62,300.49,2026-10-15'
    with TestClient(server.app) as client:
        extracted=client.post('/api/extract',files=[('files',('bad.csv',bad,'text/csv')),('files',('good.csv',good,'text/csv'))])
        corrected=client.post('/api/analyse',json={'data':'Customer,Invoice No,Amount,Due Date\nAcme,I62,5000.49,2027-01-15','today':'2026-11-27'})
    result=extracted.json()
    assert len(result['rows'])==1 and result['rows'][0]['amount']==300.49
    assert len(result['notes'])==1 and result['notes'][0].startswith('bad.csv:')
    assert corrected.status_code==200
    row=corrected.json()['report']['priority'][0]
    assert row['due_date']=='2027-01-15' and row['days_overdue']==-49
