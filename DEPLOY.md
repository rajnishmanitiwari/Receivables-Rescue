# Deploying Receivables Rescue

The repo is a monorepo: `frontend/` (React, CRA) and `backend/` (FastAPI).
Deploy them as **two projects** and point the frontend at the backend URL.

## Emergent / Railway / Render / any container host

Works as-is. Backend start command:

```bash
cd backend && pip install -r requirements.txt && uvicorn server:app --host 0.0.0.0 --port $PORT
```

Frontend: build `frontend/` with `npm run build`, serve `frontend/build`.
Set `REACT_APP_BACKEND_URL` to the backend's public URL before building.
All API routes are under `/api`, so ingress can route `/api/*` to the backend.

## Vercel

**Backend project**: Root Directory = `backend`. `backend/vercel.json` +
`backend/api/index.py` run the FastAPI app as a serverless function. No env
vars are required (Mongo and the LLM key are optional).

**Frontend project**: Root Directory = repo root (uses `vercel.json` here) or
`frontend/`. Add one env var:

```
REACT_APP_BACKEND_URL = https://<your-backend-project>.vercel.app
```

Redeploy the frontend after setting it (CRA inlines env vars at build time).

## Environment variables

See `backend/.env.example` and `frontend/.env.example`. Everything on the
backend is optional. The app is fully functional with nothing set.

## Dependencies added for invoice reading (2026-08-28)

`backend/requirements.txt` gained two packages:

| Package | Why | If it fails to install |
|---------|-----|------------------------|
| `python-multipart==0.0.20` | FastAPI needs it for `UploadFile` | `POST /api/extract` is not registered; the rest of the API is unaffected and the UI falls back to the paste box. `GET /api/health` reports `upload:false`. |
| `pymupdf==1.25.2` | Reads the text layer out of PDF invoices | PDF reading is skipped; `GET /api/health` reports `pdf:false`. CSV and pasted rows still work. |

Neither needs a system package on Linux. Both ship manylinux wheels, so
`.emergent/system_deps.txt` is unchanged.

`frontend/package.json` gained `@fontsource/source-serif-4` and
`@fontsource/ibm-plex-sans`. Fonts are bundled rather than fetched from Google
so the app renders on networks that block font CDNs. `package-lock.json` has
been regenerated, so `npm ci`, `npm install` and `yarn install` all resolve.

## Upload size

`POST /api/extract` accepts files up to **4 MB each**, which keeps requests
inside Vercel's 4.5 MB serverless body cap. On a container host (Emergent,
Railway, Render) there is no such cap. Raise it with:

```
MAX_UPLOAD_MB=12
```

`GET /api/health` reports the active limit as `max_upload_mb`.

## Optional AI

Nothing below is required. Without it the app reads text-layer PDFs, CSVs and
pasted rows deterministically and writes follow-ups from templates.

```
LLM_API_KEY=            # any OpenAI-compatible key
LLM_BASE_URL=https://integrate.api.nvidia.com/v1
LLM_MODEL=moonshotai/kimi-k3
LLM_VISION_MODEL=moonshotai/kimi-k3
```

Setting these adds one capability: reading **scanned PDFs and phone photos** of
paper invoices. `GET /api/health` reports `vision:true` when it is wired up.
