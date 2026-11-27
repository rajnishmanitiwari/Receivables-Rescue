"""
Receivables Rescue: deterministic collections engine.

No LLM required. Every number below is arithmetic on the user's own invoice
data plus a published-style aging recovery curve. We are explicit that the
curve is a benchmark heuristic, not a prediction about their specific customers.
"""
from __future__ import annotations

import csv
import io
import math
import re
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from typing import Any

# ---------------------------------------------------------------------------
# Recovery curve
# ---------------------------------------------------------------------------
# Probability that a receivable is eventually collected, by days past due.
# Based on the standard commercial-collections aging curve (collectability
# falls off a cliff after 90 days). Treated as a transparent benchmark, and
# surfaced to the user as an assumption they can see.
RECOVERY_CURVE: list[tuple[int, float]] = [
    (-60, 0.98),
    (0, 0.94),
    (30, 0.86),
    (60, 0.74),
    (90, 0.56),
    (180, 0.31),
    (365, 0.14),
    (730, 0.08),
]

BUCKETS: list[tuple[str, int, int]] = [
    ("Not yet due", -10_000, -1),
    ("0-30 days", 0, 30),
    ("31-60 days", 31, 60),
    ("61-90 days", 61, 90),
    ("91-180 days", 91, 180),
    ("180+ days", 181, 10_000),
]

TIERS: list[tuple[str, int, int]] = [
    ("reminder", -10_000, 15),
    ("firm", 16, 45),
    ("escalation", 46, 90),
    ("final", 91, 10_000),
]

MAX_INVOICES = 2000

# --- India: MSMED Act, 2006 ------------------------------------------------
# Section 15: a buyer must pay a registered micro/small enterprise within the
#   agreed period, capped at 45 days from acceptance (15 days if nothing agreed).
# Section 16: on delay, the buyer owes compound interest with MONTHLY RESTS at
#   three times the Bank Rate notified by the Reserve Bank of India.
# Bank Rate is user-editable in the UI because it moves; this default is the
# rate published as effective 5 August 2026. Verify before relying on a figure.
RBI_BANK_RATE_DEFAULT = 5.50
MSMED_MULTIPLIER = 3
MSMED_MAX_CREDIT_DAYS = 45
DAYS_PER_MONTH = 30.4375


def msmed_interest(amount: float, days_overdue: int, bank_rate: float) -> float:
    """Section 16 compound interest, monthly rests. Zero until payment is late."""
    if days_overdue <= 0 or amount <= 0 or bank_rate <= 0:
        return 0.0
    monthly = (MSMED_MULTIPLIER * bank_rate / 100.0) / 12.0
    months = days_overdue / DAYS_PER_MONTH
    return round(amount * ((1 + monthly) ** months - 1), 2)


class ParseError(ValueError):
    pass


def recovery_probability(days_overdue: int) -> float:
    """Linear interpolation between aging anchors, so every extra day of delay
    has a visible cost rather than nothing happening until a bucket flips."""
    pts = RECOVERY_CURVE
    if days_overdue <= pts[0][0]:
        return pts[0][1]
    if days_overdue >= pts[-1][0]:
        return pts[-1][1]
    for (d0, p0), (d1, p1) in zip(pts, pts[1:]):
        if d0 <= days_overdue <= d1:
            span = d1 - d0
            return round(p0 + (p1 - p0) * ((days_overdue - d0) / span), 4)
    return pts[-1][1]


def bucket_for(days_overdue: int) -> str:
    for name, lo, hi in BUCKETS:
        if lo <= days_overdue <= hi:
            return name
    return BUCKETS[-1][0]


def tier_for(days_overdue: int) -> str:
    for name, lo, hi in TIERS:
        if lo <= days_overdue <= hi:
            return name
    return "final"


