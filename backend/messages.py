"""
Escalating follow-up generator.

Works with zero API keys (deterministic templates below). If an LLM key is
configured, backend/llm.py rewrites the same messages in the user's chosen
tone/language — the app never depends on that being available.
"""
from __future__ import annotations

from typing import Any

CURRENCY_SYMBOLS = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£", "AED": "AED "}


def fmt_money(amount: float, currency: str = "INR") -> str:
    sym = CURRENCY_SYMBOLS.get(currency, currency + " ")
    if currency == "INR":
        # Indian grouping: 12,34,567
        whole = f"{int(round(amount)):d}"
        neg = whole.startswith("-")
        whole = whole.lstrip("-")
        if len(whole) > 3:
            head, tail = whole[:-3], whole[-3:]
            parts = []
            while len(head) > 2:
                parts.insert(0, head[-2:])
                head = head[:-2]
            if head:
                parts.insert(0, head)
            whole = ",".join(parts) + "," + tail
        return ("-" if neg else "") + sym + whole
    return f"{sym}{amount:,.0f}"


TIER_LABELS = {
    "reminder": "Polite reminder",
    "firm": "Firm follow-up",
    "escalation": "Escalation",
    "final": "Final notice before recovery",
}

TIER_GUIDANCE = {
    "reminder": "Assume it is an oversight. Give them a one-click way to pay.",
    "firm": "Name the date, name the amount, ask for a committed payment date.",
    "escalation": "Move it up a level. Copy their finance lead and pause new work.",
    "final": "State consequences plainly and give a hard deadline. Then follow through.",
}


def _subject(tier: str, inv: dict[str, Any], currency: str) -> str:
    ref = inv.get("invoice_no") or "your invoice"
    amt = fmt_money(inv["amount"], currency)
    days = inv["days_overdue"]
    return {
        "reminder": f"{ref} — {amt} due{' in ' + str(-days) + ' days' if days < 0 else ' now'}",
        "firm": f"Overdue: {ref} — {amt}, {days} days past due",
        "escalation": f"Action needed: {ref} unpaid for {days} days ({amt})",
        "final": f"Final notice — {ref}, {amt}, {days} days overdue",
    }[tier]


def _email_body(tier: str, inv: dict[str, Any], sender: str, company: str, currency: str) -> str:
    name = inv["customer"].split()[0] if inv["customer"] else "there"
    ref = inv.get("invoice_no") or "the invoice"
    amt = fmt_money(inv["amount"], currency)
    days = inv["days_overdue"]
    due = inv.get("due_date") or "the agreed date"
    sign = f"{sender}\n{company}".strip()

    if tier == "reminder":
        body = (
            f"Hi {name},\n\n"
            f"Quick note that {ref} for {amt} is due on {due}. "
            "I am sure it is already in the queue — this is just so it does not slip.\n\n"
            "If you need the invoice re-sent or a PO number added, tell me and I will "
            "turn it around today.\n\n"
            f"Thanks,\n{sign}"
        )
    elif tier == "firm":
        body = (
            f"Hi {name},\n\n"
            f"{ref} for {amt} was due on {due} and is now {days} days past due.\n\n"
            "Could you confirm the date it will be paid? If there is a problem with the "
            "invoice, I would rather know now than keep chasing.\n\n"
            "A specific date is all I need.\n\n"
            f"Thanks,\n{sign}"
        )
    elif tier == "escalation":
        body = (
            f"Hi {name},\n\n"
            f"{ref} for {amt} is now {days} days overdue and I have not had a payment date.\n\n"
            "I am copying your finance team so this stops sitting between us. To be direct: "
            "until this is cleared I am holding new work on the account.\n\n"
            "If cash timing is the issue, propose a payment plan and I will look at it "
            "seriously. Silence is the only outcome I cannot work with.\n\n"
            f"Regards,\n{sign}"
        )
    else:
        body = (
            f"{name},\n\n"
            f"This is a final notice on {ref} for {amt}, now {days} days overdue "
            f"against a due date of {due}.\n\n"
            "If payment or a signed payment plan is not received within 7 days, I will pass "
            "this to recovery and stop all service on the account. I would rather not — "
            "one email today ends it.\n\n"
            "Please treat this as time-sensitive.\n\n"
            f"Regards,\n{sign}"
        )
    return body


