"""Store audio inputs; inference is not implemented yet."""
import uuid
from pathlib import Path
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from app.routers.video import UPLOAD_DIR

router = APIRouter(prefix="/api", tags=["audio"])
EXTENSIONS = {".wav", ".mp3", ".m4a", ".ogg", ".webm", ".flac", ".mp4"}
MAX_BYTES = 20 * 1024 * 1024


@router.post("/audio", status_code=201)
def upload_audio(file: UploadFile = File(...), astronaut_id: str | None = Form(None)):
    extension = Path(file.filename or "").suffix.lower()
    if extension not in EXTENSIONS:
        raise HTTPException(400, "Choose a WAV, MP3, M4A, OGG, WebM, FLAC or MP4 audio file.")
    path = UPLOAD_DIR / f"audio_{uuid.uuid4().hex}{extension}"
    size = 0
    try:
        with path.open("wb") as output:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise HTTPException(413, "Audio must be at most 20 MiB.")
                output.write(chunk)
        if not size:
            raise HTTPException(400, "The audio file is empty.")
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return {"status": "stored", "analysis_status": "not_implemented",
            "astronaut_id": astronaut_id, "saved_as": path.name, "size_bytes": size}
