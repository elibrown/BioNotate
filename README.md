# astro-health-monitor

Astronaut health monitoring and early risk detection platform for NASA Space Apps Challenge 2026.

## System design

### Dashboard

![Dashboard read path and planned database integration](docs/diagrams/dashboard-design.svg)

The browser polls `GET /api/dashboard` every 15 seconds. The API reads crew data through `CrewRepository`, evaluates metric/prediction rules and freshness, and returns crew status and alerts. By default the repository reads the SQLite database (`DatabaseCrewRepository`): the `astronauts` roster (filled from `data/astronauts.json` on first run) and the readings saved from uploaded videos. Set `ASTROHEALTH_DASHBOARD=demo` to show the JSON demo files instead (`DemoCrewRepository`).

### Video / data upload

![Target multimodal upload and prediction pipeline](docs/diagrams/system-design.svg)

This is the target upload architecture. Currently `/upload` calls the existing `POST /api/video`: check filename extension → save video → select video processor → call `run_model()` → return cardioresp estimates for heart rate (HR), respiratory rate (RR), and pulse-respiration quotient (PRQ). All processing strategies currently pass input through unchanged; video is connected, while audio/metrics endpoints and a separate `/predict` service remain planned. The model returns latest HR/RR/PRQ, timestamped measurements, and recording-level median summaries. Invalid recordings return HTTP 422. Recordings need a visible frontal face, stable lighting, minimal movement, and at least 30 seconds of usable video (60+ recommended). This experimental model is not validated for medical decisions, astronauts, or microgravity; `ok` means computation succeeded. Uploaded results are saved to the database and appear on the dashboard on its next refresh. Both flows run in one FastAPI app, with sidebar links between dashboard and upload.

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

Open http://127.0.0.1:8000/. This starts both the API and UI. From `backend/`, install pytest with `python -m pip install pytest`, then run `python -m pytest -v` for all tests.

## Demo data and status rules

`data/astronauts.json` contains profiles, `metrics.json` contains timestamped readings/history, and `predictions.json` contains synthetic model scores. Records join by astronaut ID. Files reload on each API request; `rules.json` configures inclusive metric ranges, prediction thresholds, and freshness duration.

- **Needs attention:** a metric is outside its range or a prediction meets/exceeds its threshold.
- **Unknown:** no alert, but required metrics are missing or observations are stale.
- **Healthy:** required metrics are fresh/present and no rule triggers. These are illustrative demo rules, not a clinical assessment.

The demo clock is the latest fixture timestamp. Member details show trends, predictions, and alert reasons. Alerts are calculated on request; saved alert history and external notifications remain future work. Astronaut IDs are provided by demo records or entered manually on upload; automatic identity recognition is not implemented.

## Dashboard class relationships

```mermaid
classDiagram
    class CrewRepository {
        <<interface>>
        list_crew()
    }
    CrewRepository <|.. DemoCrewRepository
    CrewRepository --> CrewMember : returns
    CrewMember "1" *-- "0..*" Metric
    CrewMember "1" *-- "0..*" Prediction
```

## Prediction storage (SQLite)

Everything is stored in one SQLite file, `backend/astrohealth.db` (created on
first use, not committed to git; set `ASTROHEALTH_DB` to use another path).
All database code is in `backend/app/db.py`. There are two tables:

- **predictions**: one row per model run (e.g. one uploaded video). It keeps
  the model's full output as JSON, its `model`, `status`, and whether it is an
  alert. This is what the UI shows as status and alerts.
- **measurements**: every reading, for charts and trend analysis. Each row is
  one value: astronaut, `source`, `metric`, value, unit, time. Each model has
  its own metrics, so `source` is the model name (e.g. `cardioresp`) and
  `metric` is its field (e.g. `hr_bpm`). Values entered by hand, e.g. a lab
  result, have `source = "manual"` and no `prediction_id`.

After each model run, `backend/app/extractors.py` picks the readings out of the
model output. For `cardioresp` it saves every reading with status `ok` or
`partial`: `hr_bpm`, `respi_rate` and `prq` (a 60 s video gives about 30
readings x 3 metrics). `warming_up` and `no_face` readings have no values and
are skipped. A reading's time is the upload time plus its `timestamp_s`
(stored as `offset_s`); approximate, since we don't know when the video was
recorded. A new model needs one small function in that file.

A prediction is an alert if the model returns `"alert": true`, or if the
**median** of a metric's readings in that video is outside its range in
`ALERT_RANGES` (`backend/app/db.py`). The median, so one noisy reading doesn't
raise an alert. Today the only range is cardioresp heart rate 40-120 bpm, a
placeholder until someone sets real limits. Respiratory rate has no range
because cardioresp's RR is not validated. The model `status` describes video
quality, not health, so it never triggers an alert; it is still saved so the
UI can say "retake the video".

