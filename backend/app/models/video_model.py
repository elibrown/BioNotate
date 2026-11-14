"""
The video health model (PLACEHOLDER).

run_model() is the ONE place to plug in the real model later.
It gets the path of a saved video and returns a dict with the result.
"""

from pathlib import Path


def run_model(video_path: Path) -> dict:
    """
    >>> THIS IS WHERE THE REAL MODEL GOES. <<<

    Later, replace the dummy code below with something like:

        frames = load_frames(video_path)
        prediction = my_transformer_model(frames)
        return {"status": prediction.label, "confidence": prediction.score}

    For now it returns a fake answer so the rest of the app works.
    """
    size_mb = video_path.stat().st_size / (1024 * 1024)
    return {
        "model": "placeholder (not a real model yet)",
        "status": "normal",
        "confidence": 0.0,
        "video_size_mb": round(size_mb, 2),
        "note": "Dummy result. Replace run_model() in backend/app/models/video_model.py.",
    }
