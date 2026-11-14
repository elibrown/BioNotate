# astro-health-monitor

Astronaut health monitoring and early risk detection platform for NASA Space Apps Challenge 2026.

## Current implementation

The skeleton provides a FastAPI backend and a plain HTML upload page. The current flow is:

```text
Browser → POST /api/video → backend/uploads/ → run_model(saved_path) → JSON response
```

- `GET /` serves the upload page.
- `GET /api/health` returns service status and version.
- `GET /docs` provides interactive API documentation.
- `POST /api/video` accepts multipart `file` and optional `astronaut_id`. It checks the filename extension (`.mp4`, `.mov`, `.avi`, `.mkv`, `.webm`), saves the file under a generated name, and calls the placeholder model synchronously.
- The response includes `astronaut_id`, `filename`, `saved_as`, and `result`. The placeholder returns a fixed `normal` status, zero confidence, and video size; this is a dummy result, not a health assessment.

There is no frame extraction, face processing, separate `/predict` endpoint, or prediction database yet. Upload validation currently checks extensions only; content validation, size limits, retention, and retry handling remain to be implemented.

## Modality processing: factory and strategies

`backend/app/processing/` adds an isolated processing layer for video, audio, and metrics. **It is not connected to the upload endpoint yet.** Existing routes, frontend, and model code are unchanged.

```text
InputData(request_id, modality, source, astronaut_id)
                         ↓
                 ProcessorFactory
                 ├── video   → VideoProcessor → injected video adapter
                 ├── audio   → AudioProcessor → injected audio adapter
                 └── metrics → MetricsProcessor → validated numeric values
                         ↓
          PredictionRequest(common envelope, modality-specific payload)
                         ↓
          Future prediction client / model service (not implemented)
```

The factory selects by explicit modality, not extension: WebM may contain video or audio. Every strategy implements `process(InputData) -> PredictionRequest`. `register()` can replace a strategy within one factory instance. Processing performs no inference, HTTP calls, or persistence and adds no dependencies.

| Strategy | Implemented | Still requires |
|---|---|---|
| Video | Validate local path, extension, file existence, and nonempty file; invoke injected adapter | Model-specific decoding, frame extraction, face processing, and features |
| Audio | Validate local path, extension, file existence, and nonempty file; invoke injected adapter | Model-specific decoding, resampling, and features |
| Metrics | Validate named finite numbers, reject booleans, copy values as floats | Agreed names, units, timestamps, and model-specific normalization |

Media validation does not inspect encoded content. Without a configured adapter, video and audio raise `NotImplementedError`. An adapter accepts a `Path` and returns a payload dictionary; its shape and serialization requirements must be agreed with the future prediction client. Metrics currently accept a flat mapping, not a time series.

Example, from `backend/` with the venv active:

```python
from app.processing import InputData, Modality, ProcessorFactory

factory = ProcessorFactory()
request = factory.get_processor(Modality.METRICS).process(
    InputData(
        request_id="req-001",
        modality=Modality.METRICS,
        source={"heart_rate": 72, "temperature": 36.5},
        astronaut_id="A-07",
    )
)
print(request.to_dict())
# {"request_id": "req-001", "modality": "metrics", "astronaut_id": "A-07",
#  "payload": {"metrics": {"heart_rate": 72.0, "temperature": 36.5}}}
```

Configure media with `ProcessorFactory(video_adapter=prepare_video, audio_adapter=prepare_audio)`. The caller supplies the request ID, selects a strategy, and passes `InputData`. Unsupported modalities and invalid inputs raise `ValueError`; adapter failures propagate. Future API integration must translate errors into HTTP responses.

Run processing tests from `backend/`:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

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


## Implementation plan

The target pipeline accepts video, audio, or metrics, selects a processing strategy, prepares model input, and requests a prediction from the model service. The model and its preprocessing requirements are still being evaluated. The diagram below describes the target architecture. The current skeleton implements video upload and a direct call to a placeholder model in one FastAPI backend; the processing factory exists as an unconnected package; media adapters, the separate prediction endpoint, and the database are not implemented.

### System design

![System design: client data passes through ingestion and modality-specific transformation to model prediction, with future database persistence.](docs/diagrams/system-design.svg)

1. **Client:** submits video, audio, or metrics. The current UI/API accepts video only; audio and metrics ingestion are future additions.
2. **Ingestion service:** receives data with an explicit modality, validates the supported format and size, and assigns a request ID that follows the video through the pipeline.
3. **Transformer:** uses the factory to select a video, audio, or metrics strategy. Each strategy prepares its own model-specific payload. Possible steps include frame extraction, face detection or recognition, cropping, and normalization. The exact steps and output format depend on model selection; face recognition is not yet a requirement.
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

1. Agree with the upload/model owners on modality-specific ingestion and prediction contracts.
2. Connect the isolated processing package at an agreed call site, then validate integration with a stub model service.
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
│   │   └── processing/              # Isolated; not connected to routes
│   │       ├── __init__.py
│   │       ├── contracts.py          # Envelopes and processor protocol
│   │       ├── factory.py            # Strategy selection and registration
│   │       └── strategies.py         # Video, audio, and metrics processing
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
