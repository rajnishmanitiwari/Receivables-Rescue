# Receivables Rescue

**Find the money your business is already owed.**

Paste your unpaid invoices (CSV, TSV, or just rows). In one pass you get:

- how much is realistically collectable vs. already lost,
- **how much you lose by waiting 30 more days** — the number that makes people act,
- a ranked chase list, ordered by cost of waiting rather than by age,
- ready-to-send follow-up messages (email + WhatsApp) that escalate correctly by tier.

No signup. No invoice data is stored.

---

## Stack

| Layer    | Tech                                   |
|----------|----------------------------------------|
| Frontend | React 18 (react-scripts 5), plain CSS  |
| Backend  | FastAPI + Uvicorn (Python 3.11)        |
| Store    | MongoDB — anonymous aggregate counter only |

All backend routes are prefixed `/api` for platform ingress routing.
The frontend calls `process.env.REACT_APP_BACKEND_URL`.

## Run locally

```bash
# backend
cd backend
cp .env.example .env
pip install -r requirements.txt
uvicorn server:app --reload --port 8000

# frontend (new terminal)
cd frontend
cp .env.example .env          # REACT_APP_BACKEND_URL=http://localhost:8000
npm install
npm start
```

## Tests

```bash
cd backend && python test_engine.py
```
8 tests cover CSV/TSV/semicolon parsing, headerless positional fallback,
Indian and US number and date formats, missing dates, bad rows, curve
monotonicity, concentration risk, and message tier assignment.

Verified: `CI=true npx react-scripts build` compiles with zero warnings.

## Environment

`backend/.env`

| Var | Required | Notes |
|-----|----------|-------|
| `MONGO_URL` | no | Anonymous counter only. App runs fine unset. |
| `DB_NAME` | no | Defaults to `receivables_rescue`. |
| `LLM_API_KEY` | no | Optional. Rewrites messages in a chosen tone/language. Without it, built-in templates are used and everything still works. |
| `LLM_BASE_URL` | no | OpenAI-compatible. Defaults to `https://api.openai.com/v1`. |
| `LLM_MODEL` | no | Defaults to `gpt-4o-mini`. |
| `CORS_ORIGINS` | no | Comma-separated. Defaults to `*`. |

`frontend/.env`

| Var | Required |
|-----|----------|
| `REACT_APP_BACKEND_URL` | yes |

No secrets are committed. Only `.env.example` files are in the repo.

## API

`GET /api/health` → `{status, llm, db, time}`

`GET /api/stats` → anonymous aggregate run count

`POST /api/analyse`
```json
{ "data": "Customer,Amount,Due Date\nAcme,425000,2026-04-21",
  "currency": "INR", "sender_name": "", "company_name": "" }
```
Returns `{ report, messages, warnings, currency }`.
Returns `422` with a human-readable `detail` on unparseable input.

## How the numbers work

Every figure is arithmetic on the user's own amounts, multiplied by a linearly
interpolated commercial aging curve (98% not-yet-due → 8% at two years). The
curve is shown to the user in the UI as an assumption, not hidden as a
prediction. Priority ranking uses **cost of waiting**:

```
slip_30d = amount × ( P(collect | today) − P(collect | 30 days later) )
```

This deliberately surfaces mid-age invoices sitting just above the 90-day
collectability cliff, which is where the real money leaks — not the oldest
invoices, which are largely already lost.

## Limitations

Not legal, accounting or debt-collection advice. The recovery percentages are
industry aging benchmarks, not a prediction about specific customers. Users
should rely on the ranking, not the decimal places.