| Endpoint | What it returns |
| --- | --- |
| `GET /api/predictions?astronaut_id=A-07&limit=50` | Model runs, newest first (omit `astronaut_id` for everyone) |
| `GET /api/predictions/{id}` | One model run, with its full output |
| `GET /api/alerts` | Alerts nobody has handled, newest first (`?astronaut_id=`, `?include_acknowledged=true`) |
| `POST /api/alerts/{id}/ack` | Marks an alert as handled |
| `GET /api/measurements?astronaut_id=A-07&source=cardioresp&metric=hr_bpm&since=2026-11-01` | Readings oldest first, ready for a chart (all filters optional, plus `prediction_id` for one video, `until`, `limit`) |
| `POST /api/measurements` | Add one value by hand (JSON: `astronaut_id`, `metric`, `value`, optional `unit`, `measured_at`, `source` (default `manual`)) |

A measurement looks like:

```json
{"id": 1, "astronaut_id": "A-07", "source": "cardioresp", "metric": "hr_bpm",
 "value": 71.8, "unit": "bpm", "measured_at": "2026-11-14T12:20:01.000+00:00",
 "offset_s": 30.0, "prediction_id": 1}
```

`POST /api/video` now also returns `prediction_id`, `created_at`, `is_alert`
and the `measurements` it saved.

Tests: from `backend/`, run `python -m pytest -q`.

If you ran an earlier version of this branch, delete `backend/astrohealth.db`
once; it will be recreated with the current tables.

The dashboard (`GET /api/dashboard`) reads this database through
`DatabaseCrewRepository` in `backend/app/dashboard/repository.py`. `DB_METRICS`
there maps each dashboard metric in `data/rules.json` to a stored
`(source, metric)`; today only `heart_rate` -> `("cardioresp", "hr_bpm")`.
Rule metrics with no mapping (e.g. `oxygen`) are not shown, and risk-score
predictions stay empty until a model produces scores. Note the dashboard's
alerts use the ranges in `data/rules.json`, separate from `ALERT_RANGES` above.

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
│   │   ├── main.py                 # FastAPI setup, pages, and static assets
│   │   ├── db.py                   # SQLite storage: predictions, measurements, alert rule
│   │   ├── extractors.py           # Model output -> measurement rows, per model
│   │   ├── dashboard/
│   │   │   └── repository.py       # Demo data models/reader; database handoff
│   │   ├── routers/
│   │   │   ├── dashboard.py        # Snapshot API and status/alert functions
│   │   │   ├── predictions.py      # Prediction history and alerts API
│   │   │   ├── measurements.py     # Measurements API (trends, manual entry)
│   │   │   └── video.py            # Video upload and analysis endpoint
│   │   ├── models/
│   │   │   └── video_model.py      # HR/RR/PRQ model adapter
│   │   └── processing/
│   │       ├── factory.py          # Select video/audio/metrics strategy
│   │       └── strategies.py       # Current pass-through processors
│   ├── tests/
│   │   ├── test_dashboard.py
│   │   ├── test_processing.py
│   │   └── test_video_model.py
│   └── uploads/                    # Runtime videos, ignored by Git
├── frontend/
│   ├── index.html                  # Crew dashboard and detail dialog
│   ├── dashboard.css               # Shared theme, sidebar, responsive layouts
│   ├── dashboard.js                # Polling, rendering, filters, member details
│   └── upload.html                 # Video form and analysis results
├── data/
│   ├── astronauts.json
│   ├── metrics.json
│   ├── predictions.json
│   └── rules.json
└── docs/diagrams/
    ├── dashboard-design.svg        # Dashboard read flow
    └── system-design.svg           # Target upload/prediction flow
```

Python package markers and empty-directory placeholders are omitted from the tree. Next decisions: model/preprocessing contracts, ingestion limits and retention, synchronous versus asynchronous prediction, and database persistence/retry behavior.

## Manual measurements

Use **Manual measurements** in the sidebar (`/measurements`) to record one metric at a time: systolic or diastolic blood pressure (mmHg), glucose (mg/dL), or temperature (°C). Choose an astronaut and collection time. Each value is saved as one SQLite measurement row with `source=manual` and shown in member details. Manual values do not change health status or trigger alerts yet.

`GET /api/measurement-catalog` lists supported fields/units; `POST /api/manual-measurements` validates and saves one metric/value. No device adapters or CSV imports are included.

Docker stores SQLite at `/app/storage/astrohealth.db` in the persistent `database` volume. Container rebuilds/recreation retain it; `docker compose down -v` deletes it. Venv uses its own `backend/astrohealth.db` file.
