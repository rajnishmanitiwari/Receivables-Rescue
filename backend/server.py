"""Receivables Rescue API. All routes are prefixed /api for platform ingress."""
from __future__ import annotations

import logging
import os
import re
import sys
from datetime import date, datetime, timezone

# Robust against being launched from any working directory.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except Exception:
    pass

from fastapi import APIRouter, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import engine
import extract
import llm
import messages as msg
import followup_planner as fp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("receivables")

app = FastAPI(title="Receivables Rescue API", version="1.0.0")
# Browser access defaults to the known production frontends; CORS_ORIGINS can
# widen or narrow it per deployment. This is an origin check, not rate limiting.
_DEFAULT_ORIGINS = (
    "https://duerise.vercel.app,"
    "https://receivables-rescue.vercel.app,"
    "http://localhost:3000,http://localhost:8090"
)
# Simple abuse cap: fixed-window per client IP. On serverless this is per
# instance, so it blunts bursts rather than guaranteeing a global limit.
_hits: dict[str, list[float]] = {}


def _client_ip(request: Request) -> str:
    # Vercel's edge overwrites X-Forwarded-For with the real client IP and does not
    # forward client-sent values (anti-spoofing, per the official request-headers
    # docs), so it is trusted only when x-vercel-id shows the request really came
    # through Vercel. Off Vercel, use the direct peer. When nothing reliable
    # exists, everyone shares the "unknown" bucket - the cap still applies.
    if request.headers.get("x-vercel-id"):
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    if request.url.path.startswith("/api/") and request.method != "OPTIONS":
        import time

        limit = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "60"))
        ip = _client_ip(request)
        now = time.time()
        window = _hits.setdefault(ip, [])
        window[:] = [t for t in window if now - t < 60.0]
        if len(window) >= limit:
            return JSONResponse(
                {"detail": "Too many requests. Try again in a minute."}, status_code=429
            )
        window.append(now)
        if len(_hits) > 10000:  # keep the map bounded
            _hits.clear()
    return await call_next(request)


# CORS is added last so it is the OUTERMOST middleware: preflight OPTIONS is
# answered (and never counted) here, and every response - including a 429 from
# the rate limiter - carries the CORS headers.
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", _DEFAULT_ORIGINS).split(","),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# MSMED interest is off: its applicability and formula are not verified against the Act and
# notified rules. Set ENABLE_MSMED_INTEREST=1 only after that review.
INTEREST_ENABLED = os.environ.get("ENABLE_MSMED_INTEREST") == "1"

api = APIRouter(prefix="/api")

# --- Mongo is used ONLY for an anonymous aggregate counter. No invoice data,
# --- no customer names, no amounts per user are ever written. See /api/stats.
_db = None
try:
    from motor.motor_asyncio import AsyncIOMotorClient

    _mongo_url = os.environ.get("MONGO_URL")
    if _mongo_url:
        _client = AsyncIOMotorClient(_mongo_url, serverSelectionTimeoutMS=3000)
        _db = _client[os.environ.get("DB_NAME", "receivables_rescue")]
except Exception as exc:  # pragma: no cover
    logger.warning("Mongo unavailable, running stateless: %s", exc)


class WaitlistRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=160)


class AnalyseRequest(BaseModel):
    data: str = Field(..., min_length=1, max_length=400_000)
    currency: str = Field("INR", max_length=4)
    sender_name: str = Field("", max_length=80)
    company_name: str = Field("", max_length=80)
    tone: str = Field("professional and direct", max_length=60)
    language: str = Field("English", max_length=40)
    # None switches the MSMED statutory-interest calculation off (non-India users).
    bank_rate: float | None = Field(None, ge=0, le=25)


@api.get("/health")
async def health():
    try:
        import pymupdf  # noqa: F401
        pdf_ok = True
    except Exception:
        pdf_ok = False
    return {
        "status": "ok",
        "llm": llm.is_enabled(),
        "vision": extract.vision_enabled(),
        "pdf": pdf_ok,
        "upload": globals().get("UPLOAD_ENABLED", False),
        "max_upload_mb": extract.MAX_BYTES // (1024 * 1024),
        "db": _db is not None,
        "default_bank_rate": None,
        "time": datetime.now(timezone.utc).isoformat(),
    }


@api.get("/stats")
async def stats():
    """Anonymous, aggregate-only social proof."""
    if _db is None:
        return {"runs": 0, "recoverable_found": 0, "currency": "INR"}
    try:
        doc = await _db.counters.find_one({"_id": "global"}) or {}
        return {
            "runs": int(doc.get("runs", 0)),
            "recoverable_found": float(doc.get("recoverable_found", 0)),
            "currency": "INR",
        }
    except Exception:
        return {"runs": 0, "recoverable_found": 0, "currency": "INR"}


