"""
Voice recording route:  POST /api/audio

The astronaut records FIVE clips (see TASK_INSTRUCTIONS in
app/models/voice_model.py), sent together as five file fields:
counting_normal, counting_fast, vowel_a, vowel_e, vowel_o
(plus an optional astronaut_id).

We save the clips in their own folder, backend/uploads/<unique name>/, run
the voice model, store the prediction and its measurements in the database
(app/db.py) and return the result.

A recording the model rejects (too noisy, too short...) still returns 200:
check result["status"] ("ok" or "rejected") and result["advice"].
"""

import shutil
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app import db
from app.extractors import extract_measurements
from app.models.voice_model import (
    MAX_UPLOAD_BYTES,
    TASK_INSTRUCTIONS,
    TASKS,
    RecordingTooLong,
    UndecodableAudio,
    run_model,
)
from app.processing import ProcessorFactory

BACKEND_DIR = Path(__file__).resolve().parents[2]   # .../backend
UPLOAD_DIR = BACKEND_DIR / "uploads"                 # same folder as videos
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {".wav", ".webm", ".ogg", ".opus"}

router = APIRouter(prefix="/api", tags=["audio"])


@router.get("/audio/tasks")
def audio_tasks():
    """The five clips to record, in order, with what to say in each."""
    return [{"field": task, "instruction": TASK_INSTRUCTIONS[task]} for task in TASKS]


@router.post("/audio")
def upload_audio(
    counting_normal: UploadFile = File(..., description=TASK_INSTRUCTIONS["counting_normal"]),
    counting_fast: UploadFile = File(..., description=TASK_INSTRUCTIONS["counting_fast"]),
    vowel_a: UploadFile = File(..., description=TASK_INSTRUCTIONS["vowel_a"]),
    vowel_e: UploadFile = File(..., description=TASK_INSTRUCTIONS["vowel_e"]),
    vowel_o: UploadFile = File(..., description=TASK_INSTRUCTIONS["vowel_o"]),
    astronaut_id: str | None = Form(None),   # optional
):
    """Receive the five clips, save them, run the voice model, return the result."""
    files = dict(zip(TASKS, (counting_normal, counting_fast, vowel_a, vowel_e, vowel_o)))

    for task, upload in files.items():
        extension = Path(upload.filename or "").suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"{task}: please upload WAV, WebM or Ogg/Opus audio "
                       f"({', '.join(sorted(ALLOWED_EXTENSIONS))}).",
            )

    # One folder per recording, e.g. uploads/20261114-161200_ab12cd34/vowel_a.webm
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    folder_name = f"{timestamp}_{uuid.uuid4().hex[:8]}"
    folder = UPLOAD_DIR / folder_name
    folder.mkdir()

    processor = ProcessorFactory().get_processor("audio")
    clips, total_bytes = {}, 0
    try:
        for task, upload in files.items():
            path = folder / f"{task}{Path(upload.filename).suffix.lower()}"
            with path.open("wb") as out_file:
                shutil.copyfileobj(upload.file, out_file)
            total_bytes += path.stat().st_size
            if total_bytes > MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"The five clips are over {MAX_UPLOAD_BYTES // (1024 * 1024)} MB in total.",
                )
            clips[task] = processor.process(path)

        try:
            result = run_model(clips)
        except UndecodableAudio as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RecordingTooLong as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
    except HTTPException:
        # Request problem: don't keep clips we couldn't use.
        shutil.rmtree(folder, ignore_errors=True)
        raise

    saved = db.save_prediction(
        result,
        astronaut_id=astronaut_id,
        video_file=folder_name,   # the column holds any upload's name; here, the folder
        measurements=extract_measurements(result),
    )

    return {
        "prediction_id": saved["id"],
        "created_at": saved["created_at"],
        "is_alert": saved["is_alert"],
        "measurements": saved["measurements"],
        "astronaut_id": astronaut_id,
        "saved_as": folder_name,
        "result": result,
    }
