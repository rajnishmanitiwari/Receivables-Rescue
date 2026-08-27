# Receivables Rescue — PRD

## Problem Statement
Deployment engineering task on an already-working Receivables Rescue app (FastAPI + React + optional MongoDB). Configure env, install deps, start services, verify tests, verify primary user journey, fix only production blockers.

## Architecture
- Backend: FastAPI + Uvicorn (Python 3.11), `/app/backend/server.py`, all routes `/api`, runs on 0.0.0.0:8001 (supervisor).
- Frontend: React 18 (react-scripts 5), `/app/frontend`, port 3000 (supervisor). Uses `REACT_APP_BACKEND_URL`.
- Store: MongoDB — anonymous aggregate counter only. App runs even if `MONGO_URL` is unset.

## Deployment Work Done (2026-01)
- Created `/app/backend/.env` from `.env.example` with `MONGO_URL=mongodb://localhost:27017`, `DB_NAME=receivables_rescue`, `CORS_ORIGINS=*`, LLM keys left blank (templates used).
- Created `/app/frontend/.env` with `REACT_APP_BACKEND_URL=https://4a56c5bd-e19e-4e94-a8b1-af95e96fb132.preview.emergentagent.com`.
- Installed backend deps (`pip install -r requirements.txt`) and frontend deps (`yarn install`).
- Restarted backend and frontend via supervisor. Both RUNNING.
- Ran `python test_engine.py` — **8/8 tests passed**.
- Verified `/api/health` returns `{status:ok, llm:false, db:true}` and `/api/analyse` returns full report.
- Primary user journey verified end-to-end via browser: home loads → "Use sample data" → "Show me the money" → 3 stat cards render (₹13,51,750 / ₹9,66,203 / ₹1,40,870) → 5 aging bars → 8 chase rows → expanding a row shows email subject/body and WhatsApp message.
- `deployment_agent` check: **PASS** — no hardcoded secrets, env wiring correct, CORS ok, supervisor config valid, no destructive DB ops.

## Out of Scope (Not Changed)
No auth, no payments, no analytics, no refactors, no copy/style/business logic changes.

## Backlog
None from this task. App is production-ready.
