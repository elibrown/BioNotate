# astro-health-monitor

Astronaut health monitoring and early risk detection platform for NASA Space Apps Challenge 2026.

## System design

![Target processing pipeline](docs/diagrams/system-design.svg)

Today, FastAPI serves the dashboard and API together. Video upload uses a pass-through processor and an rPPG heart-rate estimator. The dashboard reads demo JSON files; Itamar is handling database work for users, metrics, and predictions. Model-specific preprocessing and database integration remain planned.

## Run with Docker

From the repository root with Docker running:

```bash
# Development: Python reload, mounted frontend and demo data
docker compose -f compose.yaml -f compose.dev.yaml up --build

# Production: source and demo files baked into the image, no reload
docker compose up --build -d
```

Open http://localhost:8000/ for the dashboard, `/upload` for video upload, or `/docs` for the API. No separate frontend server or build is needed. In development, Python changes reload automatically; refresh the browser after HTML/CSS/JS edits. Demo JSON changes appear on the next dashboard fetch (every 15 seconds). Rebuild after dependency changes; production requires rebuilding for all source/data changes.

Use one mode at a time. Stop development with Ctrl+C; run `docker compose down` to remove containers. Uploads persist in a named volume; `down -v` deletes them. View logs with `docker compose logs -f app`. The image runs as a non-root user with a `/api/health` health check.

If port 8000 is occupied, prefix the command with `APP_PORT=8001` and open http://localhost:8001/. PowerShell: set `$env:APP_PORT = "8001"` first. Inspect configuration with `docker compose config` (include both `-f` flags for development).

## Run without Docker

Python 3.11+ is required. From the repository root:

```bash
cd backend
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/. This starts both the API and UI. From `backend/`, run tests with `.venv/bin/python -m unittest discover -s tests -v`.

## Component details

- [Dashboard, demo data, rules, and database handoff](frontend/README.md)
- [Processing factory, strategies, and debugging](backend/app/processing/README.md)

Next decisions: model and preprocessing contracts, ingestion limits and retention, synchronous versus asynchronous prediction, and database persistence/retry behavior. Only video ingestion exists today; audio/metrics ingestion and a separate `/predict` service are planned. Upload validation currently checks filename extensions only.
