"""Customer-name extraction must never return a money fragment.

The label regex once matched the "to" inside "Total", so an invoice with no
bill-to block yielded customer="tal: Rs 1,86,500". Labels are whole words
now, and any candidate containing a currency amount is rejected.
"""
import extract


def test_total_line_fragment_is_not_a_customer():
    text = (
        "Bluepeak Logistics\n"
        "Invoice No: INV-2044\n"
        "Invoice Date: 2026-05-01\n"
        "Due Date: 05/06/2026\n"
        "Total: Rs 1,86,500\n"
        "Amount due: Rs 1,86,500\n"
        "Please pay by the due date above. Thank you for your business.\n"
    )
    got = extract.parse_invoice_text(text)
    assert "1,86,500" not in got["customer"] and "tal:" not in got["customer"], got
    # No bill-to block: the customer stays empty rather than offering the
    # seller's header line as a plausible-but-wrong debtor. The review step
    # requires the user to type the name.
    assert got["customer"] == "", got


def test_real_bill_to_still_wins_over_total_line():
    text = "TOTAL: Rs 5,000\nBill To: Acme Traders\nTotal: Rs 5,000"
    assert extract.parse_invoice_text(text)["customer"] == "Acme Traders"


def test_label_with_amount_capture_falls_through_to_next_line():
    text = "Bill To: Rs 5,000 only\nAcme Traders\nTotal: Rs 5,000"
    assert extract.parse_invoice_text(text)["customer"] == "Acme Traders"


def test_net_total_does_not_shadow_customer_label():
    text = "Net Total: Rs 1,000\nCustomer: Sharma Textiles"
    assert extract.parse_invoice_text(text)["customer"] == "Sharma Textiles"


def test_sold_to_multiline_still_matches():
    text = "Sold To:\nKapoor Garments LLP\nTotal 2,02,125"
    assert extract.parse_invoice_text(text)["customer"] == "Kapoor Garments LLP"


def test_no_label_means_no_customer():
    got = extract.parse_invoice_text("Acme Traders\nThank you for your business.\nTotal: Rs 500")
    assert got["customer"] == "", got


# Label ownership is load-bearing: these blocks do not name a billing party.
import pytest


@pytest.mark.parametrize("tail", [
    "Please remit to Bluepeak Logistics",
    "Ship To: Warehouse Nine\nPhone: +91 99887 66554",
    "Shipping To: Warehouse Nine\nEmail: dock@warehouse.test",
    "Remit To: Bluepeak Logistics\nPhone: +91 98110 12345",
    "Pay To: Bluepeak Logistics\nEmail: sales@bluepeak.test",
    "To: Warehouse Nine\nPhone: +91 99887 66554",
    "Delivery to Warehouse Nine\nEmail: dock@warehouse.test",
    "Customer support\nPhone: +91 98110 12345",
    "Buyer assistance\nEmail: sales@bluepeak.test",
    "Bill to be paid within 30 days\nPhone: +91 98110 12345",
    "For customer support\nPhone: +91 98110 12345",
    "Contact the buyer for details\nEmail: sales@bluepeak.test",
    "Please send this bill to Seller Corp\nPhone: +91 98110 12345",
    "Bill\nTo: Warehouse Nine\nPhone: +91 99887 66554",
])
def test_non_billing_party_labels_leave_debtor_and_contacts_blank(tail):
    row = extract.parse_invoice_text(
        "Bluepeak Logistics\nInvoice No: INV-9\nTotal: Rs 45000\n" + tail)
    assert row["customer"] == "", row
    assert row["email"] == "", row
    assert row["phone"] == "", row


@pytest.mark.parametrize("label", ["Bill To:", "Billed To:", "Buyer:", "Customer:", "Sold To:", "BillTo:"])
def test_explicit_billing_labels_still_capture_debtor_and_contact(label):
    row = extract.parse_invoice_text(
        "Ship To: Warehouse Nine\nPhone: +91 90000 11111\n"
        + label + " Acme Traders\nPhone: +91 99887 66554\nEmail: ap@acme.test")
    assert row["customer"] == "Acme Traders", row
    assert row["phone"] == "+91 99887 66554", row
    assert row["email"] == "ap@acme.test", row