# ---------------------------------------------------------------------------
# Input parsing
# ---------------------------------------------------------------------------
_HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "customer": ("customer", "client", "name", "party", "company", "customer name",
                 "client name", "buyer", "account", "debtor", "billed to", "bill to"),
    "invoice_no": ("invoice", "invoice no", "invoice number", "inv", "inv no",
                   "invoice#", "bill no", "ref", "reference", "document no", "invoice id"),
    "amount": ("amount", "value", "total", "balance", "outstanding", "amount due",
               "balance due", "grand total", "net amount", "invoice amount", "due amount"),
    "due_date": ("due date", "duedate", "due", "date due", "payment due",
                 "maturity", "due on"),
    "invoice_date": ("invoice date", "date", "issue date", "bill date", "created"),
    "email": ("email", "e-mail", "email id", "contact email", "mail"),
    "phone": ("phone", "mobile", "whatsapp", "contact", "phone no", "contact no", "tel"),
}

_DATE_FORMATS = (
    "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%d.%m.%Y",
    "%d %b %Y", "%d %B %Y", "%b %d %Y", "%B %d %Y", "%Y/%m/%d",
    "%d/%m/%y", "%d-%m-%y", "%m/%d/%y", "%Y-%m-%d %H:%M:%S",
)

# Numeric dates split by convention. A date like 05/06/2026 matches both
# families: only the reader knows which way the file was written.
_DMY_FORMATS = ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y")
_MDY_FORMATS = ("%m/%d/%Y", "%m/%d/%y")
_NUMERIC_DATE_RE = re.compile(r"^(\d{1,2})([/.\-])(\d{1,2})\2(\d{2}|\d{4})(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?$")


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", str(s or "").strip().lower()).strip()


def _map_headers(headers: list[str]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    normed = [_norm(h) for h in headers]
    for field_name, aliases in _HEADER_ALIASES.items():
        for idx, h in enumerate(normed):
            if h in aliases and field_name not in mapping:
                mapping[field_name] = idx
                break
        if field_name in mapping:
            continue
        for idx, h in enumerate(normed):
            if not h:
                continue
            if any(h.startswith(a) or a in h for a in aliases) and idx not in mapping.values():
                mapping[field_name] = idx
                break
    return mapping


def parse_amount(raw: Any) -> float | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    # Do not join operands into a larger amount when stripping punctuation.
    if re.search(r"[0-9]\s*[+/*\u00d7\u00f7]\s*[+\-\u2212]?\s*[0-9]", s):
        return None
    # An explicit CR marker is not confirmed positive money to collect.
    # Reject it rather than stripping the marker and chasing a credit.
    if re.search(r"(?<![A-Za-z])cr(?![A-Za-z])", s, re.IGNORECASE):
        return None
    # A rate is not an outstanding money amount. Never discard its unit.
    if any(mark in s for mark in ("%", "\uff05", "\u066a")):
        return None
    # Scientific notation is not a supported money format. Stripping its
    # exponent marker would silently turn e.g. 1e3 into 13.
    if re.search(r"[0-9][0-9.,]*[eE][+\-\u2212]?[0-9]", s):
        return None
    neg = s.startswith("(") and s.endswith(")")
    # Preserve the mathematical minus used by spreadsheet/accounting exports.
    # Dropping it would turn a credit into a positive receivable.
    s = s.replace("\u2212", "-")
    s = re.sub(r"[^0-9.,\-]", "", s)
    if not s:
        return None
    # Indian/US thousands separators; last separator followed by exactly 2 digits = decimal
    if "," in s and "." in s:
        s = s.replace(",", "") if s.rfind(".") > s.rfind(",") else s.replace(".", "").replace(",", ".")
    elif "," in s:
        tail = s.split(",")[-1]
        s = s.replace(",", ".") if len(tail) == 2 and s.count(",") == 1 else s.replace(",", "")
    try:
        val = float(s)
    except ValueError:
        return None
    if not math.isfinite(val):
        return None
    if neg:
        # Accounting parentheses denote negative, never invert an explicit minus.
        val = -abs(val)
    return val


def parse_date(raw: Any) -> date | None:
    if raw is None:
        return None
    if isinstance(raw, date):
        return raw
    s = str(raw).strip()
    if not s:
        return None
    s = re.sub(r"\s+", " ", s.replace(",", " ")).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    # Read the whole cell, never turn a range, note or malformed timestamp
    # into a confirmed due date by silently discarding its suffix.
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    if re.fullmatch(
        r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}"
        r"(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)?", s
    ):
        try:
            # A due-date column uses the stated calendar day, not a timezone
            # conversion. Validate the time too before accepting that day.
            # Python 3.10 only accepts 3 or 6 fractional digits. Pad valid
            # shorter fractions so supported ISO values do not become unknown.
            stamp = re.sub(r"\.(\d{1,6})(?=Z|[+-]|$)",
                           lambda m: "." + m.group(1).ljust(6, "0"), s)
            return datetime.fromisoformat(stamp.replace("Z", "+00:00")).date()
        except ValueError:
            return None
    return None


