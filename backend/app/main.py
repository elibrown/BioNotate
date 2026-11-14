from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.routers import audio, dashboard, measurements, predictions, video

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

app = FastAPI(
    title="AstroHealth API",
    description="Astronaut health monitoring and early risk detection",
    version="0.1.0",
)

app.include_router(video.router)
app.include_router(audio.router)
app.include_router(predictions.router)
app.include_router(measurements.router)
app.include_router(dashboard.router)
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


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


@app.get("/measurements", include_in_schema=False)
def measurements_page():
    return FileResponse(FRONTEND_DIR / "measurements.html", headers={"Cache-Control": "no-cache"})
