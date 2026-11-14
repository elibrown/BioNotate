"""
Video upload route:  POST /api/video

Receives a video (plus an optional astronaut_id), saves it in
backend/uploads/ under a unique name, runs the model and returns the result.
"""

import shutil
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.models.video_model import run_model

BACKEND_DIR = Path(__file__).resolve().parents[2]   # .../backend
UPLOAD_DIR = BACKEND_DIR / "uploads"                 # where videos are saved
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}

router = APIRouter(prefix="/api", tags=["video"])


@router.post("/video")
def upload_video(
    file: UploadFile = File(...),
    astronaut_id: str | None = Form(None),   # optional
):
    """Receive a video, save it, run the model, return the result."""
    extension = Path(file.filename or "").suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Please upload a video file ({', '.join(sorted(ALLOWED_EXTENSIONS))}).",
        )

    # Unique file name so two uploads never overwrite each other.
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    saved_name = f"{timestamp}_{uuid.uuid4().hex[:8]}{extension}"
    saved_path = UPLOAD_DIR / saved_name

    with saved_path.open("wb") as out_file:
        shutil.copyfileobj(file.file, out_file)

    result = run_model(saved_path)

    return {
        "astronaut_id": astronaut_id,
        "filename": file.filename,
        "saved_as": saved_name,
        "result": result,
    }