@api.post("/analyse")
async def analyse(req: AnalyseRequest):
    try:
        invoices, warnings = engine.parse_invoices(req.data, today=date.today())
    except engine.ParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("parse failure")
        raise HTTPException(status_code=422, detail="Could not read that file. Check the format and try again.") from exc

    report = engine.analyse(invoices, today=date.today(), bank_rate=req.bank_rate if INTEREST_ENABLED else None)
    followups = msg.build_messages(
        report["priority"],
        sender=req.sender_name,
        company=req.company_name,
        currency=req.currency,
        limit=10,
        statutory_rate=report.get("statutory_rate"),
    )
    if llm.is_enabled():
        followups = await llm.polish(followups, req.tone, req.language)

    if _db is not None and req.currency == "INR":
        try:
            await _db.counters.update_one(
                {"_id": "global"},
                {"$inc": {"runs": 1, "recoverable_found": report["expected_recoverable"]}},
                upsert=True,
            )
        except Exception:
            pass

    return {"report": report, "messages": followups, "warnings": warnings, "currency": req.currency}


@api.post("/waitlist")
async def waitlist(req: WaitlistRequest):
    """Capture interest for the upcoming AI auto-chase agent. Best-effort, no PII beyond email."""
    email = req.email.strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    if _db is None:
        raise HTTPException(status_code=503, detail="Sign-ups are not open yet; nothing was saved.")
    if _db is not None:
        try:
            await _db.waitlist.update_one(
                {"_id": email},
                {"$set": {"email": email, "created_at": datetime.now(timezone.utc).isoformat()}},
                upsert=True,
            )
        except Exception:
            logger.exception("waitlist write failed")
    return {"ok": True}


def _register_upload_route() -> bool:
    """Register the file-upload route defensively.

    FastAPI asserts that python-multipart is installed at ROUTE DEFINITION time,
    not at request time. If that dependency ever fails to install, an unguarded
    route would take down the whole backend at import. Here, uploads simply
    switch off and the paste/CSV path keeps working. /api/health reports which.
    """
    try:
        api.add_api_route("/extract", extract_files, methods=["POST"])
        return True
    except Exception:
        logger.error("File uploads disabled: python-multipart is unavailable.")
        return False


async def extract_files(files: list[UploadFile] = File(...)):
    """Read invoices out of PDFs, photos or spreadsheets.

    Always returns rows for the user to review and correct — extraction is a
    starting point, never the final word.
    """
    if not files:
        raise HTTPException(status_code=422, detail="No files were uploaded.")
    if len(files) > 12:
        raise HTTPException(status_code=422, detail="Up to 12 files at a time.")
    rows: list[dict] = []
    notes: list[str] = []
    for f in files:
        try:
            blob = await f.read()
        except Exception:
            notes.append(f"{f.filename}: could not be read.")
            continue
        try:
            out = await extract.extract_file(f.filename or "file", blob)
        except Exception:
            logger.exception("extract failure for %s", f.filename)
            notes.append(f"{f.filename}: could not be read.")
            continue
        rows.extend(out.get("rows", []))
        if out.get("note"):
            notes.append(out["note"])
    return {"rows": rows, "notes": notes, "vision": extract.vision_enabled()}


UPLOAD_ENABLED = _register_upload_route()

class PlanEventIn(BaseModel):
    day: date
    type: str = Field(..., pattern="^(sent|reply|payment)$")
    text: str | None = Field(None, max_length=2000)   # reply text; classified by a keyword baseline
    label: str | None = None                         # or pass an explicit label
    promise_date: date | None = None
    amount: float | None = Field(None, ge=0)
    tier: str | None = None


class PlanRequest(BaseModel):
    number: str = Field(..., max_length=60)
    amount: float = Field(..., gt=0)
    due: date
    status: str = Field("open", pattern="^(open|void|paid)$")
    today: date | None = None
    events: list[PlanEventIn] = Field(default_factory=list, max_length=200)


@api.post("/next-action")
async def next_action(req: PlanRequest):
    """Deterministic follow-up decision prototype. Sends nothing; the caller decides."""
    evs = []
    for e in req.events:
        label = None
        flags = frozenset()
        if e.type == "reply":
            try:
                label = fp.Label(e.label) if e.label else fp.classify_reply(e.text or "")
            except ValueError:
                raise HTTPException(422, "unknown label")
            if e.text:
                flags = fp.reply_flags(e.text)
            elif label == fp.Label.DONT_CONTACT:
                flags = frozenset({"optout"})
            elif label == fp.Label.DISPUTE:
                flags = frozenset({"dispute"})
        evs.append(fp.Event(e.day, e.type, label, e.promise_date, e.amount, e.tier, flags))
    inv = fp.Invoice(req.number, req.amount, req.due, req.status)
    a = fp.next_action(inv, evs, req.today or date.today())
    return {"kind": a.kind.value, "reason": a.reason, "tier": a.tier,
            "until": a.until.isoformat() if a.until else None, "prototype": True}


app.include_router(api)


@app.get("/")
async def root():
    return {"service": "Receivables Rescue", "docs": "/docs", "api": "/api/health"}


@app.get("/health")
async def health_probe():
    return {"status": "ok"}
