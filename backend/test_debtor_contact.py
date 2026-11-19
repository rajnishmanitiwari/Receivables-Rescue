"""Debtor contact details come only from the bill-to block.

The first email/phone in an invoice is usually the SELLER's own header or
footer contact. Passing it to the debtor row puts the seller's number into
chase links: a wrong-recipient defect worse than a blank field. Unknown
contacts stay blank.
"""
import extract


def test_seller_header_contact_stays_blank():
    row = extract.parse_invoice_text(
        "Bluepeak Logistics\nPhone: +91 98110 12345\nEmail: sales@bluepeak.test\n"
        "Invoice No: INV-9\nDate: 01/10/2026\nTotal: Rs 45,000\n"
        "Bill To: Acme Traders\n456 Buyer Lane\nMumbai"
    )
    assert row["customer"] == "Acme Traders"
    assert row["phone"] == "", row
    assert row["email"] == "", row


def test_contact_inside_billto_block_is_captured():
    row = extract.parse_invoice_text(
        "Bluepeak Logistics\nPhone: +91 98110 12345\n"
        "Invoice No: INV-9\nDate: 01/10/2026\nTotal: Rs 45,000\n"
        "Bill To: Acme Traders\n456 Buyer Lane\nEmail: ap@acme.test\nPhone: +91 99887 66554"
    )
    assert row["customer"] == "Acme Traders"
    assert row["email"] == "ap@acme.test"
    assert "99887" in row["phone"]


def test_no_billto_means_no_contact():
    row = extract.parse_invoice_text(
        "Bluepeak Logistics\nPhone: +91 98110 12345\nEmail: sales@bluepeak.test\n"
        "Invoice No: INV-9\nDate: 01/10/2026\nTotal: Rs 45,000"
    )
    assert row["customer"] == ""
    assert row["phone"] == ""
    assert row["email"] == ""


def test_seller_footer_contact_stays_blank():
    # Contact block at the bottom of the document, far from the bill-to.
    row = extract.parse_invoice_text(
        "Bluepeak Logistics\nInvoice No: INV-9\nDate: 01/10/2026\nTotal: Rs 45,000\n"
        "Bill To: Acme Traders\n456 Buyer Lane\nMumbai\n\n\n\n\n\n\n"
        "Contact us: sales@bluepeak.test, +91 98110 12345"
    )
    assert row["customer"] == "Acme Traders"
    assert row["phone"] == "", row
    assert row["email"] == "", row


BASE = "Invoice No: INV-9\nDate: 01/10/2026\nTotal: Rs 45,000\n"


def test_remittance_email_not_debtor_contact():
    row = extract.parse_invoice_text(
        "Bluepeak Logistics\n" + BASE +
        "Bill To: Acme Traders\n456 Buyer Lane\n"
        "Remit To: accounts@bluepeak.test\nBank: HDFC")
    assert row["email"] == ""
    assert row["phone"] == ""


def test_seller_query_phone_not_debtor_contact():
    row = extract.parse_invoice_text(
        "Bluepeak Logistics\n" + BASE +
        "Bill To: Acme Traders\n456 Buyer Lane\n"
        "Queries? Call us on +91 98110 12345")
    # "Queries" is a boundary and the number follows the seller's "us".
    assert row["phone"] == "", row


def test_shipto_contact_not_debtor_contact():
    row = extract.parse_invoice_text(
        "Bluepeak Logistics\n" + BASE +
        "Bill To: Acme Traders\n456 Buyer Lane\n"
        "Ship To: Warehouse 9\nEmail: dock@warehouse.test\nPhone: +91 90000 11111")
    assert row["email"] == ""
    assert row["phone"] == ""


def test_second_billto_closes_first_block():
    row = extract.parse_invoice_text(
        "Bluepeak Logistics\n" + BASE +
        "Bill To: Acme Traders\n"
        "Bill To: Other Corp\nEmail: ops@othercorp.test")
    assert row["email"] == "", row


def test_bank_account_digits_never_become_phone():
    row = extract.parse_invoice_text(
        "Bluepeak Logistics\n" + BASE +
        "Bill To: Acme Traders\n456 Buyer Lane\n"
        "Bank: HDFC\nAccount No: 50100234567890\nIFSC: HDFC0001")
    assert row["phone"] == "", row


def test_unlabeled_digits_in_block_stay_blank():
    row = extract.parse_invoice_text(
        "Bluepeak Logistics\n" + BASE +
        "Bill To: Acme Traders\n456 Buyer Lane 400001\n99887 66554")
    assert row["phone"] == "", row


def test_labeled_debtor_phone_in_block_captured():
    row = extract.parse_invoice_text(
        "Bluepeak Logistics\nPhone: +91 98110 12345\n" + BASE +
        "Bill To: Acme Traders\n456 Buyer Lane\nPhone: +91 99887 66554")
    assert "99887" in row["phone"]


