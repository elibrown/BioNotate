"""HTTP bridge to the separate stateless MADA clinical-agent service.

Never expose the MADA base URL in browser code. The backend forwards a
bounded, patient-ID-verified snapshot of existing metrics alongside the
current assessment conversation, and optional current media. Never forward
real patient data without authenticated, authorized, private transport.
"""
from __future__ import annotations

import os

import httpx
from fastapi import HTTPException


def configured() -> bool:
    return bool(os.environ.get("MADA_SERVICE_URL", "").strip())


def enabled() -> bool:
    # Explicit opt-in: the current AstroHealth prototype has no user auth.
    # This gate prevents accidentally exposing sensitive assessment history on
    # the existing public Cloud Run deployment.
    return os.environ.get("MADA_DEMO_ENABLED") == "1"


def require_enabled() -> str:
    if not enabled():
        raise HTTPException(503, "MADA demo is disabled. Configure authentication before public deployment.")
    url = os.environ.get("MADA_SERVICE_URL", "").strip().rstrip("/")
    if not url:
        raise HTTPException(503, "MADA service is not configured (MADA_SERVICE_URL).")
    if not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(503, "MADA_SERVICE_URL must be an HTTP(S) address.")
    return url


async def request_mada(method: str, path: str, *, data=None, files=None) -> dict:
    url = require_enabled() + path
    # MADA can take up to 60 seconds to generate a response (or queue for 30).
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(100.0, connect=5.0), follow_redirects=False) as client:
            response = await client.request(method, url, data=data, files=files)
    except httpx.TimeoutException as exc:
        raise HTTPException(504, "MADA did not respond before the timeout.") from exc
    except httpx.RequestError as exc:
        raise HTTPException(503, "MADA service is unreachable.") from exc

    if response.status_code >= 400:
        # Do not expose upstream stack traces, URLs, or credentials.
        messages = {400: "MADA could not decode the media. Please retake it.",
                    413: "MADA rejected the media size or audio duration.",
                    415: "MADA does not support the uploaded media format.",
                    422: "MADA rejected the assessment format or check answers.",
                    503: "MADA is starting or busy. Please try again.",
                    504: "MADA could not finish its response."}
        code = response.status_code if response.status_code in messages else 502
        raise HTTPException(code, messages.get(response.status_code, "MADA returned an error."))
    try:
        result = response.json()
        if not isinstance(result, dict):
            raise ValueError("response isn't an object")
        return result
    except (ValueError, httpx.DecodingError) as exc:
        raise HTTPException(502, "MADA returned an invalid response.") from exc