def _numeric_date_form(raw: Any) -> str:
    """Classify a numeric date cell: "dmy" or "mdy" when only one convention
    can read it, "ambiguous" when both can read it DIFFERENTLY, "" when it
    is not a numeric day/month/year-shaped value (ISO, month names, blank,
    unparseable). Same-day numerics (07/07/2026) read identically both ways,
    so they are not ambiguous."""
    if raw is None or isinstance(raw, date):
        return ""
    s = re.sub(r"\s+", " ", str(raw).strip().replace(",", " ")).strip()
    m = _NUMERIC_DATE_RE.match(s)
    if not m:
        return ""
    a, b = int(m.group(1)), int(m.group(3))
    if a > 12 and b <= 12:
        return "dmy"
    if b > 12 and a <= 12:
        return "mdy"
    if 1 <= a <= 12 and 1 <= b <= 12 and a != b:
        return "ambiguous"
    return ""


def _parse_numeric_convention(raw: Any, convention: str) -> date | None:
    """Parse a numeric date under one convention only ("dmy" or "mdy")."""
    s = re.sub(r"\s+", " ", str(raw or "").strip().replace(",", " ")).strip()
    for fmt in (_DMY_FORMATS if convention == "dmy" else _MDY_FORMATS):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


@dataclass
class Invoice:
    customer: str
    invoice_no: str = ""
    amount: float = 0.0
    due_date: date | None = None
    email: str = ""
    phone: str = ""
    # Where the due date came from: "column" (a named due-date column, which the
    # caller's own header confirms), "positional" (an unlabelled column in
    # headerless input - an assumption, not a confirmed due date) or "ambiguous"
    # (a numeric date readable day-first or month-first - kept as a visible
    # guess, never a confirmed due date). "" when none.
    date_source: str = ""
    # Preserve unreadable source text for correction in the import review.
    due_date_raw: str = ""
    # derived
    days_overdue: int = 0
    bucket: str = ""
    tier: str = ""
    probability: float = 0.0
    expected_value: float = 0.0
    slip_30d: float = 0.0
    statutory_interest: float = 0.0
    rank: int = 0


def _sniff_dialect(text: str) -> str:
    head = text[:4000]
    # Recognizable headers outrank punctuation inside data fields. Raw counts
    # alone can mistake quoted semicolons in a CSV customer for the delimiter.
    header_scores = {}
    for delimiter in (",", "\t", ";", "|"):
        try:
            first = next(csv.reader(io.StringIO(head), delimiter=delimiter), [])
        except csv.Error:
            continue
        fields = _map_headers(first)
        if "amount" in fields and len(fields) >= 2:
            header_scores[delimiter] = len(fields)
    if header_scores:
        return max(header_scores, key=header_scores.get)
    # Keep the existing fallback for input without a recognizable header.
    counts = {d: head.count(d) for d in (",", "\t", ";", "|")}
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else ","


