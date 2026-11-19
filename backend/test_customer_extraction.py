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