def _whatsapp(tier: str, inv: dict[str, Any], sender: str, company: str, currency: str,
              clause: str = "") -> str:
    name = inv["customer"].split()[0] if inv["customer"] else "Hi"
    ref = inv.get("invoice_no") or "the invoice"
    amt = fmt_money(inv["amount"], currency)
    days = inv["days_overdue"]
    tail = f"— {sender}, {company}".strip(" ,-")
    core = {
        "reminder": f"Hi {name}, quick reminder that {ref} ({amt}) is due. Anything you need from me to release it?",
        "firm": f"Hi {name}, {ref} ({amt}) is {days} days past due. Can you give me a payment date today?",
        "escalation": f"{name}, {ref} ({amt}) is {days} days overdue and I have no payment date. I am holding new work until it clears. Can we sort this out today?",
        "final": f"{name}, final notice on {ref} ({amt}), {days} days overdue. Payment or a payment plan within 7 days, or it goes to recovery. Please call me.",
    }[tier]
    # The sign-off always goes last, after any statutory note.
    return " ".join(x for x in (core, clause.strip(), tail) if x)


def _statutory_clause(inv: dict[str, Any], currency: str, rate: float | None, channel: str) -> str:
    """Optional MSMED paragraph. Only for genuinely late, material invoices —
    quoting a statute over a three-day delay reads as bluster, not leverage."""
    amt = inv.get("statutory_interest") or 0
    if not rate or amt < 100 or inv.get("days_overdue", 0) <= 45:
        return ""
    money = fmt_money(amt, currency)
    if channel == "whatsapp":
        return f"Statutory interest under the MSMED Act has also accrued to about {money}."
    if inv["tier"] == "final":
        return (
            f"\n\nSeparately: under Section 16 of the MSMED Act, 2006, this delay has accrued "
            f"approximately {money} in statutory interest at {rate}% per annum, compounded "
            "monthly. If this is not settled I will register the claim on the MSME Samadhaan "
            "portal. I would prefer to close it between us."
        )
    return (
        f"\n\nFor completeness: under the MSMED Act, 2006 a delay of this length accrues "
        f"statutory interest at {rate}% per annum, currently around {money}. I am not pursuing "
        "that, and would rather just agree a payment date."
    )


def _insert_clause(body: str, clause: str) -> str:
    """Place the clause above the sign-off rather than after it."""
    if not clause:
        return body
    parts = body.rsplit("\n\n", 1)
    return (parts[0] + clause + "\n\n" + parts[1]) if len(parts) == 2 else body + clause


def build_messages(
    priority: list[dict[str, Any]],
    sender: str = "",
    company: str = "",
    currency: str = "INR",
    limit: int = 10,
    statutory_rate: float | None = None,
) -> list[dict[str, Any]]:
    sender = (sender or "").strip()[:80]
    company = (company or "").strip()[:80]
    out = []
    for inv in priority[:limit]:
        tier = inv["tier"]
        out.append({
            "invoice_no": inv.get("invoice_no", ""),
            "customer": inv["customer"],
            "amount": inv["amount"],
            "days_overdue": inv["days_overdue"],
            "tier": tier,
            "tier_label": TIER_LABELS[tier],
            "why": TIER_GUIDANCE[tier],
            "to_email": inv.get("email", ""),
            "to_phone": inv.get("phone", ""),
            "subject": _subject(tier, inv, currency),
            "statutory_interest": inv.get("statutory_interest", 0),
            "email": _insert_clause(
                _email_body(tier, inv, sender or "[Your name]", company or "[Your company]", currency),
                _statutory_clause(inv, currency, statutory_rate, "email")),
            "whatsapp": _whatsapp(tier, inv, sender or "[Your name]", company or "[Your company]",
                                  currency, _statutory_clause(inv, currency, statutory_rate, "whatsapp")),
        })
    return out
