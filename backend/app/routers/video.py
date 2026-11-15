"""
Video upload routes.

Two ways to send a video:

1. POST /api/video
   One request with the whole file. Simple, but only works for small videos
   when the app runs on Google Cloud Run: Cloud Run refuses request bodies over
   32 MB, and Firebase Hosting cuts any request off after 60 seconds, while the
   model needs about 2 minutes for a 1 minute video.

2. Upload in pieces, then analyse in the background (what upload.html uses):
     POST /api/video/uploads                      -> {"upload_id", "chunk_size"}
     PUT  /api/video/uploads/{id}?offset=N        body = the next piece of the file
     POST /api/video/uploads/{id}/finish          -> starts the analysis
     GET  /api/video/jobs/{id}?wait=25            -> {"status": "processing" | "done" | "error"}
   The page keeps asking for the job status. Each status request waits up to
   25 s, so a request is almost always open while the model runs; Cloud Run
   only gives the app CPU time while it is answering a request.

   Pieces and jobs live on one server instance, which is why deploy.yml keeps
   --max-instances 1. If that instance restarts, the page tells the user to
   upload again.

Both ways save the video in backend/uploads/ under a unique name, run the
model, store the prediction in the database (app/db.py) and return the result.
"""

import os
import shutil
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from app import db
from app.extractors import extract_measurements
from app.models.video_model import run_model
from app.processing import ProcessorFactory

BACKEND_DIR = Path(__file__).resolve().parents[2]   # .../backend
UPLOAD_DIR = BACKEND_DIR / "uploads"                 # where videos are saved
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}

CHUNK_SIZE = 8 * 1024 * 1024          # 8 MB per piece, well under Cloud Run's 32 MB cap
MAX_VIDEO_BYTES = 500 * 1000 * 1000  # 500 MB; Cloud Run keeps files in its 2 GB of memory
MAX_WAIT_SECONDS = 25                 # under Firebase Hosting's 60 s request limit
FORGET_AFTER_SECONDS = 60 * 60        # drop finished or abandoned jobs after an hour
# On Cloud Run (which sets K_SERVICE) files live in memory and vanish on restart
# anyway, so delete each video once analysed to keep memory free.
DELETE_AFTER_ANALYSIS = bool(os.environ.get("K_SERVICE"))

router = APIRouter(prefix="/api", tags=["video"])


class VideoRejected(Exception):
    """The model could not use this recording (too short, too few fps, ...)."""


def check_extension(filename: str | None) -> str:
    extension = Path(filename or "").suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Please upload a video file ({', '.join(sorted(ALLOWED_EXTENSIONS))}).",
        )
    return extension


