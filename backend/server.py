"""Receivables Rescue API. All routes are prefixed /api for platform ingress."""
from __future__ import annotations

import logging
import os
import sys
from datetime import date, datetime, timezone

# Robust against being launched from any working directory.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except Exception:
    pass

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import engine
import llm
import messages as msg

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("receivables")

app = FastAPI(title="Receivables Rescue API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
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


class AnalyseRequest(BaseModel):
    data: str = Field(..., min_length=1, max_length=400_000)
    currency: str = Field("INR", max_length=4)
    sender_name: str = Field("", max_length=80)
    company_name: str = Field("", max_length=80)
    tone: str = Field("professional and direct", max_length=60)
    language: str = Field("English", max_length=40)


@api.get("/health")
async def health():
    return {
        "status": "ok",
        "llm": llm.is_enabled(),
        "db": _db is not None,
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

    report = engine.analyse(invoices, today=date.today())
    followups = msg.build_messages(
        report["priority"],
        sender=req.sender_name,
        company=req.company_name,
        currency=req.currency,
        limit=10,
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


app.include_router(api)


@app.get("/")
async def root():
    return {"service": "Receivables Rescue", "docs": "/docs", "api": "/api/health"}
