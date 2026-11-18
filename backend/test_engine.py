from datetime import date, timedelta
import engine, extract, messages as msg

TODAY = date(2026, 8, 27)


def d(days_ago):
    return (TODAY - timedelta(days=days_ago)).isoformat()


def test_header_csv():
    csv_text = (
        "Customer Name,Invoice No,Amount,Due Date,Email,Phone\n"
        f"Acme Traders,INV-101,\"1,25,000\",{d(120)},ap@acme.test,+919812345678\n"
        f"Bluepeak Ltd,INV-102,45000.50,{d(20)},,\n"
        f"Corex,INV-103,9000,{d(-10)},c@corex.test,\n"
    )
    inv, warn = engine.parse_invoices(csv_text, today=TODAY)
    assert len(inv) == 3, inv
    assert inv[0].amount == 125000.0, inv[0].amount
    assert inv[0].email == "ap@acme.test"
    r = engine.analyse(inv, today=TODAY)
    assert r["invoice_count"] == 3
    assert abs(r["total_outstanding"] - 179000.50) < 0.01, r["total_outstanding"]
    assert r["overdue_count"] == 2
    # Ranked by cost of waiting, not by age: the mid-age invoice above the
    # 90-day cliff should beat the not-yet-due one, which must rank last.
    assert r["priority"][-1]["customer"] == "Corex", r["priority"][-1]
    assert all(p["slip_30d"] >= 0 for p in r["priority"])
    assert r["cost_of_waiting_30d"] > 0
    assert r["expected_recoverable"] < r["total_outstanding"]
    return r


def test_no_header_positional():
    text = f"Acme,INV-1,50000,{d(200)}\nBeta,INV-2,20000,{d(5)}\n"
    inv, warn = engine.parse_invoices(text, today=TODAY)
    assert len(inv) == 2
    assert any("No header" in w for w in warn)
    r = engine.analyse(inv, today=TODAY)
    slips = [p["slip_30d"] for p in r["priority"]]
    assert slips == sorted(slips, reverse=True), slips


def test_tsv_and_semicolon_and_us_dates():
    text = "Customer;Amount;Due Date\nZed Corp;$12,500.75;06/12/2026\n"
    inv, _ = engine.parse_invoices(text, today=TODAY)
    assert abs(inv[0].amount - 12500.75) < 0.01, inv[0].amount
    assert inv[0].due_date is not None


def test_missing_dates_and_bad_rows():
    text = "Customer,Amount,Due Date\nA,,2026-01-01\nB,1000,\nC,abc,2026-01-01\n"
    inv, warn = engine.parse_invoices(text, today=TODAY)
    assert len(inv) == 1 and inv[0].customer == "B"
    assert any("no readable due date" in w for w in warn)


def test_empty_raises():
    for bad in ("", "   ", "Customer,Amount\n"):
        try:
            engine.parse_invoices(bad, today=TODAY)
        except engine.ParseError:
            continue
        raise AssertionError(f"should have raised for {bad!r}")


def test_probability_monotonic():
    prev = 2.0
    for days in range(-30, 500, 7):
        p = engine.recovery_probability(days)
        assert p <= prev + 1e-9, (days, p, prev)
        prev = p


def test_concentration_and_risks():
    text = "Customer,Amount,Due Date\n" + f"Whale Inc,900000,{d(100)}\n" + f"Small,10000,{d(2)}\n"
    inv, _ = engine.parse_invoices(text, today=TODAY)
    r = engine.analyse(inv, today=TODAY)
    assert r["concentration_top_customer"] > 40
    assert any("Whale Inc" in x for x in r["risks"])
    assert any("90 days" in x for x in r["risks"])


def test_messages_tiers_and_formatting():
    text = (
        "Customer,Invoice No,Amount,Due Date\n"
        f"A,INV-1,100000,{d(200)}\nB,INV-2,50000,{d(60)}\n"
        f"C,INV-3,25000,{d(25)}\nD,INV-4,5000,{d(-5)}\n"
    )
    inv, _ = engine.parse_invoices(text, today=TODAY)
    r = engine.analyse(inv, today=TODAY)
    m = msg.build_messages(r["priority"], sender="Damini", company="Nyneso", currency="INR")
    tiers = {x["customer"]: x["tier"] for x in m}
    assert tiers["A"] == "final" and tiers["B"] == "escalation"
    assert tiers["C"] == "firm" and tiers["D"] == "reminder"
    for x in m:
        assert "Damini" in x["email"] and len(x["whatsapp"]) < 400
        assert x["subject"]
    assert msg.fmt_money(1234567, "INR") == "₹12,34,567", msg.fmt_money(1234567, "INR")
    assert msg.fmt_money(5000, "USD") == "$5,000"


