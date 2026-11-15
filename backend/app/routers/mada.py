"""MADA bridge, patient identity, follow-up turns and trend retrieval.

MADA is a SEPARATE model service. AstroHealth owns patient identity and
conversation/history storage. These demo endpoints require explicit opt-in;
use authentication and durable encrypted storage before real-world use.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from app import db, mada_client, mada_storage

router = APIRouter(prefix="/api", tags=["mada"])
MAX_MEDIA_BYTES = 10 * 1024 * 1024
ALLOWED_IMAGE = {"image/jpeg", "image/png", "image/webp", "image/heic"}
ALLOWED_AUDIO = {"audio/wav", "audio/x-wav", "audio/wave", "audio/webm",
                 "audio/ogg", "audio/mp4", "audio/mpeg", "audio/x-m4a"}


def _get_patient(patient_id: str) -> dict:
    patient = mada_storage.get_patient(patient_id)
    if not patient:
        raise HTTPException(422, "Choose an existing patient from the crew roster.")
    return patient


def _require_demo() -> None:
    if not mada_client.enabled():
        raise HTTPException(503, "MADA demo/history is disabled until access controls are configured.")


@router.get("/patients")
def patients():
    """Shared patient identities (never infer patient identity from responder)."""
    return mada_storage.list_registered_patients()


@router.get("/patients/{patient_id}/trends")
def trends(patient_id: str):
    patient = _get_patient(patient_id)
    return {"patient": patient, **mada_storage.patient_trends(patient_id)}


@router.get("/mada/status")
def status():
    return {"demo_enabled": mada_client.enabled(), "configured": mada_client.configured(),
            "note": "Prototype only; not validated for patient care."}


@router.get("/mada/checks")
async def check_catalog():
    return await mada_client.request_mada("GET", "/api/v1/clinical/checks")


@router.get("/mada/protocols")
async def protocol_catalog():
    return await mada_client.request_mada("GET", "/api/v1/clinical/protocols")


@router.get("/patients/{patient_id}/mada-assessments")
def patient_assessments(patient_id: str, limit: int = Query(15, ge=1, le=50)):
    _require_demo()
    _get_patient(patient_id)
    return mada_storage.list_assessments(patient_id, limit)


@router.get("/mada/assessments/{assessment_id}")
def assessment_detail(assessment_id: str):
    _require_demo()
    found = mada_storage.get_assessment(assessment_id)
    if not found:
        raise HTTPException(404, "Assessment not found.")
    return found


async def _media_part(file: UploadFile | None, what: str) -> tuple | None:
    if file is None or not file.filename:
        return None
    ctype = (file.content_type or "").split(";", 1)[0].strip().lower()
    allowed = ALLOWED_IMAGE if what == "image" else ALLOWED_AUDIO
    if ctype not in allowed:
        raise HTTPException(415, f"Unsupported {what} content type.")
    contents = await file.read(MAX_MEDIA_BYTES + 1)
    if not contents:
        raise HTTPException(400, f"The {what} file is empty.")
    if len(contents) > MAX_MEDIA_BYTES:
        raise HTTPException(413, f"The {what} file exceeds 10 MB.")
    return (file.filename, contents, ctype)


@router.post("/mada/assess")
async def assess(
    patient_id: str = Form(...),
    responder_id: str | None = Form(None),
    assessment_id: str | None = Form(None),
    text: str = Form(""),
    check_answers: str = Form("{}"),
    image: UploadFile | None = File(None),
    audio: UploadFile | None = File(None),
):
    mada_client.require_enabled()
    patient = _get_patient(patient_id)
    if not (0 < len(patient_id) <= 64) or (responder_id and len(responder_id) > 64):
        raise HTTPException(422, "Invalid patient or responder ID.")
    if len(text) > 4000 or len(check_answers) > 20000:
        raise HTTPException(422, "Assessment text or answers exceed the limit.")
    try:
        answers: Any = json.loads(check_answers)
    except json.JSONDecodeError as exc:
        raise HTTPException(422, "Check answers must be valid JSON.") from exc
    if not isinstance(answers, dict) or len(answers) > 50 or any(
        not isinstance(k, str) or len(k) > 80 for k in answers
    ):
        raise HTTPException(422, "Check answers must be an object keyed by check ID.")

    previous = None
    if assessment_id:
        previous = mada_storage.get_assessment(assessment_id)
        if not previous:
            raise HTTPException(404, "Assessment not found.")
        if previous["patient_id"] != patient_id:
            raise HTTPException(409, "Assessment belongs to a different patient.")
        if responder_id and responder_id != previous["responder_id"]:
            raise HTTPException(409, "Responder does not match the assessment.")
        responder_id = previous["responder_id"]
        if len(previous["turns"]) >= 39:
            raise HTTPException(422, "Maximum conversation length reached. Start a new assessment.")

    image_part = await _media_part(image, "image")
    audio_part = await _media_part(audio, "audio")
    if not text.strip() and not answers and image_part is None and audio_part is None:
        raise HTTPException(422, "Provide symptoms, a check answer, or an attachment.")

    responder_turn: dict = {
        "role": "responder",
        "timestamp": db.to_iso(datetime.now(timezone.utc)),
    }
    if text.strip():
        responder_turn["text"] = text.strip()
    if answers:
        responder_turn["check_answers"] = answers
    turns = [*previous["turns"], responder_turn] if previous else [responder_turn]

    # Server-side, authoritative patient context. The browser cannot submit
    # or alter readings belonging to a different crew member.
    context = mada_storage.patient_context(patient["id"])
    # Identity is established by the app, never guessed by the model.
    context["responder_is_patient"] = (responder_id == patient_id) if responder_id else None
    multipart_files = {}
    if image_part:
        multipart_files["image"] = image_part
    if audio_part:
        multipart_files["audio"] = audio_part
    response = await mada_client.request_mada(
        "POST", "/api/v1/clinical/analyze",
        data={"conversation": json.dumps({"turns": turns, "patient_context": context})},
        files=multipart_files or None,
    )
    if response.get("action") not in ("ask_checks", "finalize") or not isinstance(response.get("first_steps"), list):
        raise HTTPException(502, "MADA returned an invalid assessment structure.")

    # Store exactly the protocol IDs and check IDs MADA returned. The service
    # expects the full conversation on the next round.
    agent_turn = {
        "role": "agent",
        "timestamp": db.to_iso(datetime.now(timezone.utc)),
        "asked_check_ids": [c["id"] for c in response.get("next_checks", [])],
        "protocol_ids": [p["id"] for p in response.get("protocols", [])],
    }
    try:
        stored = mada_storage.save_assessment(
            patient_id=patient["id"], responder_id=responder_id,
            turns=[*turns, agent_turn], response=response, previous=previous,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"assessment_id": stored["id"], "patient": patient,
            "responder_id": responder_id, "assessment": response,
            "patient_context_metrics_sent": len(context["measurements"]),
            "saved_at": stored["updated_at"]}
