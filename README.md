# astro-health-monitor

Astronaut health monitoring and early risk detection platform for NASA Space Apps Challenge 2026.

## System design

### Dashboard

![Dashboard read path and planned database integration](docs/diagrams/dashboard-design.svg)

The browser polls `GET /api/dashboard` every 15 seconds. The API reads crew data through `CrewRepository`, evaluates metric/prediction rules and freshness, and returns crew status and alerts. By default the repository reads the SQLite database (`DatabaseCrewRepository`): the `astronauts` roster (filled from `data/astronauts.json` on first run) and the readings saved from uploaded videos. Set `ASTROHEALTH_DASHBOARD=demo` to show the JSON demo files instead (`DemoCrewRepository`).

### Video / data upload

![Target multimodal upload and prediction pipeline](docs/diagrams/system-design.svg)

Video upload calls `POST /api/video`, saves the recording, selects a processor, runs cardioresp (HR/RR/PRQ), and stores results in SQLite. Audio is storage-only; a separate `/predict` service remains planned. Video needs at least 30 seconds of usable face footage. Model output is experimental, not a clinical assessment.

## Run with Docker

From the repository root with Docker running:

```bash
# Development: Python reload, mounted frontend and demo data
docker compose -f compose.yaml -f compose.dev.yaml up --build

# Production: source and demo files baked into the image, no reload
docker compose up --build -d
```

Open http://localhost:8000/ for the dashboard, `/upload` for video upload, or `/docs` for the API. No separate frontend server or build is needed. In development, Python changes reload automatically; refresh the browser after HTML/CSS/JS edits. Demo JSON changes appear on the next dashboard fetch (every 15 seconds). Rebuild after dependency changes; production requires rebuilding for all source/data changes.

Use one mode at a time. Stop development with Ctrl+C; run `docker compose down` to remove containers. Uploads and SQLite persist in separate named volumes; `down -v` deletes both. View logs with `docker compose logs -f app`. The image runs as a non-root user with a `/api/health` health check.

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

Open http://127.0.0.1:8000/. This starts both the API and UI. From `backend/`, install pytest with `python -m pip install pytest`, then run `python -m pytest -v` for all tests.

## Data and rules

SQLite stores `astronauts`, `predictions` (model runs), and `measurements` (one metric observation per row). Docker uses a persistent `database` volume at `/app/storage/astrohealth.db`; venv defaults to `backend/astrohealth.db`. Override with `ASTROHEALTH_DB`. Team members' local databases are independent.

Dashboard status uses `data/rules.json`: out-of-range readings trigger attention; missing/stale data is unknown. Stored prediction alerts separately use `ALERT_RANGES` in `backend/app/db.py`. Limits are illustrative. Manual readings do not affect status yet.

## Dashboard class relationships

![Dashboard class relationships](docs/diagrams/dashboard-classes.svg)

## Pages and simulation

Sidebar pages: dashboard `/`, manual readings `/measurements`, video `/upload`, and audio `/audio`. Audio can be recorded/uploaded and stored (20 MiB maximum); audio analysis is not implemented.

Seed synthetic SQLite readings with `docker compose exec app python -m app.seed_demo`, or `python -m app.seed_demo` from `backend/` in a venv. Seeding is repeatable and preserves existing data. Simulation uses a labeled replay clock; real cardioresp readings switch the dashboard back to live time. `ASTROHEALTH_DASHBOARD=demo` instead reads JSON fixtures directly.

## Manual measurements and biomarker intake

Open **Manual measurements** in the sidebar to enter blood pressure, glucose, temperature, or other supported numeric readings. Each value is stored as one `measurements` row with astronaut ID, metric, unit, source, and collection time. Blood-pressure pairs save together.

- `GET /api/measurement-catalog`: supported groups, metric keys, and units.
- `POST /api/manual-measurements`: validated manual panel; `source=manual`.
- `POST /api/measurements`: numeric device input with an explicit `source`, metric, unit, and timestamp.

BM01–BM12 mappings are provisional in `backend/app/measurement_catalog.py`. Device adapters need confirmed payloads and units; the biologist's CSV has not been imported. Manual readings are displayed without new alert thresholds.

## Repository structure

```text
astro-health-monitor/
├── README.md                       # Setup, architecture, and demo behavior
├── Dockerfile                      # Production image, including cardioresp package
├── .dockerignore                   # Exclude local/private files from builds
├── compose.yaml                    # Production configuration and uploads volume
├── compose.dev.yaml                # Development source mounts and reload
├── backend/
│   ├── requirements.txt
│   ├── vendor/                     # Vendored cardioresp wheel
│   ├── app/
│   │   ├── seed_demo.py             # Explicit, repeatable SQLite simulation seed
│   │   ├── measurement_catalog.py  # Provisional biomarker groups and analyte units
│   │   ├── main.py                 # FastAPI setup, pages, and static assets
│   │   ├── db.py                   # SQLite storage: predictions, measurements, alert rule
│   │   ├── extractors.py           # Model output -> measurement rows, per model
│   │   ├── dashboard/
│   │   │   └── repository.py       # Demo data models/reader; database handoff
│   │   ├── routers/
│   │   │   ├── dashboard.py        # Snapshot API and status/alert functions
│   │   │   ├── predictions.py      # Prediction history and alerts API
│   │   │   ├── audio.py            # Audio storage endpoint (no model yet)
│   │   │   ├── measurements.py     # Trends, generic readings, validated manual panels
│   │   │   └── video.py            # Video upload and analysis endpoint
│   │   ├── models/
│   │   │   └── video_model.py      # HR/RR/PRQ model adapter
│   │   └── processing/
│   │       ├── factory.py          # Select video/audio/metrics strategy
│   │       └── strategies.py       # Current pass-through processors
│   ├── tests/
│   │   ├── test_manual_measurements.py
│   │   ├── test_dashboard.py
│   │   ├── test_processing.py
│   │   └── test_video_model.py
│   └── uploads/                    # Runtime videos, ignored by Git
├── frontend/
│   ├── index.html                  # Crew dashboard and detail dialog
│   ├── dashboard.css               # Shared theme, sidebar, responsive layouts
│   ├── measurements.html           # Manual measurement page
│   ├── audio.html                  # Audio upload / recording page
│   ├── audio.js                    # Microphone, preview, audio submission
│   ├── manual.js                   # Manual measurement form and saving
│   ├── dashboard.js                # Polling, rendering, filters, member details
│   └── upload.html                 # Video form and analysis results
├── data/
│   ├── astronauts.json
│   ├── metrics.json
│   ├── predictions.json
│   └── rules.json
└── docs/diagrams/
    ├── dashboard-classes.svg       # Repository and data-model relationships
    ├── dashboard-design.svg        # Dashboard read flow
    └── system-design.svg           # Target upload/prediction flow
```

Python package markers and empty-directory placeholders are omitted from the tree. Next decisions: model/preprocessing contracts, ingestion limits and retention, synchronous versus asynchronous prediction, and database persistence/retry behavior.