def test_remittance_sentence_does_not_shadow_later_billing_party():
    row = extract.parse_invoice_text(
        "Please remit to Bluepeak Logistics\n"
        "Bill To:\nAcme Traders\nPhone: +91 99887 66554")
    assert row["customer"] == "Acme Traders", row
    assert row["phone"] == "+91 99887 66554", row


@pytest.mark.parametrize("label", ["Bill To", "Billed To", "Buyer", "Customer", "Sold To"])
def test_billing_label_own_line_is_supported(label):
    row = extract.parse_invoice_text(label + "\nAcme Traders\nEmail: ap@acme.test")
    assert row["customer"] == "Acme Traders", row
    assert row["email"] == "ap@acme.test", row


@pytest.mark.parametrize("tail", [
    "Bill To:\nTotal: Rs 45000\nShip To: Warehouse Nine\nPhone: +91 99887 66554",
    "Bill To:\nEmail: sales@seller.test\nRemit To: Seller Corp\nPhone: +91 98110 12345",
    "Bill To:\nEmail: sales@seller.test\nShip To: Warehouse Nine\nPhone: +91 99887 66554",
    "Bill To: Phone: +91 98110 12345\nBank: HDFC\nSeller Corp",
    "Bill To: Total: Rs 45000\nSeller Corp",
    "Bill To:\nEmail: sales@seller.test\nPlease remit payment to Seller Corp",
    "Bill To:\nEmail: sales@seller.test",
    "Bill To: Phone: +91 98110 12345",
    "Bill To: Call +91 98110 12345",
    "Bill To: Contact: sales@seller.test",
    "Bill To: E-mail: sales@seller.test",
])
def test_missing_billing_name_never_crosses_party_or_payment_boundary(tail):
    row = extract.parse_invoice_text("Invoice No: INV-99\nTotal: Rs 45000\n" + tail)
    assert row["customer"] == "", row
    assert row["email"] == "", row
    assert row["phone"] == "", row


def test_name_fallback_before_boundary_still_works():
    row = extract.parse_invoice_text(
        "Bill To: Email: ap@acme.test\nAcme Traders\nPhone: +91 99887 66554\n"
        "Ship To: Warehouse Nine\nEmail: dock@warehouse.test")
    assert row["customer"] == "Acme Traders", row
    assert row["email"] == "ap@acme.test", row
    assert row["phone"] == "+91 99887 66554", row


@pytest.mark.parametrize("name", [
    "Total Home Developers", "Total Environment", "Totalline Fabrics",
    "Price Waterhouse Coopers", "Acme Payment Services", "Acme Bank Services",
    "Account Services Limited", "Quantity Fabrics", "Description Studios",
    "Rate Solutions", "Item Works", "Due North Limited", "Tax Advisors",
    "GST Solutions", "Terms Consulting", "Invoice Systems", "Thank You Foods",
    "Note Studios", "Declaration Works", "Signature Textiles", "Authorized Services",
])
@pytest.mark.parametrize("separator", [" ", "\n"])
def test_billing_names_are_not_header_keywords(name, separator):
    row = extract.parse_invoice_text(
        "Bill To:" + separator + name + "\nEmail: ap@debtor.test")
    assert row["customer"] == name, row
    assert row["email"] == "ap@debtor.test", row


@pytest.mark.parametrize("party", ["Remit To: Seller Corp", "Ship To: Warehouse Nine", "Seller: Other Corp"])
def test_glued_party_header_is_not_billing_name(party):
    row = extract.parse_invoice_text("Bill To: " + party + "\nEmail: wrong@other.test")
    assert row["customer"] == "", row
    assert row["email"] == "", row


