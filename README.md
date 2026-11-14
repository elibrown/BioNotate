# astro-health-monitor

Astronaut health monitoring and early risk detection platform for NASA Space Apps Challenge 2026.

## Current implementation

The skeleton provides a FastAPI backend and a plain HTML upload page. The current flow is:

```text
Browser → POST /api/video → save file → video processor → run_model() → JSON response
```

- `GET /` serves the upload page.
- `GET /api/health` returns service status and version.
- `GET /docs` provides interactive API documentation.
- `POST /api/video` accepts multipart `file` and optional `astronaut_id`. It checks the filename extension (`.mp4`, `.mov`, `.avi`, `.mkv`, `.webm`), saves the file under a generated name, and calls the placeholder model synchronously.
- The response includes `astronaut_id`, `filename`, `saved_as`, and `result`. The placeholder returns a fixed `normal` status, zero confidence, and video size; this is a dummy result, not a health assessment.

There is no frame extraction, face processing, or separate `/predict` endpoint yet. Predictions are saved to SQLite (see below). Upload validation currently checks extensions only; content validation, size limits, retention, and retry handling remain to be implemented.

## Processing skeleton: factory and strategies

The factory selects a processor; the processor handles transformation for that data type.

```text
Caller chooses data type
          ↓
ProcessorFactory.get_processor("video" / "audio" / "metrics")
          ↓
VideoProcessor / AudioProcessor / MetricsProcessor
          ↓
processor.process(data)
```

All three processors currently return their input unchanged. They provide a place to add transformations once we choose models. There are no request wrappers, data-type enums, injected adapters, or processing-specific validation yet.

**Video is connected:** `POST /api/video` saves the uploaded file, selects the video processor, passes the saved path through it, then passes its output to the existing placeholder `run_model()`. The response format is unchanged. Audio and metrics have skeleton processors but no endpoints or model integration yet.

```python
from app.processing import ProcessorFactory

processor = ProcessorFactory().get_processor("metrics")
result = processor.process({"heart_rate": 72})
# For now: {"heart_rate": 72}
```

Unsupported data types raise `ValueError`. The input and output formats of each processor can be defined when its real transformation is implemented. Video currently accepts and returns a saved file path because that is what the existing model expects.

### Food for thought: separate endpoints

We could eventually expose `/api/video`, `/api/audio`, and `/api/metrics`. Each endpoint would know the data type and select its processor internally. The client would not need to send a `modality` or `data_type` field. Only `/api/video` exists today; the others are ideas for future integration.

From `backend/`, run the processing tests:

```bash
.venv/bin/python -m unittest discover -s tests -p test_processing.py -v
```

To debug, set breakpoints in the factory or processors, then right-click `backend/tests/test_processing.py` in PyCharm and choose **Debug**. The same file serves testing and debugging.

## Running the backend


You need Python 3.10 or newer. From the repo folder:

```bash
cd backend
python -m venv .venv
# Windows:      .venv\Scripts\activate
# Linux/macOS:  source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then open http://127.0.0.1:8000 for the upload page, or
http://127.0.0.1:8000/docs for the interactive API docs.

### Video upload: `POST /api/video`

Send a video as form data. `astronaut_id` is optional.

```bash
curl -F "file=@clip.mp4" -F "astronaut_id=A-07" http://127.0.0.1:8000/api/video
```

The video is saved in `backend/uploads/` (not committed to git) and the
model result comes straight back as JSON. The model is a placeholder for now:
replace `run_model()` in `backend/app/models/video_model.py` with the real one.

### Saved predictions, measurements and alerts

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


## Implementation plan

The target pipeline accepts video, audio, or metrics, selects a processing strategy, prepares model input, and requests a prediction from the model service. The model and its preprocessing requirements are still being evaluated. The diagram below describes the target architecture. The current skeleton connects video upload to a pass-through video processor and a placeholder model in one FastAPI backend. Audio and metrics processors are skeletons; real transformations, the separate prediction endpoint, and the database are not implemented.

### System design

![System design: client data passes through ingestion and modality-specific transformation to model prediction, with future database persistence.](docs/diagrams/system-design.svg)

1. **Client:** submits video, audio, or metrics. The current UI/API accepts video only; audio and metrics ingestion are future additions.
2. **Ingestion service:** determines the data type, potentially from separate endpoints, validates the supported format and size, and assigns a request ID that follows the data through the pipeline.
3. **Transformer:** uses the factory to select a video, audio, or metrics strategy. Each strategy will prepare model input; currently all three pass their input through unchanged. Possible steps include frame extraction, face detection or recognition, cropping, and normalization. The exact steps and output format depend on model selection; face recognition is not yet a requirement.
4. **Model service:** exposes a proposed `POST /predict` endpoint, validates the transformed input, runs inference, and returns a prediction associated with the request ID.
5. **Prediction database (future):** the model service will persist prediction results and relevant metadata. The database technology and schema remain undecided.

The transformer should isolate model-specific preprocessing from ingestion. Its output contract must be agreed with the model service once a model is chosen. These are logical boundaries; separate deployment of each component is still an open decision.

### Decisions to resolve before implementation

- Select the model, prediction targets, and required input/output schemas.
- Choose video upload versus streaming, supported formats, duration and size limits.
- Decide whether ingestion passes video bytes or a reference to stored video, and define raw-video retention and access rules.
- Choose synchronous processing versus asynchronous jobs. For jobs, define status tracking and how clients retrieve results.
- Define the prediction request/response contract, including request ID, model version, and error responses.
- Define timeout and retry behavior, including how duplicate requests avoid duplicate predictions or database records.
- Choose the prediction database and define the persistence schema and failure behavior.

### Suggested implementation order

1. Agree on input/output formats for each data type and decide whether to add separate endpoints.
2. Extend the connected video processing path and add audio/metrics ingestion when needed.
3. Select a model and implement its preprocessing adapter and inference.
4. Add prediction persistence, then verify the full flow and failure handling with a representative video fixture.

## Repository structure

```text
astro-health-monitor/
├── .gitignore
├── README.md
├── backend/
│   ├── requirements.txt              # Python dependency pins
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                   # FastAPI app, health route, upload page
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   └── video.py              # POST /api/video and file storage
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   └── video_model.py        # Placeholder run_model()
│   │   └── processing/              # Video connected to upload route
│   │       ├── __init__.py
│   │       ├── factory.py            # Select processor by data type
│   │       └── strategies.py         # Base class and three pass-through processors
│   ├── tests/
│   │   └── test_processing.py
│   └── uploads/
│       └── .gitkeep                  # Uploaded files are ignored
├── frontend/
│   ├── .gitkeep
│   └── index.html                    # Browser upload form
├── data/
│   └── sample/
│       └── .gitkeep                  # Placeholder for sample data
└── docs/
    ├── .gitkeep
    └── diagrams/
        └── system-design.svg         # Target architecture
