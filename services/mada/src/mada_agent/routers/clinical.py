"""Clinical API routes."""

from __future__ import annotations

import json

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import ValidationError

from ..agent_service import ClinicalAgent, MediaInput, QueueTimeout
from ..llm_client import LlmTimeout
from ..media import MediaError, decode_audio, prepare_image, wav_base64
from ..schemas import AnalyzeResponse, Conversation

router = APIRouter(prefix="/api/v1/clinical", tags=["clinical"])


def _agent(request: Request) -> ClinicalAgent:
    agent = getattr(request.app.state, "agent", None)
    if agent is None:
        raise HTTPException(503, "service is starting")
    return agent


async def _read_limited(f: UploadFile, limit: int, what: str) -> bytes:
    data = await f.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"{what} is larger than {limit // (1024 * 1024)} MB")
    return data


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    request: Request,
    conversation: str = Form(..., description="JSON: {\"turns\": [...]} — see docs/INTEGRATION.md"),
    image: UploadFile | None = File(None, description="Optional photo for the latest turn"),
    audio: UploadFile | None = File(None, description="Optional audio (≤30 s) for the latest turn"),
) -> AnalyzeResponse:
    agent = _agent(request)
    settings = agent.settings
    try:
        conv = Conversation.model_validate(json.loads(conversation))
    except json.JSONDecodeError as exc:
        raise HTTPException(422, f"conversation is not valid JSON: {exc.msg}") from exc
    except ValidationError as exc:
        raise HTTPException(422, json.loads(exc.json(include_url=False))) from exc

    media = MediaInput()
    try:
        if image is not None and image.filename:
            data = await _read_limited(image, settings.max_upload_bytes, "image")
            media.image_data_uri = prepare_image(data, image.content_type, settings.max_image_px)
        if audio is not None and audio.filename:
            data = await _read_limited(audio, settings.max_upload_bytes, "audio")
            wav, _secs = decode_audio(data, audio.content_type, settings.max_audio_s)
            media.audio_wav_b64 = wav_base64(wav)
    except MediaError as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc

    try:
        return await agent.assess(conv, media)
    except QueueTimeout as exc:
        raise HTTPException(503, str(exc), headers={"Retry-After": "5"}) from exc
    except LlmTimeout as exc:  # only raised if degradation itself failed
        raise HTTPException(504, str(exc)) from exc


@router.get("/protocols")
async def protocols(request: Request) -> dict:
    kb = _agent(request).kb
    return {
        "first_steps": list(kb.universal_first_steps),
        "protocols": [{"id": p.id, "title": p.title, "severity": p.severity, "steps": p.display_steps}
                      for p in kb.protocols.values()],
    }


@router.get("/checks")
async def checks(request: Request) -> dict:
    kb = _agent(request).kb
    return {"checks": [{"id": c.id, "title": c.title, "instruction": c.instruction, "status": c.status,
                        "source": c.source, "when": c.when, "answer": c.answer} for c in kb.checks.values()],
            "chest_pain_required_checks": list(kb.chest_pain_required_checks)}
