from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.routers import dashboard, measurements, predictions, video

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

app = FastAPI(
    title="AstroHealth API",
    description="Astronaut health monitoring and early risk detection",
    version="0.1.0",
)

app.include_router(video.router)
app.include_router(predictions.router)
app.include_router(measurements.router)
app.include_router(dashboard.router)
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.middleware("http")
async def prevent_stale_frontend(request, call_next):
    response = await call_next(request)
    if request.url.path in {"/", "/upload"} or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


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
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/upload", include_in_schema=False)
def upload_page():
    return FileResponse(FRONTEND_DIR / "upload.html")