```

Keep source files, `requirements.txt`, Python package markers (`__init__.py`), and the architecture diagram in Git. `.gitkeep` files preserve otherwise empty directories; they can be removed once those directories contain tracked files.

Local PyCharm settings (`.idea/`), virtual environments (`.venv/`), Python caches, environment secrets, and uploaded videos are ignored by the root `.gitignore`. Ignoring a file does not untrack it if it has already been committed or staged.

Future transformer and model-service boundaries should grow from this skeleton. Their runtime, deployment layout, prediction contract, and database remain undecided.


## Cardiorespiratory Monitoring

AstroHealth integrates `cardioresp` v0.2.0 to estimate
cardiorespiratory measurements from prerecorded face videos.

### Supported measurements

- **Heart Rate (HR):** Estimated beats per minute.
- **Respiratory Rate (RR):** Estimated breaths per minute.
- **Pulse-Respiration Quotient (PRQ):** HR divided by RR.

All three measurements are derived from the same analysis
window, avoiding timestamp alignment between separate models.

### Model installation

Requirements:
- Python 3.11 or newer
- A supported OpenCV video decoder

The model wheel is included in `backend/vendor/`.

From the `backend` directory:

```bash
python -m pip install -r requirements.txt
```

The installation includes cardioresp, NumPy, SciPy,
scikit-learn and OpenCV.

### Running the backend

From `backend/`:

```bash
python -m uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/ to upload a video.

### Video upload API

**Endpoint:** `POST /api/video`

**Content type:** `multipart/form-data`

Parameters:
- `file` (required): Video recording
- `astronaut_id` (optional): Identifier for the astronaut

The backend saves the recording, selects VideoProcessor
through ProcessorFactory, and calls the cardioresp model.

### Recording requirements

- Duration: At least 30 seconds; 60+ seconds recommended
- Frame rate: At least 15 FPS; 30 FPS recommended
- Resolution: At least 640x480 recommended
- One seated person facing the camera
- Stable lighting and minimal movement

The first 30 seconds are used for warm-up.

### API response

The response contains:

- `model`: cardioresp
- `model_version`: 0.2.0
- `status`: Status of the latest reading
- `hr_bpm`: Latest heart-rate estimate
- `respi_rate`: Latest respiratory-rate estimate
- `prq`: Latest HR/RR quotient
- `summary`: Recording-level median estimates
- `measurements`: Timestamped readings and their statuses

The `summary` contains median HR and RR estimates from
successful readings and calculates PRQ from those medians.
It also reports the number of valid readings.

Reading statuses:
- `warming_up`: Not enough data collected yet
- `ok`: HR, RR and PRQ produced
- `partial`: HR available, RR/PRQ unavailable
- `no_face`: Face detection unsuccessful

Invalid recordings return HTTP 422 with a descriptive error.

### Running tests

From `backend/`:

```bash
python -m pip install pytest
python -m pytest -v
```

### Important accuracy limitations

This is an experimental prototype, not a medical device.

The model developer's UBFC-rPPG evaluation reported:
- HR MAE: 0.95 BPM on DATASET_1
- HR MAE: 2.73 BPM on DATASET_2
- RR MAE: 3.65 breaths/min on DATASET_1

Respiratory-rate estimation did not outperform a
constant-mean baseline (3.53 breaths/min MAE).
Consequently, RR and PRQ are not sufficiently validated
for medical decisions.

The model has not been validated on astronauts, in
microgravity, or under International Space Station
lighting conditions.

A status of `ok` indicates successful computation,
not verified clinical accuracy.
