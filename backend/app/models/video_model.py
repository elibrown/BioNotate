
"""
Heart-rate prediction adapter for AstroHealth.

Uses the rPPG package to estimate heart rate
from a recorded video file.
"""

from pathlib import Path

from rppg import estimate_video


MODEL_NAME = "rppg"
MODEL_VERSION = "0.1.0"


def run_model(video_path: Path) -> dict:
    """
    Run heart-rate estimation on a recorded video.

    Args:
        video_path: Path to a locally saved video file.

    Returns:
        A JSON-serializable prediction result.
    """

    readings = estimate_video(str(video_path))

    measurements = [
        {
            "timestamp_s": round(float(timestamp), 2),
            "hr_bpm": round(float(bpm), 1),
        }
        for timestamp, bpm in readings
        if bpm is not None
    ]

    if not measurements:
        return {
            "model": MODEL_NAME,
            "model_version": MODEL_VERSION,
            "status": "insufficient_data",
            "hr_bpm": None,
            "measurements": [],
            "message": (
                "No heart-rate estimate produced. "
                "Check video duration, face visibility, "
                "and lighting."
            ),
        }

    return {
        "model": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "status": "ok",
        "hr_bpm": measurements[-1]["hr_bpm"],
        "measurements": measurements,
    }
