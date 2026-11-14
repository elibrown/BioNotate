"""
Upload day1 ... day6 to a running backend, in order, for one astronaut.

Start the backend first (uvicorn app.main:app --reload), then, from the
repository root:
    backend\\.venv\\Scripts\\python data\\sample\\voice\\upload_trend.py A-01
The astronaut ID is optional (default A-01). Server address: set
ASTROHEALTH_URL if it isn't http://localhost:8000.
"""

import os
import sys
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
URL = os.environ.get("ASTROHEALTH_URL", "http://localhost:8000") + "/api/audio"
TASKS = ["counting_normal", "counting_fast", "vowel_a", "vowel_e", "vowel_o"]

astronaut_id = sys.argv[1] if len(sys.argv) > 1 else "A-01"

for day in sorted(HERE.glob("day*"), key=lambda p: int(p.name[3:])):
    files = {task: (f"{task}.wav", (day / f"{task}.wav").read_bytes(), "audio/wav")
             for task in TASKS}
    response = requests.post(URL, files=files, data={"astronaut_id": astronaut_id}, timeout=120)
    response.raise_for_status()
    result = response.json()["result"]
    print(f"{day.name}: status={result['status']} vocal_biomarker={result['vocal_biomarker']}"
          f" shimmer={result['voice_quality'].get('shimmer_pct')}%")
