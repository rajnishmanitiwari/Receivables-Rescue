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

**Backend project** — Root Directory = `backend`. `backend/vercel.json` +
`backend/api/index.py` run the FastAPI app as a serverless function. No env
vars are required (Mongo and the LLM key are optional).

**Frontend project** — Root Directory = repo root (uses `vercel.json` here) or
`frontend/`. Add one env var:

```
REACT_APP_BACKEND_URL = https://<your-backend-project>.vercel.app
```

Redeploy the frontend after setting it (CRA inlines env vars at build time).

## Environment variables

See `backend/.env.example` and `frontend/.env.example`. Everything on the
backend is optional — the app is fully functional with nothing set.
