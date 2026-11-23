"""Oversized PDFs must never quietly turn into partial bill imports."""
import asyncio
import io
from unittest.mock import patch

import pymupdf
from fastapi import UploadFile
import extract
import server


def pdf(pages):
    doc = pymupdf.open()
    for _ in range(pages):
        p = doc.new_page()
        p.insert_text((50, 50), 'Invoice No: INV-47\nBill To:\nAcme Traders\nTotal Amount: INR 5000.49\nDue Date: 2026-10-15\n' + 'Invoice details for goods delivered. ' * 5)
    result = doc.tobytes()
    doc.close()
    return result


def test_thirteen_page_text_pdf_rejects_before_any_extraction():
    with patch.object(extract, 'parse_invoice_text') as parse, patch.object(extract, 'extract_via_vision') as vision:
        result = asyncio.run(extract.extract_file('thirteen.pdf', pdf(13)))
    assert result['rows'] == []
    assert '13 pages' in result['note'] and '12 pages or fewer' in result['note']
    assert 'Nothing was imported from this PDF' in result['note']
    parse.assert_not_called()
    vision.assert_not_called()


def test_twelve_pages_still_reach_text_parser():
    row = {'customer': 'Acme', 'amount': 5000.49}
    with patch.object(extract, 'parse_invoice_text', return_value=row) as parse:
        result = asyncio.run(extract.extract_file('twelve.pdf', pdf(12)))
    assert len(result['rows']) == 1 and result['rows'][0]['amount'] == 5000.49
    parse.assert_called_once()


def test_thirteen_page_scan_rejects_even_when_vision_enabled():
    doc = pymupdf.open()
    for _ in range(13):
        doc.new_page()
    blob = doc.tobytes()
    doc.close()
    with patch.object(extract, 'vision_enabled', return_value=True), patch.object(extract, 'extract_via_vision') as vision:
        result = asyncio.run(extract.extract_file('scan.pdf', blob))
    assert result['rows'] == [] and '13 pages' in result['note']
    vision.assert_not_called()


def test_mixed_upload_keeps_valid_csv_and_reports_only_pdf_rejection():
    files = [UploadFile(filename='too-long.pdf', file=io.BytesIO(pdf(13))),
             UploadFile(filename='good.csv', file=io.BytesIO(b'Customer,Invoice No,Amount,Due Date\nAcme,I47,100.49,2026-10-15'))]
    result = asyncio.run(server.extract_files(files))
    assert len(result['rows']) == 1 and result['rows'][0]['amount'] == 100.49
    assert len(result['notes']) == 1 and 'too-long.pdf has 13 pages' in result['notes'][0]
    assert 'Nothing was imported from this PDF' in result['notes'][0]