def test_trailing_email_on_billto_line_not_in_customer_name():
    row = extract.parse_invoice_text(
        "Bluepeak Logistics\n" + BASE +
        "Bill To: Acme Traders ap@acme.test")
    assert row["customer"] == "Acme Traders", row
    # A bare email is proximity, not attribution: without a contact label it
    # stays blank rather than risk chasing the wrong inbox.
    assert row["email"] == ""


def test_trailing_phone_on_billto_line_not_in_customer_name():
    row = extract.parse_invoice_text(
        "Bluepeak Logistics\n" + BASE +
        "Bill To: Acme Traders +91 99887 66554")
    assert row["customer"] == "Acme Traders", row
    assert row["phone"] == ""


def test_sentence_prefix_seller_query_line_is_boundary():
    # Strong seller markers end the block wherever they appear in the line.
    row = extract.parse_invoice_text(
        "Bluepeak Logistics\n" + BASE +
        "Bill To: Acme Traders\n456 Buyer Lane\n"
        "For queries call us on +91 98110 12345")
    assert row["phone"] == "", row
    row = extract.parse_invoice_text(
        "Bluepeak Logistics\n" + BASE +
        "Bill To: Acme Traders\n456 Buyer Lane\n"
        "If you have any questions contact us at sales@bluepeak.test")
    assert row["email"] == "", row
    row = extract.parse_invoice_text(
        "Bluepeak Logistics\n" + BASE +
        "Bill To: Acme Traders\n456 Buyer Lane\n"
        "Please remit payment to accounts@bluepeak.test")
    assert row["email"] == "", row


def test_weak_words_midline_do_not_close_block():
    # Weak boundary words only count at line start, so address lines that
    # contain them mid-line do not cost the debtor's labeled contact.
    row = extract.parse_invoice_text(
        "Bluepeak Logistics\n" + BASE +
        "Bill To: Acme Traders\nNear Total Home Developers, 12 Due Lane\n"
        "Email: ap@acme.test\nPhone: +91 99887 66554")
    assert row["email"] == "ap@acme.test", row
    assert "99887" in row["phone"]


# --- Independent reviewer's exact probe fixtures (relayed verbatim via Main) ---
REVIEWER_PREFIX = (
    "Bluepeak Logistics\nPhone: +91 98110 12345\nEmail: sales@bluepeak.test\n"
    "Invoice No: INV-9\nDate: 01/10/2026\nTotal: Rs 45,000\n"
)


def _reviewer_row(tail):
    return extract.parse_invoice_text(REVIEWER_PREFIX + tail)


def test_reviewer_fixture_1_for_queries_call():
    row = _reviewer_row("Bill To: Acme Traders\n456 Buyer Lane\nFor queries call +91 98110 12345")
    assert row["customer"] == "Acme Traders"
    assert row["phone"] == "", row
    assert row["email"] == "", row


def test_reviewer_fixture_2_for_any_queries_contact():
    row = _reviewer_row("Bill To: Acme Traders\n456 Buyer Lane\nFor any queries contact sales@bluepeak.test")
    assert row["email"] == "", row
    assert row["phone"] == "", row


def test_reviewer_fixture_3_please_contact_us():
    row = _reviewer_row("Bill To: Acme Traders\n456 Buyer Lane\nPlease contact us at +91 98110 12345")
    assert row["phone"] == "", row
    assert row["email"] == "", row


def test_reviewer_fixture_4_kindly_remit_payment():
    row = _reviewer_row("Bill To: Acme Traders\n456 Buyer Lane\nKindly remit payment to accounts@bluepeak.test")
    assert row["email"] == "", row
    assert row["phone"] == "", row


def test_reviewer_remittance_bank_block_blank():
    row = _reviewer_row(
        "Bill To: Acme Traders\nRemittance: email accounts@bluepeak.test\n"
        "Bank: HDFC 50200012345678\nIFSC: HDFC0001234")
    assert row["email"] == "", row
    assert row["phone"] == "", row


def test_two_column_glued_seller_contact_not_captured():
    # Two-column PDF text glues the seller column after a wide gap.
    row = extract.parse_invoice_text(
        "Bluepeak Logistics\nInvoice No: INV-9\nDate: 01/10/2026\nTotal: Rs 45,000\n"
        "Bill To: Acme Traders        Phone: +91 98110 12345\n"
        "456 Buyer Lane               Email: sales@bluepeak.test")
    assert row["customer"] == "Acme Traders", row
    assert row["phone"] == "", row
    assert row["email"] == "", row


