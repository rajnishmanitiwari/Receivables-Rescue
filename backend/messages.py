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
    "final": "Final notice",
}

TIER_GUIDANCE = {
    "reminder": "Assume it is an oversight. Give them a one-click way to pay.",
    "firm": "Name the date, name the amount, ask for a committed payment date.",
    "escalation": "Same facts, firmer tone, from you or someone senior. Ask for a committed date or a reason.",
    "final": "A dated last ask: payment or a plan by a date you set. Only send a deadline you intend to keep.",
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
            "If there is a problem with the invoice, or cash timing is the issue, tell me - "
            "a payment plan is fine to propose.\n\n"
            "What I cannot plan around is silence. A specific date, or a reason, is all I need.\n\n"
            f"Regards,\n{sign}"
        )
    else:
        body = (
            f"{name},\n\n"
            f"This is a final notice on {ref} for {amt}, now {days} days overdue "
            f"against a due date of {due}.\n\n"
            "I need payment, or a payment plan we both agree to, by [date you choose]. "
            "If anything is blocking it, tell me today and I will work with it.\n\n"
            "Please treat this as time-sensitive.\n\n"
            f"Regards,\n{sign}"
        )
    return body


def _whatsapp(tier: str, inv: dict[str, Any], sender: str, company: str, currency: str) -> str:
    name = inv["customer"].split()[0] if inv["customer"] else "Hi"
    ref = inv.get("invoice_no") or "the invoice"
    amt = fmt_money(inv["amount"], currency)
    days = inv["days_overdue"]
    tail = f"— {sender}, {company}".strip(" ,-")
    core = {
        "reminder": f"Hi {name}, quick reminder that {ref} ({amt}) is due. Anything you need from me to release it?",
        "firm": f"Hi {name}, {ref} ({amt}) is {days} days past due. Can you give me a payment date today?",
        "escalation": f"{name}, {ref} ({amt}) is {days} days overdue and I still have no payment date. Can you give me a date, or tell me what is blocking it?",
        "final": f"{name}, final notice on {ref} ({amt}), {days} days overdue. Please pay, or send me a firm payment date, by [date you choose]. Please call me today.",
    }[tier]
    # The sign-off always goes last.
    return " ".join(x for x in (core, tail) if x)


def build_messages(
    priority: list[dict[str, Any]],
    sender: str = "",
    company: str = "",
    currency: str = "INR",
    limit: int = 10,
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
            # No statutory/legal assertions in sendable text: MSMED eligibility is
            # unverified, so no clause is inserted whatever rate the caller has.
            "email": _email_body(tier, inv, sender or "[Your name]", company or "[Your company]", currency),
            "whatsapp": _whatsapp(tier, inv, sender or "[Your name]", company or "[Your company]",
                                  currency),
        })
    return out
