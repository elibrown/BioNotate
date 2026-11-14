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

The initial pipeline accepts video from a client, transforms it into the input required by a model, and requests a prediction from the model service. The model and its preprocessing requirements are still being evaluated. The diagram below describes the target architecture. The current skeleton implements video upload and a direct call to a placeholder model in one FastAPI backend; the transformer, separate prediction endpoint, and database are not implemented.

### System design

![System design: client video passes through ingestion and transformation to model prediction, with future database persistence.](docs/diagrams/system-design.svg)

1. **Client:** captures or selects a video and submits it to the ingestion service. Video is the only input type in the initial scope.
2. **Ingestion service:** receives the video, validates the supported format and size, and assigns a request ID that follows the video through the pipeline.
3. **Transformer:** prepares the video for the selected model. Possible steps include frame extraction, face detection or recognition, cropping, and normalization. The exact steps and output format depend on model selection; face recognition is not yet a requirement.
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

1. Agree on an initial video submission contract and prediction contract using sample payloads.
2. Build an ingestion-to-transformer-to-model-service path with a placeholder transformer and stub predictions to validate integration.
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
│   │   └── models/
│   │       ├── __init__.py
│   │       └── video_model.py        # Placeholder run_model()
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
