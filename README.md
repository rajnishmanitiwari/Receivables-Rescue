# DueRise (formerly Receivables Rescue)

**Find the money your business is already owed.** Live at https://duerise.vercel.app (the older receivables-rescue.vercel.app address still works; the repo keeps its original name).

Add your unpaid bills as a PDF, a spreadsheet, or typed in. In one pass you get:

- how much is realistically collectable vs. already lost,
- how late each bill is, with the oldest and largest surfaced,
- a ranked chase list, ordered by urgency rather than by age alone,
- ready-to-send follow-ups (WhatsApp + email) that escalate correctly by tier,
- a rule-based helper that suggests the **next step per invoice** from what has
  happened (replies, payments, sends). It never sends anything.

No signup. No invoice data is stored.

---

## Design principles

Built for a small-business owner who is not technical, on a phone, in a hurry.

1. **The app is the first screen.** No marketing page, no login wall.
2. **Three visible steps**: add → check → act. You always know where you are.
3. **Nothing is trusted silently.** Whatever is read out of a file is shown in an
   editable table for review before any number is used.
4. **Plain words.** "Who owes you", "was due on", "12 days late", not
   "receivables ageing" or "DSO".
5. **It works with no API keys.** AI is an upgrade, never a dependency.

Type: Instrument Serif headings, Manrope body, both bundled as woff2 in the
repo, not fetched from a CDN, so the app renders correctly on networks that
block font CDNs. Palette: warm off-white `#fffdf8` / green `#16a34a` /
ink `#1c1917` / muted `#7d7469`.

## Stack

| Layer    | Tech                                        |
|----------|---------------------------------------------|
| Frontend | React 18 (react-scripts 5), plain CSS       |
| Backend  | FastAPI + Uvicorn (Python 3.11), PyMuPDF    |
| Store    | MongoDB, anonymous aggregate counter only   |

Backend routes are prefixed `/api` for platform ingress.
Frontend reads `process.env.REACT_APP_BACKEND_URL`.

## What works without any API key

- **PDF invoices with a text layer**: read by deterministic pattern matching in
  `backend/extract.py`. Handles Indian and US date and number formats, `Net 30`
  style terms, `Bill To` / `Buyer` blocks, GSTIN, email and phone.
- **CSV / TSV / pasted rows**: flexible header matching, no fixed column order.
- **Every calculation**: ageing, recovery curve, cost of waiting, concentration
  risk.
- **Every follow-up message**: built from templates, tiered by how late the bill is.

## What the optional AI key adds

- Reading **scanned PDFs and phone photos** of paper invoices (vision).
- Optionally rewriting the follow-ups in a different tone or language.

Any OpenAI-compatible endpoint works. Example, NVIDIA's hosted catalogue:

```
LLM_API_KEY=<your-nvidia-key>
LLM_BASE_URL=https://integrate.api.nvidia.com/v1
LLM_MODEL=moonshotai/kimi-k3
LLM_VISION_MODEL=moonshotai/kimi-k3
```

Verify the endpoint before relying on it:

```bash
curl -s https://integrate.api.nvidia.com/v1/chat/completions \
  -H "Authorization: Bearer $LLM_API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"moonshotai/kimi-k3","messages":[{"role":"user","content":"say ok"}],"max_tokens":5}'
```

If the key is absent or the call fails, the app falls back to templates and
deterministic parsing. It never breaks; it just does less.

## Run locally

```bash
cd backend && cp .env.example .env && pip install -r requirements.txt
uvicorn server:app --reload --port 8000

cd frontend && cp .env.example .env   # REACT_APP_BACKEND_URL=http://localhost:8000
npm install && npm start
```

## Tests

```bash
cd backend && python -m pytest -q    # 48 tests
```

Covers CSV/TSV/semicolon parsing, headerless positional fallback, Indian and US
number and date formats, missing dates, bad rows, recovery-curve monotonicity,
customer concentration, message tier assignment, the follow-up planner, its reply
classifier (with a pinned hard-case set), the next-action API, and honest defaults.

Verified: `CI=true npx react-scripts build` compiles with zero warnings; the full
journey (PDF upload → review → analysis → message) runs in a real browser with no
console errors and no horizontal overflow at 390px.

## API

| Route | Purpose |
|-------|---------|
| `GET /api/health` | `{status, llm, vision, pdf, db, default_bank_rate}` |
| `GET /api/stats` | anonymous aggregate run count |
| `POST /api/extract` | multipart upload → rows for review |
| `POST /api/analyse` | rows as CSV text → report + messages |
| `POST /api/next-action` | rule-based next-step suggestion per invoice (prototype; sends nothing) |

## How the numbers work

**Recovery curve.** A linearly interpolated commercial ageing curve (98% not yet
due → 8% at two years), shown to the user in the UI as an assumption rather than
hidden as a prediction.

**Chase order.** Ranked by cost of waiting:

```
slip_30d = amount x ( P(collect today) - P(collect in 30 days) )
```

This surfaces mid-age bills sitting just above the 90-day collectability cliff,
which is where money actually leaks, not the oldest bills, which are largely
already lost. Bills that are not yet due always rank below ones that are.

**MSMED statutory interest: currently disabled.** An experimental MSMED Act
late-payment interest estimate exists in the codebase but is switched off
(`ENABLE_MSMED_INTEREST` unset) until its applicability and formula are verified.
The UI shows no interest figures while it is off, and no interest clause is added
to messages.

## Limitations

Not legal, accounting or debt-collection advice. Recovery percentages are
industry ageing benchmarks, not a prediction about specific customers. The reply
classifier behind the follow-up helper is a keyword baseline (English only) and
can misread replies; ambiguous replies are routed to a human rather than chased.

## Security

No secrets are committed; only `.env.example` files, with empty values. Never
paste a live key into a repo, an issue, or a chat window. If one has been
exposed, rotate it at the provider before doing anything else.