def parse_invoices(text: str, today: date | None = None) -> tuple[list[Invoice], list[str]]:
    """Accept CSV/TSV with or without a header row, or free-form pasted lines."""
    today = today or date.today()
    warnings: list[str] = []
    text = (text or "").strip()
    if not text:
        raise ParseError("No invoice data provided.")

    delim = _sniff_dialect(text)
    try:
        rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim, strict=True) if any(str(c).strip() for c in r)]
    except csv.Error:
        raise ParseError(
            "CSV text could not be read safely. Check for unclosed quotes or extra text after a closing quote, "
            "then try again. No rows from this input were imported or analysed."
        ) from None
    if not rows:
        raise ParseError("Could not read any rows from that input.")

    header_map: dict[str, int] = {}
    body = rows
    candidate = _map_headers(rows[0])
    first_row_has_amount = parse_amount(rows[0][-1] if rows[0] else "") is not None
    if len(candidate) >= 2 and not (first_row_has_amount and "amount" not in candidate):
        amount_columns = sum(_norm(h) in _HEADER_ALIASES["amount"] for h in rows[0])
        if amount_columns > 1:
            raise ParseError(
                "More than one amount column was found. Keep only the outstanding balance column you intend "
                "to use and name it Amount, then try again. No rows from this input were imported or analysed."
            )
        due_columns = sum(_norm(h) in _HEADER_ALIASES["due_date"] for h in rows[0])
        if due_columns > 1:
            raise ParseError(
                "More than one due-date column was found. Keep only the due date you intend "
                "to use and name it Due Date, then try again. No rows from this input were imported or analysed."
            )
        customer_columns = sum(_norm(h) in _HEADER_ALIASES["customer"] for h in rows[0])
        if customer_columns > 1:
            raise ParseError(
                "More than one customer column was found. Keep only the name of who owes you "
                "and name that column Customer, then try again. No rows from this input were imported or analysed."
            )
        header_map = candidate
        body = rows[1:]
    if not body:
        raise ParseError("Found a header row but no invoice rows underneath it.")

    if header_map and any(any(str(c).strip() for c in row[len(rows[0]):]) for row in body):
        raise ParseError(
            "A row has more fields than the header. Check the separators and quote values containing "
            "separators, such as comma-formatted amounts, then try again. "
            "No rows from this input were imported or analysed."
        )

    positional_mode = not header_map
    if positional_mode:
        # Positional fallback: customer, invoice_no, amount, due_date, email, phone
        widest = max(len(r) for r in body)
        header_map = {"customer": 0}
        if widest >= 4:
            header_map |= {"invoice_no": 1, "amount": 2, "due_date": 3}
        elif widest == 3:
            header_map |= {"amount": 1, "due_date": 2}
        elif widest == 2:
            header_map |= {"amount": 1}
        if widest >= 5:
            header_map["email"] = 4
        if widest >= 6:
            header_map["phone"] = 5

    if "amount" not in header_map:
        raise ParseError(
            "Couldn't find an amount column. Include a column named Amount, Balance or Outstanding."
        )

    def cell(row: list[str], key: str) -> str:
        idx = header_map.get(key)
        if idx is None or idx >= len(row):
            return ""
        return str(row[idx]).strip()

    # A numeric date like 05/06/2026 reads as 5 June day-first or 6 May
    # month-first. One unambiguous row elsewhere in the column does not prove
    # how another person typed the ambiguous rows, so inference never
    # confirms them: every ambiguous date stays unconfirmed. The column scan
    # only picks which reading to SHOW as the guess (day-first by default;
    # the column's proven direction when one exists) and how the warning
    # explains it. A column containing BOTH conventions is flagged mixed.
    column_convention = ""
    if not positional_mode and "due_date" in header_map:
        forms = {_numeric_date_form(cell(r, "due_date")) for r in body[:MAX_INVOICES]}
        if "dmy" in forms and "mdy" in forms:
            column_convention = "mixed"
        elif "dmy" in forms:
            column_convention = "dmy"
        elif "mdy" in forms:
            column_convention = "mdy"
    guess_convention = column_convention if column_convention in ("dmy", "mdy") else "dmy"

    invoices: list[Invoice] = []
    skipped = 0
    undated = 0
    ambiguous_guessed = 0
    unnamed = 0
    for row in body[:MAX_INVOICES]:
        amount = parse_amount(cell(row, "amount"))
        # Validate the same two-decimal balance we actually store and chase.
        # A tiny positive source value may round to zero, which is not a bill.
        if amount is not None:
            amount = round(amount, 2)
        if amount is None or amount <= 0:
            skipped += 1
            continue
        # Only an explicit due-date column sets the due date. An invoice date
        # is when the bill was issued, never when payment is due; rows without
        # a confirmed due date stay unscheduled (analyse keeps them neutral).
        raw_due = cell(row, "due_date")
        due: date | None = None
        if _numeric_date_form(raw_due) == "ambiguous" and not positional_mode:
            # Readable two ways and inference never confirms: keep the guess
            # visible for the review screen, but unconfirmed - it never
            # drives totals, tiers or chase drafts until the user confirms.
            due = _parse_numeric_convention(raw_due, guess_convention)
            if due is not None:
                date_source = "ambiguous"
                ambiguous_guessed += 1
        else:
            due = parse_date(raw_due)
            if due is not None:
                date_source = "positional" if positional_mode else "column"
        if due is None:
            undated += 1
            date_source = ""
        customer = cell(row, "customer")
        if not customer:
            # Unknown means unknown: a blank customer is never replaced with a
            # placeholder. "Unnamed customer" would merge distinct unknown
            # debtors into one pseudo-customer, corrupting by-customer totals
            # and combining their chase drafts, so the whole analysis is
            # rejected below and the user names each bill first.
            unnamed += 1
            continue
        if len(customer) > 120:
            raise ParseError(
                "A customer name is longer than 120 characters. Shorten or correct it to a unique name "
                "of at most 120 characters, then try again. No rows from this input were imported or analysed."
            )
        invoice_no = cell(row, "invoice_no")
        if len(invoice_no) > 60:
            raise ParseError(
                "A bill number is longer than 60 characters. Shorten or correct it to a unique reference "
                "of at most 60 characters, then try again. No rows from this input were imported or analysed."
            )
        invoices.append(
            Invoice(
                customer=customer,
                invoice_no=invoice_no,
                amount=amount,
                due_date=due,
                due_date_raw=raw_due if due is None else "",
                email=cell(row, "email")[:120],
                phone=cell(row, "phone")[:40],
                date_source=date_source,
            )
        )

    if unnamed:
        raise ParseError(
            f"{unnamed} bill(s) have no customer name. Add who owes you for "
            "each bill before analysing; an unknown debtor is never guessed, "
            "grouped or chased."
        )
    if len(body) > MAX_INVOICES:
        warnings.append(f"Only the first {MAX_INVOICES} rows were analysed.")
    if skipped:
        warnings.append(f"Skipped {skipped} row(s) with no usable amount.")
    positional_dated = sum(1 for i in invoices if i.date_source == "positional")
    if positional_dated:
        warnings.append(
            f"{positional_dated} row(s) came without a header row, so the due date was "
            "read from an unlabelled column and is unconfirmed. Those rows are not "
            "scheduled for chasing. Confirm or fix the dates where you review them, "
            "or add a header row naming the due date column."
        )
    elif positional_mode:
        warnings.append("No header row detected - read columns as: customer, invoice no, amount, due date.")
    if undated:
        warnings.append(
            f"{undated} invoice(s) had no readable due date. Their lateness is unknown "
            "and they are not scheduled for chasing. Add due dates to include them."
        )
    if ambiguous_guessed:
        shown = "day-first" if guess_convention == "dmy" else "month-first"
        if column_convention == "mixed":
            why = "this column contains BOTH date formats, so there is no safe reading"
        elif column_convention:
            why = f"matching the rest of the column, but still only a guess"
        else:
            why = "no other date in the column settles which"
        warnings.append(
            f"{ambiguous_guessed} date(s) like 05/06/2026 could be read day-first or "
            f"month-first ({why}). Shown {shown}, unconfirmed; those bills are not "
            "scheduled for chasing. Confirm or fix the dates where you review them."
        )
    # Duplicate and conflicting bills. A bill number is the bill's identity -
    # but only a REAL one: placeholder strings ("N/A", "-", "no") mean "no
    # number", and rows without an identity are never merged, so two distinct
    # bills are never collapsed into one.
    # Exact duplicates (same customer, number, amount and due date) are one
    # bill entered twice: collapse to one row with a warning, so the book is
    # not doubled and no customer gets two chasers for one bill.
    # The same number with a conflicting amount or due date means we cannot
    # tell whether it is one bill or two. Neither version is counted in totals
    # or scheduled for chasing - the records are quarantined with a warning
    # until the user resolves which is real. We never silently pick a version.
    def _identity(inv: Invoice) -> tuple[str, str] | None:
        # Real identifiers keep their punctuation AND internal spacing: "1-2",
        # "12", "1 2", "INV 1" and "INV1" are all different bills. Only case and
        # leading/trailing whitespace are folded for the comparison.
        num = inv.invoice_no.strip().lower()
        if not num:
            return None
        # Placeholder classification is a separate, more aggressive probe:
        # "N/A", "n.a.", "-", "no." all mean "there is no bill number here".
        probe = re.sub(r"[\s./\\\-_:;#]+", "", num)  # classification only
        if probe in ("", "na", "none", "nil", "no", "unknown", "tbd"):
            return None
        cust = re.sub(r"\s+", " ", inv.customer).strip().lower()
        return (cust, num)

    seen_numbers: dict[tuple[str, str], tuple[float, date | None]] = {}
    original_numbers: dict[tuple[str, str], str] = {}
    dupe_counts: dict[tuple[str, str], int] = {}
    conflict_keys: set[tuple[str, str]] = set()
    kept: list[Invoice] = []
    for inv in invoices:
        key = _identity(inv)
        if key is None:
            kept.append(inv)
            continue
        original_numbers.setdefault(key, inv.invoice_no.strip())
        sig = (inv.amount, inv.due_date)
        if key in seen_numbers:
            if seen_numbers[key] == sig:
                dupe_counts[key] = dupe_counts.get(key, 0) + 1
                continue
            conflict_keys.add(key)
        else:
            seen_numbers[key] = sig
        kept.append(inv)
    if conflict_keys:
        kept = [inv for inv in kept
                if _identity(inv) is None or _identity(inv) not in conflict_keys]
    # A group that ends up quarantined was not "counted once" - the conflict
    # warning below owns its story.
    dupes = sum(n for key, n in dupe_counts.items() if key not in conflict_keys)
    if dupes:
        warnings.append(
            f"{dupes} duplicate bill(s) - same customer, bill number, amount and due date - "
            "were counted once, not twice."
        )
    conflict_warning = ""
    if conflict_keys:
        details = []
        for key in sorted(conflict_keys)[:3]:
            versions = sorted(
                {(inv.amount, inv.due_date) for inv in invoices if _identity(inv) == key},
                key=lambda v: (v[0], v[1] or date.min),
            )
            vs = " vs ".join(
                f"{amt:,.2f} due {due.isoformat() if due else 'no due date'}"
                for amt, due in versions[:4]
            )
            details.append(f"bill number {original_numbers[key]}: {vs}")
        shown = "; ".join(details)
        more = f" and {len(conflict_keys) - 3} more" if len(conflict_keys) > 3 else ""
        conflict_warning = (
            f"{len(conflict_keys)} bill number(s) have conflicting records ({shown}{more}). "
            "It is not clear whether each is one bill or two, so none of those rows are "
            "counted in the totals or scheduled for chasing. Fix the amounts, dates or bill "
            "numbers and run again to include them."
        )
        warnings.append(conflict_warning)
    invoices = kept

    if not invoices:
        if conflict_warning:
            raise ParseError(conflict_warning)
        raise ParseError("No rows had a usable amount. Check the amount column and try again.")
    return invoices, warnings


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
def analyse(invoices: list[Invoice], today: date | None = None,
            bank_rate: float | None = None) -> dict[str, Any]:
    """bank_rate is the RBI Bank Rate as a percentage. Pass None to switch the
    MSMED statutory-interest calculation off entirely (non-India users)."""
    today = today or date.today()

    unconfirmed = [i for i in invoices if i.due_date is None or i.date_source != "column"]
    for inv in invoices:
        if inv.due_date is None or inv.date_source != "column":
            # Unknown or unconfirmed due date: unknown stays unknown. No lateness,
            # tier, probability or cost of waiting is derived from it, and no chase
            # draft is built for the row (build_messages skips tier-less rows).
            inv.days_overdue = None
            inv.bucket = "No confirmed due date"
            inv.tier = ""
            inv.probability = None
            inv.expected_value = None
            inv.slip_30d = None
            inv.statutory_interest = 0.0
            continue
        inv.days_overdue = (today - inv.due_date).days
        inv.bucket = bucket_for(inv.days_overdue)
        inv.tier = tier_for(inv.days_overdue)
        inv.probability = recovery_probability(inv.days_overdue)
        inv.expected_value = round(inv.amount * inv.probability, 2)
        # The number that makes people act: value destroyed by waiting one more month.
        p_later = recovery_probability(inv.days_overdue + 30)
        inv.slip_30d = round(inv.amount * (inv.probability - p_later), 2)
        inv.statutory_interest = (
            msmed_interest(inv.amount, inv.days_overdue, bank_rate) if bank_rate else 0.0
        )

    # Overdue always outranks not-yet-due; within that, rank by the money you
    # lose by waiting another 30 days. That deliberately surfaces mid-age
    # invoices sitting right above the 90-day collectability cliff.
    ranked = sorted(
        invoices,
        key=lambda i: (0 if (i.days_overdue or 0) > 0 else 1, -(i.slip_30d or 0.0), -i.amount),
    )
    for pos, inv in enumerate(ranked, start=1):
        inv.rank = pos

    total = round(sum(i.amount for i in invoices), 2)
    overdue = [i for i in invoices if (i.days_overdue or 0) > 0]
    total_overdue = round(sum(i.amount for i in overdue), 2)
    expected = round(sum(i.expected_value or 0.0 for i in invoices), 2)
    cost_of_waiting = round(sum(i.slip_30d or 0.0 for i in invoices), 2)

    buckets = []
    for name, lo, hi in BUCKETS:
        rows = [i for i in invoices if i.days_overdue is not None and lo <= i.days_overdue <= hi]
        amt = round(sum(i.amount for i in rows), 2)
        if not rows:
            continue
        mid = -15 if hi < 0 else min((max(lo, 0) + min(hi, 365)) // 2, 365)
        buckets.append({
            "bucket": name,
            "count": len(rows),
            "amount": amt,
            "share": round(amt / total * 100, 1) if total else 0.0,
            "probability": round(recovery_probability(mid) * 100),
        })

    if unconfirmed:
        unconfirmed_amt = round(sum(i.amount for i in unconfirmed), 2)
        buckets.append({
            "bucket": "No confirmed due date",
            "count": len(unconfirmed),
            "amount": unconfirmed_amt,
            "share": round(unconfirmed_amt / total * 100, 1) if total else 0.0,
            "probability": None,
        })

    by_customer: dict[str, dict[str, Any]] = {}
    for inv in invoices:
        c = by_customer.setdefault(inv.customer, {
            "customer": inv.customer, "amount": 0.0, "count": 0,
            "oldest_days": inv.days_overdue or 0, "slip_30d": 0.0,
            "email": "", "phone": "",
        })
        c["amount"] = round(c["amount"] + inv.amount, 2)
        c["count"] += 1
        c["slip_30d"] = round(c["slip_30d"] + (inv.slip_30d or 0.0), 2)
        c["oldest_days"] = max(c["oldest_days"], inv.days_overdue or 0)
        c["email"] = c["email"] or inv.email
        c["phone"] = c["phone"] or inv.phone
    customers = sorted(by_customer.values(), key=lambda c: -c["amount"])
    for c in customers:
        c["share"] = round(c["amount"] / total * 100, 1) if total else 0.0

    dated = [i for i in invoices if i.days_overdue is not None]
    dated_total = sum(i.amount for i in dated)
    weighted_days = (
        round(sum(i.amount * max(i.days_overdue, 0) for i in dated) / dated_total, 1)
        if dated_total else 0.0
    )
    top_share = customers[0]["share"] if customers else 0.0

    risks: list[str] = []
    if top_share >= 40:
        risks.append(
            f"{customers[0]['customer']} alone is {top_share}% of everything you are owed. "
            "That is a lot riding on one customer."
        )
    old_amt = sum(i.amount for i in invoices if (i.days_overdue or 0) > 90)
    if old_amt > 0 and total:
        risks.append(
            f"{round(old_amt / total * 100)}% of your book is past 90 days, where the generic aging "
            "heuristic assumes collection odds fall sharply (not validated on your customers). Chase or decide. Do not drift."
        )
    if unconfirmed:
        risks.append(
            f"{len(unconfirmed)} invoice(s) have no confirmed due date. Nothing is known "
            "about their lateness, no reminders are scheduled for them, and they are left "
            "out of the recovery estimates. Add due dates to see their real risk."
        )
    if not overdue and not unconfirmed:
        risks.append("Nothing is overdue yet. Send the pre-due nudges below and keep it that way.")
    no_contact = sum(1 for i in invoices if not i.email and not i.phone)
    if no_contact:
        risks.append(
            f"{no_contact} invoice(s) have no email or phone on file. "
            "You cannot chase what you cannot reach. Fix your master data first."
        )

    return {
        "generated_on": today.isoformat(),
        "invoice_count": len(invoices),
        "customer_count": len(customers),
        "total_outstanding": total,
        "total_overdue": total_overdue,
        "overdue_count": len(overdue),
        "expected_recoverable": expected,
        "at_risk": round(total - expected, 2),
        "cost_of_waiting_30d": cost_of_waiting,
        "statutory_interest_total": round(sum(i.statutory_interest for i in invoices), 2),
        "bank_rate": bank_rate,
        "statutory_rate": round(MSMED_MULTIPLIER * bank_rate, 2) if bank_rate else None,
        "ranking_basis": "Ordered by how much each bill costs you if you wait another 30 days.",
        "weighted_avg_days_overdue": weighted_days,
        "concentration_top_customer": top_share,
        "buckets": buckets,
        "customers": customers[:25],
        "risks": risks,
        "priority": [
            {
                **{k: v for k, v in asdict(i).items() if k not in ("due_date", "due_date_raw")},
                "due_date": i.due_date.isoformat() if i.due_date else None,
                "probability": round(i.probability * 100) if i.probability is not None else None,
            }
            for i in ranked
        ],
        "assumptions": {
            "curve": [
                {"days_past_due": max(d, 0), "collected": round(p * 100)}
                for d, p in RECOVERY_CURVE
            ],
            "note": (
                "Recovery percentages are standard commercial aging benchmarks applied to your "
                "amounts, not a prediction about your specific customers. Your own history will "
                "differ. Use the ranking, not the decimal places."
            ),
            "msmed": {
                "enabled": bool(bank_rate),
                "bank_rate": bank_rate,
                "statutory_rate": round(MSMED_MULTIPLIER * bank_rate, 2) if bank_rate else None,
                "note": (
                    "Under Section 16 of the MSMED Act, 2006 a buyer who pays a registered micro "
                    "or small enterprise late owes compound interest at three times the RBI Bank "
                    "Rate, with monthly rests. Section 15 caps the agreed credit period at 45 days. "
                    "This is an estimate for your own planning, not legal advice, and it only "
                    "applies if you are registered on Udyam. Confirm the current Bank Rate and "
                    "your registration status with your CA before claiming a figure."
                ),
            },
        },
    }
