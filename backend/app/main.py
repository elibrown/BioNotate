from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from app import db
from app.routers import predictions, video

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

app = FastAPI(
    title="AstroHealth API",
    description="Astronaut health monitoring and early risk detection",
    version="0.1.0",
)

app.include_router(video.router)
app.include_router(predictions.router)

# Create the predictions table (backend/astrohealth.db) if it isn't there yet.
db.init_db()


@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "service": "astro-health-backend",
        "version": "0.1.0",
    }


@app.get("/", include_in_schema=False)
def upload_page():
    """Simple upload page (frontend/index.html)."""
    return FileResponse(FRONTEND_DIR / "index.html")
