"""Zero-rounded balances must not become zero-value bills or chase drafts."""
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

@pytest.mark.parametrize('delimiter',[',','\t',';','|'])
@pytest.mark.parametrize('raw',['0.001','0.004','0.000001','₹0.004'])
@pytest.mark.parametrize('mixed',[False,True])
def test_zero_rounded_balance_unusable_in_extract_and_analysis(delimiter,raw,mixed):
    out=io.StringIO();writer=csv.writer(out,delimiter=delimiter)
    writer.writerow(['Customer','Invoice No','Amount','Due Date'])
    writer.writerow(['Tiny','X64',raw,'2026-10-15'])
    if mixed:writer.writerow(['Valid','I64','300.49','2026-10-15'])
    with TestClient(server.app) as client:
        extracted=client.post('/api/extract',files=[('files',('tiny.csv',out.getvalue(),'text/csv'))])
        analysed=client.post('/api/analyse',json={'data':out.getvalue()})
    assert extracted.status_code==200
    assert len(extracted.json()['rows'])==(1 if mixed else 0)
    if mixed:
        assert extracted.json()['rows'][0]['customer']=='Valid'
        assert analysed.status_code==200
        report=analysed.json()['report']
        assert report['invoice_count']==1 and report['total_outstanding']==300.49
        assert [m['customer'] for m in analysed.json()['messages']]==['Valid']
    else:
        assert analysed.status_code==422 and 'report' not in analysed.json()

@pytest.mark.parametrize('raw,want',[('0.005',0.01),('0.009',0.01),('0.01',0.01),('100.495',100.5),('5000.49',5000.49)])
def test_positive_rounded_balances_keep_existing_rounding(raw,want):
    rows,_=engine.parse_invoices('Customer,Invoice No,Amount,Due Date\nAcme,I64,'+raw+',2026-10-15')
    assert rows[0].amount==want


def test_zero_rounded_row_does_not_conflict_with_valid_same_bill():
    rows,warnings=engine.parse_invoices('Customer,Invoice No,Amount,Due Date\nAcme,I64,0.001,2026-10-15\nAcme,I64,5000.49,2026-10-15')
    assert len(rows)==1 and rows[0].amount==5000.49
    assert any('Skipped 1' in w for w in warnings)
    assert not any('conflicting' in w for w in warnings)