def test_bank_digits_near_contact_word_never_phone():
    # A labeled 13-digit bank account number is still not a phone.
    row = _reviewer_row("Bill To: Acme Traders\n456 Buyer Lane\nContact: 5020001234567")
    assert row["phone"] == "", row
    row = _reviewer_row("Bill To: Acme Traders\n456 Buyer Lane\nCall 50200012345678 for details")
    assert row["phone"] == "", row


def test_phone_normalisation_variants():
    row = _reviewer_row("Bill To: Acme Traders\nPhone: 99887 66554")
    assert row["phone"] == "99887 66554"
    row = _reviewer_row("Bill To: Acme Traders\nPhone: +91 99887 66554")
    assert "99887" in row["phone"]
    row = _reviewer_row("Bill To: Acme Traders\nPhone: 02223456789")
    assert row["phone"] == "02223456789"  # compact 0-prefixed form only; see natural-format test
    row = _reviewer_row("Bill To: Acme Traders\nPhone: 12345 67890")
    assert row["phone"] == ""  # 10 digits but not a plausible subscriber range


def test_label_only_billto_with_name_next_line():
    row = _reviewer_row("Bill To:\nAcme Traders\n456 Buyer Lane\nEmail: ap@acme.test")
    assert row["customer"] == "Acme Traders", row
    assert row["email"] == "ap@acme.test"


def test_glued_second_party_no_chase_recipient():
    row = extract.parse_invoice_text(
        "Bluepeak Logistics\nInvoice No: INV-9\nDate: 01/10/2026\nTotal: Rs 45,000\n"
        "Bill To: Acme Traders        Other Corp\n"
        "456 Buyer Lane               Phone: +91 90000 11111")
    assert row["customer"] == "Acme Traders", row
    assert row["phone"] == "", row
    assert row["email"] == "", row


def test_reviewer_r1_two_space_gutter_blank():
    # Independent reviewer's R1 residual, verbatim: a two-column gutter of
    # exactly two spaces sits below the wide-gap cut, so the seller column
    # stays glued to the debtor address line. A label that does not start
    # the line is ambiguous and must not become a chase recipient.
    row = _reviewer_row("Bill To: Acme Traders\n456 Buyer Lane  Phone: +91 98110 12345")
    assert row["customer"] == "Acme Traders", row
    assert row["phone"] == "", row
    assert row["email"] == "", row
    row = _reviewer_row("Bill To: Acme Traders\n456 Buyer Lane  Email: sales@bluepeak.test")
    assert row["email"] == "", row
    assert row["phone"] == "", row


def test_two_space_gutter_on_billto_line_blank():
    # Same narrow gutter glued onto the bill-to label line itself. The
    # seller's contact must not become a chase recipient; a leftover label
    # word in the cleaned name is a known cosmetic artifact, not a recipient
    # risk, and the chase fields stay blank.
    row = _reviewer_row("Bill To: Acme Traders  Phone: +91 98110 12345")
    assert row["phone"] == "", row
    assert row["email"] == "", row
    assert "98110" not in row["customer"], row
    row = _reviewer_row("Bill To: Acme Traders  Email: sales@bluepeak.test")
    assert row["email"] == "", row
    assert row["phone"] == "", row
    assert "bluepeak" not in row["customer"], row


def test_midline_label_in_zone_stays_blank():
    # The line-start label rule is uniform inside the zone, not only about
    # gutters: a label following address text is ambiguous and stays blank.
    row = _reviewer_row("Bill To: Acme Traders\n456 Buyer Lane Phone: +91 99887 66554")
    assert row["phone"] == "", row


def test_natural_landline_formats_blank():
    # Documented limitation: only the compact 11-digit 0-prefixed form is
    # captured; naturally formatted landlines match nothing and stay blank.
    # Fail-safe (editable in review), not wrong-recipient.
    row = _reviewer_row("Bill To: Acme Traders\nPhone: 0141-2301234")
    assert row["phone"] == "", row
    row = _reviewer_row("Bill To: Acme Traders\nPhone: 080 4567 1234")
    assert row["phone"] == "", row
    row = _reviewer_row("Bill To: Acme Traders\nPhone: +91 141 230 1234")
    assert row["phone"] == "", row
    row = _reviewer_row("Bill To: Acme Traders\nPhone: 02223456789")
    assert row["phone"] == "02223456789", row


def test_strong_token_midline_blanks_later_contacts():
    # Documented fail-safe limitation (independent reviewer's R2): a strong
    # seller/payment token mid-line ends the zone, so a legit labeled debtor
    # contact below an address like "12 Bank Street" is lost. Blank, never
    # wrong; improving this needs address-aware zone handling later.
    row = _reviewer_row("Bill To: Acme Traders\n12 Bank Street, Jaipur\nEmail: ap@acme.test")
    assert row["customer"] == "Acme Traders", row
    assert row["email"] == "", row
