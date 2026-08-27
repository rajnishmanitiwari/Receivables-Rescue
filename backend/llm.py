"""
Optional LLM polish layer.

The app is fully functional without this file doing anything. If LLM_API_KEY is
set, one single batched call rewrites the generated follow-ups in the requested
tone/language. Any failure silently falls back to the deterministic templates.
"""
from __future__ import annotations

import json
import os
from typing import Any

import httpx

SYSTEM = (
    "You rewrite accounts-receivable follow-up messages for a small business owner. "
    "Keep every number, invoice reference, date and deadline exactly as given. "
    "Never invent facts, legal threats, interest charges or policies that were not "
    "in the original. Keep the same escalation level. Return valid JSON only."
)


def is_enabled() -> bool:
    return bool(os.environ.get("LLM_API_KEY"))


async def polish(messages: list[dict[str, Any]], tone: str, language: str) -> list[dict[str, Any]]:
    if not is_enabled() or not messages:
        return messages
    base = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
    payload = [
        {"i": n, "tier": m["tier"], "subject": m["subject"],
         "email": m["email"], "whatsapp": m["whatsapp"]}
        for n, m in enumerate(messages)
    ]
    prompt = (
        f"Rewrite each message in a {tone} tone, in {language}. "
        "Return JSON: {\"items\":[{\"i\":0,\"subject\":\"...\",\"email\":\"...\",\"whatsapp\":\"...\"}]}\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            r = await client.post(
                f"{base}/chat/completions",
                headers={"Authorization": f"Bearer {os.environ['LLM_API_KEY']}"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": SYSTEM},
                        {"role": "user", "content": prompt},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.4,
                },
            )
            r.raise_for_status()
            data = json.loads(r.json()["choices"][0]["message"]["content"])
        for item in data.get("items", []):
            idx = int(item.get("i", -1))
            if 0 <= idx < len(messages):
                for key in ("subject", "email", "whatsapp"):
                    if isinstance(item.get(key), str) and item[key].strip():
                        messages[idx][key] = item[key].strip()
    except Exception:
        return messages  # templates are always a valid answer
    return messages
