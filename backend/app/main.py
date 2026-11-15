import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.data import management
from app.routers import audio, dashboard, measurements, predictions, video, research

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Bootstrap production data and import the packaged biology metrics idempotently.
    added = management.initialize()
    if added:
        logging.getLogger("uvicorn.error").info("Database initialization: %s", added)
    yield


app = FastAPI(
    title="AstroHealth API",
    description="Astronaut health monitoring and early risk detection",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(video.router)
app.include_router(audio.router)
app.include_router(predictions.router)
app.include_router(measurements.router)
app.include_router(dashboard.router)
app.include_router(research.router)
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
app.mount("/ui-assets", StaticFiles(directory=FRONTEND_DIR.parent / "data" / "ui"), name="ui-assets")


@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "service": "astro-health-backend",
        "version": "0.1.0",
    }


@app.get("/", include_in_schema=False)
def dashboard_page():
    """Crew health dashboard."""
    return FileResponse(FRONTEND_DIR / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/upload", include_in_schema=False)
def upload_page():
    return FileResponse(FRONTEND_DIR / "upload.html")

@app.get("/audio", include_in_schema=False)
def audio_page():
    return FileResponse(
        FRONTEND_DIR / "audio.html",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/measurements", include_in_schema=False)
def measurements_page():
    return FileResponse(FRONTEND_DIR / "manual_metrics.html", headers={"Cache-Control": "no-cache"})