def test_extract_text_invoice_formats():
    cases = [
        ("""TAX INVOICE
Sharma Textiles Pvt Ltd
GSTIN: 27AABCS1234F1Z5
Invoice No: ST/2026/0417
Invoice Date: 12 May 2026
Due Date: 26 June 2026
Bill To:
Kapoor Garments LLP
accounts@kapoor.example
+91 98200 11223
TOTAL 2,02,125""",
         dict(customer="Kapoor Garments LLP", invoice_no="ST/2026/0417",
              amount=202125.0, due_date="2026-06-26")),
        ("""INVOICE #A-99120
Date: 03/14/2026
Terms: Net 30
Bill To: Northwind Design Studio
Grand Total: $4,536.00""",
         dict(customer="Northwind Design Studio", invoice_no="A-99120",
              amount=4536.0, due_date="2026-04-13")),
        ("""Bill No : KT/24-25/881
Dated 05-01-2026
Buyer: Verma Hardware Stores
Total Amount Payable Rs. 87,450/-""",
         dict(customer="Verma Hardware Stores", invoice_no="KT/24-25/881",
              amount=87450.0, due_date="2026-02-19")),
    ]
    for text, want in cases:
        got = extract.parse_invoice_text(text)
        for k, v in want.items():
            assert got[k] == v, f"{k}: got {got[k]!r} want {v!r}\n{got}"
        assert got["confidence"] == "high"


def test_extract_ignores_junk():
    got = extract.parse_invoice_text("Thank you for your business. See you soon.")
    assert got["amount"] is None and got["confidence"] == "low"
    assert extract.parse_invoice_text("")["amount"] is None


def test_extract_does_not_read_heading_as_invoice_number():
    # "TAX INVOICE\nAcme Ltd" must not yield invoice_no="Acme"
    got = extract.parse_invoice_text("TAX INVOICE\nAcme Ltd\nTotal 5000")
    assert got["invoice_no"] == "", got


def test_msmed_interest():
    # 5,00,000 late by 150 days at a 5.5% bank rate -> 16.5% p.a., monthly rests
    v = engine.msmed_interest(500000, 150, 5.50)
    assert abs(v - 34808.25) < 1.0, v
    assert engine.msmed_interest(500000, 0, 5.50) == 0.0
    assert engine.msmed_interest(500000, -30, 5.50) == 0.0
    assert engine.msmed_interest(500000, 150, 0) == 0.0
    # monotonic in time
    prev = -1
    for d in range(0, 400, 20):
        cur = engine.msmed_interest(100000, d, 5.50)
        assert cur >= prev, (d, cur, prev)
        prev = cur


def test_no_statutory_clause_in_sendable_text():
    text = ("Customer,Invoice No,Amount,Due Date\n"
            f"Old Debt,INV-1,500000,{d(150)}\n"
            f"Fresh,INV-2,20000,{d(8)}\n"
            f"Tiny,INV-3,300,{d(200)}\n")
    inv, _ = engine.parse_invoices(text, today=TODAY)
    r = engine.analyse(inv, today=TODAY, bank_rate=5.50)
    # arithmetic stays an estimate on the report, but no statutory or legal
    # assertion may reach a sendable message while eligibility is unverified
    assert r["statutory_interest_total"] > 0
    m = msg.build_messages(r["priority"], sender="D", company="N")
    for x in m:
        for field in ("email", "whatsapp", "subject"):
            assert "MSMED" not in x[field]
            assert "Samadhaan" not in x[field]
            assert "Section 16" not in x[field]
    # sign-off must stay last in both channels
    old = {x["customer"]: x for x in m}["Old Debt"]
    assert old["email"].rstrip().endswith("N")
    assert old["whatsapp"].rstrip().endswith("D, N")


if __name__ == "__main__":
    fns = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    r = test_header_csv()
    print("\n--- sample report ---")
    print("outstanding      ", r["total_outstanding"])
    print("expected recover ", r["expected_recoverable"])
    print("cost of waiting  ", r["cost_of_waiting_30d"])
    print("buckets          ", [(b["bucket"], b["amount"]) for b in r["buckets"]])
    print(f"\n{len(fns)} tests passed")
