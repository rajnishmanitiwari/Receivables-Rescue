"""Vercel Python serverless entrypoint.

Deploy the `backend/` directory as its own Vercel project (Root Directory =
`backend`). Vercel detects this `api/` folder, installs `requirements.txt`, and
serves the FastAPI app below. `backend/vercel.json` rewrites every path to here
so the existing `/api/...` routes keep working unchanged.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import app  # noqa: E402,F401  (exposed as the ASGI handler)
