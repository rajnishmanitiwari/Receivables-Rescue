"""Numeric operator expressions must not become concatenated money."""
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


@pytest.mark.parametrize('raw', ['100+200', '100 + 200', '100/2', '100 / 2', '100*2', '100×2', '100÷2', '₹100 + 200', '100 + -200'])
def test_operator_expression_rejected(raw):
    assert engine.parse_amount(raw) is None


@pytest.mark.parametrize('raw,want', [('+100.49',100.49), ('AED 100.49',100.49), ('EUR 100.49',100.49), ('₹5,000.49',5000.49), ('−5000.49',-5000.49), ('5.000,49',5000.49)])
def test_supported_formats_unchanged(raw,want):
    assert engine.parse_amount(raw) == want


@pytest.mark.parametrize('delimiter', [',','\t',';','|'])
@pytest.mark.parametrize('mixed', [False,True])
def test_operator_extract_analysis_never_joins_operands(delimiter,mixed):
    out=io.StringIO(); writer=csv.writer(out,delimiter=delimiter)
    writer.writerow(['Customer','Invoice No','Amount','Due Date'])
    writer.writerow(['Expression','X59','100+200','2026-10-15'])
    if mixed:
        writer.writerow(['Valid','I59','100.49','2026-10-15'])
    with TestClient(server.app) as client:
        extracted=client.post('/api/extract',files=[('files',('operator.csv',out.getvalue(),'text/csv'))])
        analysed=client.post('/api/analyse',json={'data':out.getvalue()})
    assert extracted.status_code==200
    rows=extracted.json()['rows']
    assert len(rows)==(1 if mixed else 0)
    if mixed:
        assert rows[0]['customer']=='Valid' and rows[0]['amount']==100.49
        assert analysed.status_code==200 and analysed.json()['report']['total_outstanding']==100.49
        assert all(m['customer']!='Expression' for m in analysed.json()['messages'])
    else:
        assert analysed.status_code==422 and 'report' not in analysed.json()
