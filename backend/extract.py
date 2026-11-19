"""
Turn an uploaded invoice into rows without requiring an API key.

Order of attack, cheapest first:
  1. PDF text layer + deterministic field patterns.  Free, instant, no network.
  2. Vision model, only for scans and phone photos where step 1 finds nothing.

Whatever comes back is always shown to the user for review before it is used.
We never silently trust an extraction.
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
from datetime import date, timedelta
from typing import Any

import httpx

import engine

# 4 MB keeps uploads inside Vercel's 4.5 MB serverless request-body cap,
# which this repo also ships a config for. Container hosts allow more;
# raise MAX_UPLOAD_MB if you only ever deploy to one.
MAX_BYTES = int(os.environ.get("MAX_UPLOAD_MB", "4")) * 1024 * 1024
MAX_PAGES = 12
THIN_TEXT_CHARS = 120  # below this per page, assume it is a scan


# ---------------------------------------------------------------------------
# Deterministic patterns
# ---------------------------------------------------------------------------
RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
RE_PHONE = re.compile(r"(?:\+?\d{1,3}[\s-]?)?(?:\(?\d{2,5}\)?[\s-]?)?\d{5}[\s-]?\d{5}|\+?\d{10,13}")
RE_GSTIN = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][A-Z0-9]Z[A-Z0-9]\b")
# The label must be on the same line as the value, and the value must contain a
# digit, otherwise "TAX INVOICE\nSharma Textiles" reads as invoice number "Sharma".
RE_INV_NO = re.compile(
    r"(?:invoice|inv|bill|document)[ \t]*(?:no\.?|number|#|id)[ \t]*[:#\-]?[ \t]*"
    r"([A-Za-z0-9][A-Za-z0-9/\-_]{2,28})", re.I)
RE_TERMS = re.compile(r"\b(?:net|terms?|credit period)\s*[:\-]?\s*(\d{1,3})\s*(?:days?)?\b", re.I)
RE_DUE = re.compile(r"(?:due\s*date|payment\s*due|due\s*on)\s*[:\-]?\s*([^\n]{4,32})", re.I)
RE_INVDATE = re.compile(r"(?:invoice\s*date|bill\s*date|date\s*of\s*issue|dated)\s*[:\-]?\s*([^\n]{4,32})", re.I)
RE_TOTAL = re.compile(
    r"(?:grand\s*total|total\s*payable|amount\s*payable|balance\s*due|amount\s*due|net\s*payable|total)"
    r"\s*[:\-]?\s*(?:rs\.?|inr|₹|\$|usd|€|£)?\s*([\d,.\s]{2,20})", re.I)
RE_BILLTO = re.compile(r"(?:bill(?:ed)?\s*to|buyer|customer|sold\s*to|to)\s*[:\-]?\s*\n?\s*([^\n]{2,80})", re.I)

_JUNK_LINE = re.compile(r"^\s*(?:gstin|pan|state|address|phone|email|tel|mobile)\b", re.I)


def _clean_name(s: str) -> str:
    s = re.sub(r"\s{2,}", " ", (s or "").strip(" :,-\t"))
    s = re.sub(r"\b(GSTIN|PAN)\b.*$", "", s, flags=re.I).strip()
    return s[:120]


def _first_date(text: str) -> date | None:
    for token in re.split(r"[,\n]", text):
        d = engine.parse_date(token.strip())
        if d:
            return d
    m = re.search(r"\d{1,4}[\s/.\-][A-Za-z0-9]{1,9}[\s/.\-]\d{2,4}", text)
    return engine.parse_date(m.group(0)) if m else None


def parse_invoice_text(text: str) -> dict[str, Any]:
    """Pull invoice fields out of a text layer. Returns whatever it is confident about."""
    out: dict[str, Any] = {"customer": "", "invoice_no": "", "amount": None,
                           "due_date": None, "email": "", "phone": "", "confidence": "low",
                           "date_assumed": False, "date_assumed_reason": ""}
    if not text or not text.strip():
        return out

    hits = 0

    for m in RE_INV_NO.finditer(text):
        cand = m.group(1).strip(" .,;:")[:60]
        if re.search(r"\d", cand):
            out["invoice_no"] = cand
            hits += 1
            break

    inv_date = None
    m = RE_INVDATE.search(text)
    if m:
        inv_date = _first_date(m.group(1))
    if inv_date is None:
        # Plenty of invoices just say "Date:". Fall back to that, then to the
        # first parseable date anywhere in the document.
        m = re.search(r"\bdate\b\s*[:\-]?\s*([^\n]{4,32})", text, re.I)
        if m:
            inv_date = _first_date(m.group(1))
    if inv_date is None:
        inv_date = _first_date(text)

    due = None
    m = RE_DUE.search(text)
    if m:
        span = m.group(1)
        # Same contract as the CSV path: a stated due date like 05/06/2026 in
        # a single document has nothing to settle day-first vs month-first,
        # and inference never confirms. It is kept as a visible day-first
        # guess held for confirmation. Same-day numerics (07/07/2026) read
        # identically both ways and stay confirmed.
        token = re.search(r"\d{1,2}\s*[/.\-]\s*\d{1,2}\s*[/.\-]\s*\d{2,4}", span)
        if token and engine._numeric_date_form(token.group(0)) == "ambiguous":
            due = engine._parse_numeric_convention(token.group(0), "dmy")
            if due:
                out["date_assumed"] = True
                out["date_assumed_reason"] = "ambiguous"
        else:
            due = _first_date(span)
    if due is None and inv_date is not None:
        t = RE_TERMS.search(text)
        # Stated credit terms are honoured as written: "Net 60" means 60 days,
        # never silently shortened. With no stated terms, fall back to a 45-day
        # estimate. Either way the date is computed, not stated: the review
        # screen asks the user to confirm it before it drives chasing.
        due = inv_date + timedelta(days=int(t.group(1)) if t else 45)
        out["date_assumed"] = True
        out["date_assumed_reason"] = "computed"
    if due:
        out["due_date"] = due.isoformat()
        hits += 1

    # Amount: prefer the largest value tagged as a total, since "Total" often
    # appears for subtotal lines too.
    best = None
    for m in RE_TOTAL.finditer(text):
        v = engine.parse_amount(m.group(1))
        if v and v > 0 and (best is None or v > best):
            best = v
    if best is None:
        nums = [engine.parse_amount(x) for x in re.findall(r"[\d][\d,]{3,}(?:\.\d{1,2})?", text)]
        nums = [n for n in nums if n and n > 0]
        best = max(nums) if nums else None
    if best:
        out["amount"] = round(best, 2)
        hits += 1

    m = RE_BILLTO.search(text)
    if m:
        cand = _clean_name(m.group(1))
        if not cand or _JUNK_LINE.match(cand):
            after = text[m.end():].splitlines()
            for line in after[:4]:
                c = _clean_name(line)
                if c and not _JUNK_LINE.match(c):
                    cand = c
                    break
        if cand:
            out["customer"] = cand
            hits += 1
    if not out["customer"]:
        for line in text.splitlines():
            c = _clean_name(line)
            if len(c) > 3 and not _JUNK_LINE.match(c) and not re.search(r"invoice|tax|bill", c, re.I):
                out["customer"] = c
                break

    m = RE_EMAIL.search(text)
    if m:
        out["email"] = m.group(0)[:120]
    m = RE_PHONE.search(text.replace("GSTIN", " "))
    if m:
        digits = re.sub(r"\D", "", m.group(0))
        if 10 <= len(digits) <= 13:
            out["phone"] = m.group(0).strip()[:40]

    out["confidence"] = "high" if hits >= 3 else "medium" if hits == 2 else "low"
    return out


# ---------------------------------------------------------------------------
# Vision fallback
# ---------------------------------------------------------------------------
VISION_PROMPT = (
    "You are reading a business invoice. Return JSON only, no prose, no markdown fence:\n"
    '{"invoices":[{"customer":"who owes the money (the bill-to / buyer, NOT the seller)",'
    '"invoice_no":"","amount":0,"due_date":"YYYY-MM-DD","invoice_date":"YYYY-MM-DD",'
    '"email":"","phone":""}]}\n'
    "amount = the final total payable including tax, as a plain number with no separators. "
    "If the due date is absent but there is an invoice date and payment terms, compute it. "
    "Use null for anything you cannot read. Never guess a number you cannot see."
)


def vision_enabled() -> bool:
    return bool(os.environ.get("LLM_API_KEY"))


async def extract_via_vision(images: list[bytes]) -> list[dict[str, Any]]:
    if not vision_enabled() or not images:
        return []
    base = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("LLM_VISION_MODEL") or os.environ.get("LLM_MODEL", "gpt-4o-mini")
    content: list[dict[str, Any]] = [{"type": "text", "text": VISION_PROMPT}]
    for img in images[:4]:
        content.append({
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64," + base64.b64encode(img).decode()},
        })
    async with httpx.AsyncClient(timeout=180) as client:
        r = await client.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {os.environ['LLM_API_KEY']}"},
            json={"model": model, "messages": [{"role": "user", "content": content}],
                  "max_tokens": 4096, "temperature": 0.1, "stream": False},
        )
        r.raise_for_status()
        raw = r.json()["choices"][0]["message"]["content"]
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    m = re.search(r"\{.*\}", raw, re.S)
    data = json.loads(m.group(0) if m else raw)
    rows = []
    for item in data.get("invoices", [])[:60]:
        amt = engine.parse_amount(item.get("amount"))
        due_raw, assumed = item.get("due_date"), False
        if not due_raw and item.get("invoice_date"):
            # An invoice date is not a due date: keep it visible but flagged so
            # the user confirms it in the review screen before it drives chasing.
            due_raw, assumed = item.get("invoice_date"), True
        rows.append({
            "customer": _clean_name(str(item.get("customer") or "")),
            "invoice_no": str(item.get("invoice_no") or "")[:60],
            "amount": round(amt, 2) if amt else None,
            "due_date": (engine.parse_date(due_raw).isoformat() if due_raw and engine.parse_date(due_raw) else None),
            "date_assumed": assumed,
            "email": str(item.get("email") or "")[:120],
            "phone": str(item.get("phone") or "")[:40],
            "confidence": "medium",
        })
    return [r for r in rows if r["amount"]]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
async def extract_file(filename: str, blob: bytes) -> dict[str, Any]:
    if len(blob) > MAX_BYTES:
        return {"rows": [], "note": (
            f"{filename} is too large. Keep each file under "
            f"{MAX_BYTES // (1024 * 1024)} MB. A phone photo at normal quality is fine.")}
    name = (filename or "file").lower()

    if name.endswith((".csv", ".tsv", ".txt")):
        try:
            invoices, warnings = engine.parse_invoices(blob.decode("utf-8", "ignore"))
        except engine.ParseError as exc:
            return {"rows": [], "note": f"{filename}: {exc}"}
        return {"rows": [{
            "customer": i.customer, "invoice_no": i.invoice_no, "amount": i.amount,
            "due_date": i.due_date.isoformat() if i.due_date else None,
            # Positional and ambiguous-format dates are both guesses the user
            # must confirm before they drive chasing. The reason lets the
            # review screen explain each guess accurately and drop the
            # explanation once that row is confirmed.
            "date_assumed": i.date_source in ("positional", "ambiguous"),
            "date_assumed_reason": i.date_source if i.date_source in ("positional", "ambiguous") else "",
            "email": i.email, "phone": i.phone, "confidence": "high",
        } for i in invoices], "note": "; ".join(warnings)}

    if name.endswith(".pdf"):
        try:
            import pymupdf
        except ImportError:
            return {"rows": [], "note": "PDF support is not installed on the server."}
        try:
            doc = pymupdf.open(stream=blob, filetype="pdf")
        except Exception:
            return {"rows": [], "note": f"{filename} could not be opened as a PDF."}
        pages = list(doc)[:MAX_PAGES]
        text = "\n".join(p.get_text() for p in pages)
        if len(text.strip()) >= THIN_TEXT_CHARS:
            row = parse_invoice_text(text)
            if row.get("amount"):
                row["source"] = filename
                return {"rows": [row], "note": ""}
        # scanned or unreadable: render and hand to vision
        if not vision_enabled():
            return {"rows": [], "note": (
                f"{filename} looks like a scan with no readable text, and no vision key is "
                "configured. Type the figures in by hand below.")}
        images = [p.get_pixmap(dpi=150).tobytes("png") for p in pages[:4]]
        try:
            rows = await extract_via_vision(images)
        except Exception as exc:
            return {"rows": [], "note": f"{filename}: could not read this scan ({type(exc).__name__})."}
        for r in rows:
            r["source"] = filename
        return {"rows": rows, "note": "" if rows else f"{filename}: nothing readable found."}

    if name.endswith((".png", ".jpg", ".jpeg", ".webp", ".heic")):
        if not vision_enabled():
            return {"rows": [], "note": (
                f"{filename} is a photo, which needs the vision key. "
                "Add LLM_API_KEY, or type the figures in by hand below.")}
        try:
            rows = await extract_via_vision([blob])
        except Exception as exc:
            return {"rows": [], "note": f"{filename}: could not read this photo ({type(exc).__name__})."}
        for r in rows:
            r["source"] = filename
        return {"rows": rows, "note": "" if rows else f"{filename}: nothing readable found."}

    return {"rows": [], "note": f"{filename}: unsupported file type. Use PDF, JPG, PNG or CSV."}