@pytest.mark.parametrize("party", [
    "Ship To Warehouse Nine", "Shipping To Warehouse Nine", "Ship-Warehouse Nine",
    "Sold To Other Corp", "Buyer Other Corp", "Seller Bluepeak Logistics",
    "From Bluepeak Logistics", "Customer Other Corp", "Bill To Other Corp",
    "Billed To Other Corp", "ShipTo Warehouse Nine",
])
@pytest.mark.parametrize("prefix", ["Bill To: ", "Bill To:\n", "Bill To:\nEmail: unknown@other.test\n"])
def test_undelimited_party_never_establishes_debtor(party, prefix):
    row = extract.parse_invoice_text(
        prefix + party + "\nEmail: ops@other.test\nPhone: +91 99887 66554")
    assert row["customer"] == "", row
    assert row["email"] == "", row
    assert row["phone"] == "", row


@pytest.mark.parametrize("name", [
    "Acme Seller Services", "Acme Customer Solutions", "Buyerly Textiles",
    "Sellerly Logistics", "Fromage Foods", "Bank of America Corp",
    "Discount Industries", "Balance Foods", "Paid Solutions", "Change Works",
])
@pytest.mark.parametrize("separator", [" ", "\n"])
def test_party_substrings_and_internal_words_remain_legal_names(name, separator):
    row = extract.parse_invoice_text("Bill To:" + separator + name + "\nEmail: ap@debtor.test")
    assert row["customer"] == name, row
    assert row["email"] == "ap@debtor.test", row


@pytest.mark.parametrize("name", ["From You Flowers", "Customer First Bank", "Seller Services Ltd"])
@pytest.mark.parametrize("separator", [" ", "\n"])
def test_ambiguous_leading_party_names_are_conservatively_unknown(name, separator):
    row = extract.parse_invoice_text("Bill To:" + separator + name + "\nEmail: ap@debtor.test")
    assert row["customer"] == "", row
    assert row["email"] == "", row


@pytest.mark.parametrize("text", [
    "Bill To: Acme Traders\nTotal: Rs 5000",
    "Bill To:\n              Bluepeak Logistics\nEmail: sales@seller.test\nTotal: Rs 5000",
    "Bill To:\nShip To Warehouse Nine\nTotal: Rs 5000",
])
def test_document_recipient_remains_provisional_even_when_name_missing(text):
    row = extract.parse_invoice_text(text)
    assert row["recipient_review_required"] is True
    assert row["recipient_unconfirmed"] is True


def test_csv_recipient_does_not_gain_document_confirmation_gate():
    import asyncio
    result = asyncio.run(extract.extract_file("bills.csv", b"customer,bill_no,amount,due_date\nAcme,INV-1,5000,2026-10-15"))
    assert result["rows"]
    assert not result["rows"][0].get("recipient_unconfirmed")



def test_pdf_upload_flags_recipient_for_review():
    import asyncio
    import pymupdf
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Synthetic invoice\nInvoice No: INV-C30\nInvoice Date: 2026-10-01\nDue Date: 2026-10-15\nTotal: Rs 45000\nBill To:\n              Bluepeak Logistics\nEmail: sales@seller.test")
    result = asyncio.run(extract.extract_file("bill.pdf", doc.tobytes()))
    row = result["rows"][0]
    assert row["customer"] == "Bluepeak Logistics"
    assert row["source"] == "bill.pdf"
    assert row["recipient_unconfirmed"] is True
    assert row["recipient_review_required"] is True
    assert row["amount"] == 45000


def test_vision_recipient_is_also_provisional(monkeypatch):
    import asyncio
    class Response:
        def raise_for_status(self):
            pass
        def json(self):
            return {"choices": [{"message": {"content": '{"invoices":[{"customer":"Acme","amount":5000}]}'}}]}
    class Client:
        def __init__(self, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, *args, **kwargs):
            return Response()
    monkeypatch.setenv("LLM_API_KEY", "synthetic-test-only")
    monkeypatch.setattr(extract.httpx, "AsyncClient", Client)
    rows = asyncio.run(extract.extract_via_vision([b"synthetic-not-an-image"]))
    assert rows[0]["recipient_unconfirmed"] is True
    assert rows[0]["recipient_review_required"] is True
