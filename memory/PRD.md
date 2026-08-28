# Receivables Rescue — PRD

## Problem Statement
Indian and global small businesses are owed money they never systematically
chase. They are not spreadsheet-native, and existing receivables tools assume a
CRM, a login and an accountant. This app takes whatever the owner has — a photo
of an invoice, a PDF, a spreadsheet, or nothing but their memory — and returns
who to chase first, what waiting is costing them, what statutory interest they
are legally owed, and the message to send.

## Architecture
- Backend: FastAPI + Uvicorn (Python 3.11), `backend/server.py`, all routes
  under `/api`, port 8001 under supervisor.
- Vercel alternative: `backend/api/index.py` + `backend/vercel.json` expose the
  same ASGI app as a serverless function. Verified working — all four `/api`
  routes respond through that entrypoint.
- Frontend: React 18 (react-scripts 5), `frontend/`, port 3000 under
  supervisor. Uses `REACT_APP_BACKEND_URL`. Plain CSS, no UI framework.
- Store: MongoDB — anonymous aggregate counter only. App runs with `MONGO_URL`
  unset.

## Routes
| Route | Purpose |
|-------|---------|
| `GET /api/health` | `{status, llm, vision, pdf, upload, max_upload_mb, db, default_bank_rate}` |
| `GET /api/stats` | anonymous aggregate run count |
| `POST /api/extract` | multipart upload (PDF / image / CSV) -> rows for user review |
| `POST /api/analyse` | rows as CSV text -> report + follow-up messages |

## Design rules — do not violate these in future changes
1. The app is the first screen. No landing page, no login, no paywall.
2. Three visible steps: add -> check -> act.
3. Nothing extracted from a file is used until the user has seen it in the
   editable review table. Never analyse an extraction silently.
4. Plain words in the UI. "Who owes you", "was due on", "12 days late" —
   never "receivables ageing", "DSO" or "aged debtors".
5. The app must work with **no API keys and no database**. AI is an upgrade,
   never a dependency. Every AI path has a deterministic fallback.

## Calculations
- **Recovery curve**: linearly interpolated commercial ageing curve, 98% not yet
  due -> 8% at two years. Surfaced to the user as an assumption, not hidden.
- **Chase order**: `slip_30d = amount x (P(collect today) - P(collect in 30 days))`.
  Deliberately ranks mid-age bills above the oldest ones, because bills just
  above the 90-day cliff are where recoverable money is actually lost. Bills not
  yet due always rank last.
- **MSMED statutory interest** (INR only, opt-in): Section 16 of the MSMED Act,
  2006 — compound interest with monthly rests at 3x the RBI Bank Rate.
  `interest = amount x ((1 + 3r/1200) ^ (days_late / 30.4375) - 1)`.
  Bank Rate is a user-editable field defaulting to 5.50% (effective 5 Aug 2026).
  The clause is only added to a message past 45 days late and above 100 units.

## Work log

### 2026-08-28 (deployment) — Emergent
Env wiring, dependency install, supervisor restart, 8/8 tests passing, primary
journey verified, Vercel configs added, `deployment_agent` PASS.

### 2026-08-28 (feature merge)
- New `backend/extract.py`: reads invoices from PDF text layers using
  deterministic patterns (Indian + US date and number formats, `Net 45` terms,
  Bill-To blocks, GSTIN, email, phone). Vision model is a fallback for scans
  and photos only, and is optional.
- `POST /api/extract` added. Registered through `_register_upload_route()`,
  which is guarded: FastAPI asserts python-multipart at route-definition time,
  so an unguarded route would take down the entire backend if that dependency
  ever failed to install. Guarded, uploads simply switch off.
- MSMED statutory interest engine in `engine.py`, surfaced in the UI and woven
  into escalation and final-notice messages.
- Full UI rebuild: white, Source Serif 4 + IBM Plex Sans (bundled), #22c55e
  accent, three-step flow, editable review table.
- Tests: **13/13 passing** (was 8). Added coverage for invoice-text extraction
  across three real-world layouts, junk input, the heading-vs-invoice-number
  trap, MSMED interest math and monotonicity, and statutory-clause placement.
- `CI=true react-scripts build` compiles with zero warnings. Journey verified in
  a real browser: PDF upload -> review -> analysis -> message. No console
  errors, no horizontal overflow at 390 / 768 / 1440 px.

## Out of scope — do not add
Authentication, payments, subscriptions, admin panels, notifications, analytics
dashboards, social features, a UI component library, an animation runtime,
Gmail/Slack OAuth integrations. The app is deliberately dependency-light because
its users are on slow mobile connections.

### 2026-08-28 (github sync + redeploy) — Emergent
- Fetched and fast-forward merged latest `main` (48e81e6) from the connected
  GitHub repo (`rajnishmanitiwari/Receivables-Rescue`) into the workspace.
- Installed new deps: `python-multipart`, `pymupdf` (backend);
  `@fontsource/ibm-plex-sans`, `@fontsource/source-serif-4` (frontend).
- `test_engine.py`: **13/13 passing**. `GET /api/health` confirms `pdf:true`,
  `upload:true`. `POST /api/extract` route reachable (422 on empty file, as
  expected). Journey re-verified via screenshot: example bills -> review table
  -> "Show me who to chase" -> aging bars + MSMED interest card -> row expand.
- Added `GET /health` (plain, non-`/api`) in `server.py` returning `{"status":
  "ok"}` as a K8s liveness-probe safety net — `deployment_agent` flagged the
  probe hitting `/health` and getting 404 since only `/` and `/api/health`
  existed.
- `deployment_agent`: no blockers. Live production still shows 404 on
  `/health` because that reflects the **previous** deployment, before this
  fix — resolves once the app is redeployed.

## Backlog
- Verify the NVIDIA / Kimi vision endpoint against a real scanned invoice; it
  has not been exercised end to end.
- Consider raising `MAX_UPLOAD_MB` on container hosts (default 4 MB is a Vercel
  constraint, not an app one).
