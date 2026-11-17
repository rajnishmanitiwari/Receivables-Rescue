"""Reply-aware next-action planner for overdue invoices (private prototype, synthetic data only).

One pure function: next_action(invoice, events, today) -> Action.
It never sends anything. A classifier may label inbound replies, but the decision
logic is deterministic and testable. Tier thresholds follow a simple ladder.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
import re

class Kind(str, Enum):
    NONE = "none"            # nothing to do today
    DRAFT = "draft"          # prepare a follow-up for human approval
    HOLD = "hold"            # wait until a date
    PAUSE = "pause"          # dispute: stop chasing, a human must resolve
    STOP = "stop"            # paid or closed
    HUMAN = "human"          # ambiguous or risky, ask a person

class Label(str, Enum):
    PAID = "paid"; DISPUTE = "dispute"; PROMISE = "promise"; DONT_CONTACT = "dont_contact"
    PARTIAL = "partial"; UNKNOWN = "unknown"

TIERS = [("reminder", 1, 14), ("firm", 15, 30), ("escalation", 31, 60), ("final", 61, 10**6)]
MIN_GAP_DAYS = 5

@dataclass(frozen=True)
class Event:
    day: date
    type: str                  # "sent", "reply", "payment", "resolved" (a person reviewed the last reply)
    label: Label | None = None
    promise_date: date | None = None
    amount: float | None = None
    tier: str | None = None
    flags: frozenset = frozenset()   # "optout" / "dispute" from reply_flags; survives label loss

@dataclass(frozen=True)
class Invoice:
    number: str; amount: float; due: date; status: str = "open"   # open|void|paid

@dataclass(frozen=True)
class Action:
    kind: Kind; reason: str; tier: str | None = None; until: date | None = None

_APOS = re.compile(r"[\u2019\u2018\u0060\u00b4\u2032\u02bc]")
def _norm(text: str) -> str:
    """Shared normalization for classifier AND flags: lowercase, unify curly/Unicode
    apostrophes to straight, then drop apostrophes so 'dont', "don't" and curly
    variants all hit the same guards. Case folding covers uppercase forms."""
    return _APOS.sub("'", text.lower()).replace("'", "")

_RE_DISPUTE = r"\b(disput\w*|incorrect|wrong amount|not (our|my) invoice|never received (the )?(goods|service)|not delivered|overcharged|(invoice|bill|amount|charge) is wrong)\b"
_RE_OPTOUT = r"\b(stop (emailing|contacting|sending)|do not (contact|email)|dont (email|contact)|unsubscribe|remove me|opt( me)?[ -]?out)\b|^\s*stop[.!\s]*$"
_PATTERNS = [
    (Label.DONT_CONTACT, _RE_OPTOUT),
    (Label.DISPUTE, _RE_DISPUTE),
    (Label.PAID, r"\b(already paid|have paid|has been paid|payment (was )?made|payment (is )?done|paid on|paid (this|it|that|the invoice|the bill|invoice))\b"),
    (Label.PROMISE, r"\b(will pay|will transfer|pay (you )?(by|on)|paying (today|tomorrow|tonight)|payment (will|is) (be )?(made|scheduled)|processing (the )?payment|by (monday|tuesday|wednesday|thursday|friday|saturday|sunday|next week|month end|eom))\b"),
    (Label.PARTIAL, r"\b(partial payment|part payment|paid half|paid part)\b"),
]

# Negation guards: a negated phrase must not be taken at face value. A guard that blocks a
# match drops the reply to UNKNOWN, which sends it to a human - never to a wrong follow-up.
_NEG_PAID = re.compile(r"\b(did not|didnt|have not|havent|has not|hasnt|never|not)\b[^.!?;]{0,40}\b(paid|payment (was )?made|payment done)\b")
_NEG_DISPUTE = re.compile(r"\bno disput\w*\b")
# Qualified or negated opt-outs are NOT clear opt-outs. "Not opting out", a channel or
# address change ("don't email, call me"), excluding a third party ("stop contacting my
# accountant") or one disputed invoice all need a human - never a sticky STOP.
_OPT_NEGATED = re.compile(
    r"\b(do not|dont|does not|doesnt|will not|wont|would not|wouldnt|cannot|can not|cant|never)\s+"
    r"(stop\b|opt(ing)?(\s+me)?[ -]?out)"
    r"|\b(did not|didnt|does not|doesnt|do not|dont|never|not)\s+"
    r"(say|said|saying|ask|asked|asking|tell|told|telling|mean|meant|opting?(\s+me)?[ -]?out)\b"
    r"|\bdoes\s*not\s+mean\s+stop\b|\bdoesnt\s+mean\s+stop\b"
)
_OPT_QUALIFIED = re.compile(
    r"\b(dont|do not|stop)\s+(email|mail|contact|message|send)\w*\b[^.!?;]{0,60}?\b("
    r"this (address|e?mail|number|invoice|bill)|that (address|e?mail|invoice|bill)|"
    r"(same|old|corrected) (invoice|bill|address|e?mail|copy)|"
    r"my other|work e?mail|personal e?mail|"
    r"call me|call instead|phone|whatsapp|text me|sms|letter|instead|"
    r"accountant|bookkeeper|ca\b|chartered|finance team|accounts team|lawyer|advocate|"
    r"weekends?|weekdays?|at night|after hours)\b"
)

def reply_flags(text: str) -> frozenset:
    """Independent of the single returned label: a reply can carry BOTH a clear opt-out
    and a dispute. The planner uses these flags so dual-intent replies keep the
    no-contact sticky AND get a human for the dispute."""
    t = _norm(text)
    out = set()
    if re.search(_RE_OPTOUT, t) and not (_OPT_NEGATED.search(t) or _OPT_QUALIFIED.search(t)):
        out.add("optout")
    if re.search(_RE_DISPUTE, t) and not _NEG_DISPUTE.search(t):
        out.add("dispute")
    return frozenset(out)

def classify_reply(text: str) -> Label:
    """Keyword baseline with negation guards. Order matters: disputes and opt-outs win over 'paid'."""
    t = _norm(text)
    for label, pat in _PATTERNS:
        if re.search(pat, t):
            if label == Label.PAID and _NEG_PAID.search(t):
                continue
            if label == Label.DISPUTE and _NEG_DISPUTE.search(t):
                continue
            if label == Label.DONT_CONTACT and (_OPT_NEGATED.search(t) or _OPT_QUALIFIED.search(t)):
                continue
            return label
    return Label.UNKNOWN

def tier_for(days_overdue: int) -> str:
    for name, lo, hi in TIERS:
        if lo <= days_overdue <= hi:
            return name
    return "reminder"

def next_action(inv: Invoice, events: list[Event], today: date) -> Action:
    if inv.status in ("void", "paid"):
        return Action(Kind.STOP, f"invoice is {inv.status}")
    paid = sum(e.amount or 0 for e in events if e.type == "payment" and e.day <= today)
    if paid >= inv.amount:
        return Action(Kind.STOP, "fully paid by recorded payments")
    evs = sorted((e for e in events if e.day <= today), key=lambda e: e.day)
    replies = [e for e in evs if e.type == "reply"]
    # Opt-out and dispute are sticky: no later event reopens them without a human.
    optouts = [e for e in replies if e.label == Label.DONT_CONTACT or "optout" in e.flags]
    if optouts:
        dispute_open = any(
            (e.label == Label.DISPUTE or "dispute" in e.flags)
            and not any(r.type == "resolved" and r.day >= e.day for r in evs)
            for e in replies)
        if dispute_open:
            # Dual intent: keep no-contact sticky AND get a person for the dispute.
            # After resolution the opt-out still stands: no resume without re-consent.
            return Action(Kind.HUMAN, "opt-out recorded with an open dispute; a person must resolve it - no further contact without explicit re-consent")
        return Action(Kind.STOP, "contact opt-out recorded")
    if any(e.label == Label.DISPUTE for e in replies):
        return Action(Kind.PAUSE, "dispute recorded; a person must resolve it")
    days_over = (today - inv.due).days
    if days_over < 1:
        return Action(Kind.NONE, "not overdue")
    last_reply = replies[-1] if replies else None
    if last_reply and last_reply.label == Label.PAID:
        return Action(Kind.HUMAN, "customer says paid but no matching payment recorded")
    if last_reply and last_reply.label == Label.PROMISE:
        if last_reply.promise_date is None:
            return Action(Kind.HUMAN, "promise without a date")
        if today <= last_reply.promise_date:
            return Action(Kind.HOLD, "honouring promised date", until=last_reply.promise_date)
    if last_reply and last_reply.label == Label.UNKNOWN and not any(e.type == "resolved" and e.day >= last_reply.day for e in evs):
        return Action(Kind.HUMAN, "latest reply not understood")
    sent = [e for e in evs if e.type == "sent"]
    if sent and (today - sent[-1].day).days < MIN_GAP_DAYS:
        return Action(Kind.HOLD, "minimum gap since last follow-up",
                      until=sent[-1].day + timedelta(days=MIN_GAP_DAYS))
    tier = tier_for(days_over)
    order = [t[0] for t in TIERS]
    if sent and sent[-1].tier in order and order.index(sent[-1].tier) >= order.index(tier):
        # never repeat the same tier; step at most one rung up from the last one sent
        nxt = order[min(order.index(sent[-1].tier) + 1, len(order) - 1)]
        if nxt == sent[-1].tier or days_over < dict((n, lo) for n, lo, _ in TIERS)[nxt]:
            return Action(Kind.HOLD, "already sent this tier; wait for next tier",
                          until=inv.due + timedelta(days=dict((n, lo) for n, lo, _ in TIERS)[nxt]))
        tier = nxt
    elif sent and sent[-1].tier in order:
        tier = order[min(order.index(sent[-1].tier) + 1, order.index(tier))]
    if last_reply and last_reply.label == Label.PARTIAL:
        return Action(Kind.DRAFT, "partial payment acknowledged; chase balance", tier="reminder")
    return Action(Kind.DRAFT, f"{days_over} days overdue", tier=tier)
