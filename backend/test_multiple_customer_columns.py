"""Two named parties require a debtor choice, never silent first-column use."""
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

def table(headers, delimiter=',', second='Buyer Co'):
    out=io.StringIO(); writer=csv.writer(out,delimiter=delimiter)
    writer.writerow(['Invoice No','Amount','Due Date',*headers])
    writer.writerow(['I63','5000.49','2026-10-15','Seller Co',second])
    return out.getvalue()

@pytest.mark.parametrize('delimiter',[',','\t',';','|'])
@pytest.mark.parametrize('headers',[
    ['Customer','Bill To'],['Bill To','Customer'],['Customer','Customer'],
    ['Client Name','Buyer'],['Party','Debtor']])
def test_multiple_exact_customer_aliases_reject_in_extract_and_analysis(delimiter,headers):
    text=table(headers,delimiter)
    with pytest.raises(engine.ParseError,match='More than one customer column'):
        engine.parse_invoices(text)
    with TestClient(server.app) as client:
        extracted=client.post('/api/extract',files=[('files',('parties.csv',text,'text/csv'))])
        analysed=client.post('/api/analyse',json={'data':text})
    assert extracted.status_code==200 and extracted.json()['rows']==[]
    assert 'parties.csv:' in extracted.json()['notes'][0]
    assert 'No rows from this input' in extracted.json()['notes'][0]
    assert analysed.status_code==422 and 'report' not in analysed.json()

@pytest.mark.parametrize('second',['Seller Co',''])
def test_repeated_columns_need_choice_even_when_equal_or_blank(second):
    with pytest.raises(engine.ParseError,match='More than one customer column'):
        engine.parse_invoices(table(['Customer','Buyer'],second=second))

@pytest.mark.parametrize('header',engine._HEADER_ALIASES['customer'])
def test_one_customer_alias_with_contacts_still_works(header):
    text='Invoice No,Amount,Due Date,'+header+',Email,Phone\nI63,5000.49,2026-10-15,Buyer Co,ap@buyer.test,9876543210'
    rows,_=engine.parse_invoices(text)
    assert rows[0].customer=='Buyer Co' and rows[0].email=='ap@buyer.test' and rows[0].phone=='9876543210'


def test_mixed_upload_preserves_valid_file_and_explicit_recipient_correction():
    bad=table(['Customer','Bill To'])
    good='Customer,Invoice No,Amount,Due Date\nValid,G63,300.49,2026-10-15'
    with TestClient(server.app) as client:
        extracted=client.post('/api/extract',files=[('files',('bad.csv',bad,'text/csv')),('files',('good.csv',good,'text/csv'))])
        corrected=client.post('/api/analyse',json={'data':'Customer,Invoice No,Amount,Due Date\nBuyer Co,I63,5000.49,2026-10-15','today':'2026-11-27'})
    result=extracted.json()
    assert len(result['rows'])==1 and result['rows'][0]['amount']==300.49
    assert len(result['notes'])==1 and result['notes'][0].startswith('bad.csv:')
    assert corrected.status_code==200
    row=corrected.json()['report']['priority'][0]
    assert row['customer']=='Buyer Co' and row['amount']==5000.49
    assert [m['customer'] for m in corrected.json()['messages']]==['Buyer Co']
    assert all('Seller Co' not in m['email'] for m in corrected.json()['messages'])
