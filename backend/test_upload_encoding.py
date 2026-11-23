"""Uploaded text must not lose undecodable bytes in financial identities/values."""
import asyncio
import io
from unittest.mock import patch

from fastapi import UploadFile
import extract
import server

HEADER = b'Customer,Invoice No,Amount,Due Date\n'


def read(blob, filename='bills.csv'):
    return asyncio.run(extract.extract_file(filename, blob))


def test_invalid_bytes_reject_before_parser_for_every_text_extension():
    for filename in ['bills.csv', 'bills.tsv', 'bills.txt']:
        for bad_row in [b'Acm\xffe,I1,5000.49,2026-10-15',
                        b'Acme,I\xff1,5000.49,2026-10-15',
                        b'Acme,I1,50\xff00.49,2026-10-15']:
            with patch.object(extract.engine, 'parse_invoices') as parse:
                result = read(HEADER + bad_row, filename)
            assert result['rows'] == []
            assert 'Nothing was imported from this file' in result['note']
            assert 'UTF-8' in result['note']
            assert 'Acme' not in result['note'] and '5000' not in result['note']
            parse.assert_not_called()


def test_utf8_with_and_without_bom_preserves_identities_and_paise():
    text = 'Customer,Invoice No,Amount,Due Date\nCafé व्यापारी,I-₹47,5000.49,2026-10-15'
    for encoding in ['utf-8', 'utf-8-sig']:
        result = read(text.encode(encoding))
        assert len(result['rows']) == 1
        row = result['rows'][0]
        assert row['customer'] == 'Café व्यापारी' and row['invoice_no'] == 'I-₹47'
        assert row['amount'] == 5000.49 and row['due_date'] == '2026-10-15'


def test_utf16_is_not_guessed_or_partially_imported():
    result = read((HEADER.decode() + 'Acme,I1,5000.49,2026-10-15').encode('utf-16'))
    assert result['rows'] == [] and 'UTF-8' in result['note']


def test_mixed_batch_reports_bad_file_without_discarding_good_csv():
    files = [UploadFile(filename='bad.csv', file=io.BytesIO(HEADER + b'Acm\xffe,I1,5000.49,2026-10-15')),
             UploadFile(filename='good.csv', file=io.BytesIO(HEADER + b'Valid,I2,100.49,2026-10-15'))]
    result = asyncio.run(server.extract_files(files))
    assert len(result['rows']) == 1 and result['rows'][0]['customer'] == 'Valid'
    assert result['rows'][0]['amount'] == 100.49
    assert len(result['notes']) == 1 and result['notes'][0].startswith('bad.csv:')