def new_saved_name(extension: str) -> str:
    """Unique file name so two uploads never overwrite each other."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{timestamp}_{uuid.uuid4().hex[:8]}{extension}"


def analyse_video(saved_name: str, astronaut_id: str | None, filename: str | None) -> dict:
    """Run the model on a saved video, store the prediction, return the response."""
    saved_path = UPLOAD_DIR / saved_name
    processor = ProcessorFactory().get_processor("video")
    processed_video = processor.process(saved_path)

    try:
        result = run_model(processed_video)
    except ValueError as exc:
        # The recording failed the model's input validation.
        # Don't keep a video that cannot be processed.
        saved_path.unlink(missing_ok=True)
        raise VideoRejected(str(exc)) from exc

    # Keep a record of every prediction, plus the health values it measured
    # (e.g. heart rate). See app/db.py and app/extractors.py.
    saved = db.save_prediction(
        result,
        astronaut_id=astronaut_id,
        video_file=saved_name,
        measurements=extract_measurements(result),
    )

    return {
        "prediction_id": saved["id"],
        "created_at": saved["created_at"],
        "is_alert": saved["is_alert"],
        "measurements": saved["measurements"],
        "astronaut_id": astronaut_id,
        "filename": filename,
        "saved_as": saved_name,
        "result": result,
    }


@router.post("/video")
def upload_video(
    file: UploadFile = File(...),
    astronaut_id: str | None = Form(None),   # optional
):
    """Receive a whole (small) video, save it, run the model, return the result."""
    saved_name = new_saved_name(check_extension(file.filename))
    with (UPLOAD_DIR / saved_name).open("wb") as out_file:
        shutil.copyfileobj(file.file, out_file)

    try:
        return analyse_video(saved_name, astronaut_id, file.filename)
    except VideoRejected as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Upload in pieces + background analysis
# ---------------------------------------------------------------------------

class UploadStart(BaseModel):
    filename: str
    size: int
    astronaut_id: str | None = None


# upload_id -> dict with the upload's details and, once finished, its job state.
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def _forget_old_jobs() -> None:
    cutoff = time.time() - FORGET_AFTER_SECONDS
    with _jobs_lock:
        for upload_id, job in list(_jobs.items()):
            if job["touched"] < cutoff:
                if job["status"] == "uploading":   # abandoned half-upload
                    (UPLOAD_DIR / job["saved_name"]).unlink(missing_ok=True)
                del _jobs[upload_id]


def _get_job(upload_id: str) -> dict:
    with _jobs_lock:
        job = _jobs.get(upload_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail="This upload is no longer on the server (it may have restarted). "
                   "Please upload the video again.",
        )
    job["touched"] = time.time()
    return job


@router.post("/video/uploads")
def start_upload(start: UploadStart):
    """Reserve a place for a video that will arrive in pieces."""
    extension = check_extension(start.filename)
    if start.size <= 0:
        raise HTTPException(status_code=400, detail="The video file is empty.")
    if start.size > MAX_VIDEO_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"The video is {start.size / 1e6:.0f} MB; the limit is "
                   f"{MAX_VIDEO_BYTES / 1e6:.0f} MB.",
        )
    _forget_old_jobs()

    upload_id = uuid.uuid4().hex
    saved_name = new_saved_name(extension)
    (UPLOAD_DIR / saved_name).touch()
    with _jobs_lock:
        _jobs[upload_id] = {
            "status": "uploading",
            "filename": start.filename,
            "size": start.size,
            "astronaut_id": (start.astronaut_id or "").strip() or None,
            "saved_name": saved_name,
            "touched": time.time(),
            "done": threading.Event(),
            "response": None,
            "error": None,
        }
    return {"upload_id": upload_id, "chunk_size": CHUNK_SIZE}


@router.put("/video/uploads/{upload_id}")
async def upload_piece(upload_id: str, offset: int, request: Request):
    """Write one piece of the video at the given byte offset.

    Sending a piece again (e.g. after a network hiccup) is safe: the file is
    cut back to the offset before writing.
    """
    job = _get_job(upload_id)
    if job["status"] != "uploading":
        raise HTTPException(status_code=409, detail="This upload is already finished.")

    body = await request.body()
    if len(body) > CHUNK_SIZE:
        raise HTTPException(status_code=413, detail="Piece is too large.")

    path = UPLOAD_DIR / job["saved_name"]
    current = path.stat().st_size
    if offset > current or offset + len(body) > job["size"]:
        raise HTTPException(
            status_code=409,
            detail=f"Expected the piece at byte {current}, got byte {offset}.",
        )
    with path.open("r+b") as out_file:
        out_file.truncate(offset)
        out_file.seek(offset)
        out_file.write(body)
    return {"received": offset + len(body)}


def _run_job(job: dict) -> None:
    try:
        job["response"] = analyse_video(job["saved_name"], job["astronaut_id"], job["filename"])
        job["status"] = "done"
    except VideoRejected as exc:
        job["error"] = str(exc)
        job["status"] = "error"
    except Exception as exc:  # noqa: BLE001 - report anything to the page
        job["error"] = f"The analysis failed: {exc}"
        job["status"] = "error"
    finally:
        if DELETE_AFTER_ANALYSIS:
            (UPLOAD_DIR / job["saved_name"]).unlink(missing_ok=True)
        job["touched"] = time.time()
        job["done"].set()


@router.post("/video/uploads/{upload_id}/finish")
def finish_upload(upload_id: str):
    """All pieces are in: start the analysis in the background."""
    job = _get_job(upload_id)
    if job["status"] != "uploading":
        return {"job_id": upload_id, "status": job["status"]}

    received = (UPLOAD_DIR / job["saved_name"]).stat().st_size
    if received != job["size"]:
        raise HTTPException(
            status_code=409,
            detail=f"Only {received} of {job['size']} bytes arrived. Please upload again.",
        )
    job["status"] = "processing"
    job["started"] = time.time()
    threading.Thread(target=_run_job, args=(job,), daemon=True).start()
    return {"job_id": upload_id, "status": "processing"}


@router.get("/video/jobs/{upload_id}")
def job_status(upload_id: str, wait: float = 0):
    """Report the analysis status, waiting up to `wait` seconds for it to finish."""
    job = _get_job(upload_id)
    if job["status"] == "processing":
        job["done"].wait(min(max(wait, 0), MAX_WAIT_SECONDS))
        job["touched"] = time.time()

    status = job["status"]
    if status == "done":
        return {"status": "done", **job["response"]}
    if status == "error":
        return {"status": "error", "detail": job["error"]}
    if status == "processing":
        return {"status": "processing", "elapsed_s": round(time.time() - job["started"])}
    return {"status": status}
