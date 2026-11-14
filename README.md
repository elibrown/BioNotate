# astro-health-monitor
Astronaut health monitoring and early risk detection platform for NASA Space Apps Challenge 2026.

## Running the backend (beginner guide)

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

Layout:

```
backend/app/main.py                ← creates the app, registers routers
backend/app/routers/video.py       ← POST /api/video
backend/app/models/video_model.py  ← run_model() (placeholder model)
backend/uploads/                   ← saved videos (git-ignored)
frontend/index.html                ← simple upload page served at /
```
