
"""
Cardiorespiratory model adapter for AstroHealth.

Estimates heart rate (HR), respiratory rate (RR),
and pulse-respiration quotient (PRQ) from a recording.
"""

from pathlib import Path
from statistics import median

from cardioresp import analyze_file


MODEL_NAME = "cardioresp"
MODEL_VERSION = "0.2.0"


def recording_summary(measurements: list[dict]) -> dict:
    """
    Summarize valid readings for the entire recording.

    Use the median of successful readings to reduce
    sensitivity to individual fluctuations.
    """
    valid = [
        reading
        for reading in measurements
        if reading["status"] == "ok"
        and reading["hr_bpm"] is not None
        and reading["respi_rate"] is not None
        and reading["respi_rate"] > 0
    ]

    if not valid:
        return {
            "hr_bpm": None,
            "respi_rate": None,
            "prq": None,
            "valid_readings": 0,
        }

    hr = round(median(r["hr_bpm"] for r in valid), 1)
    rr = round(median(r["respi_rate"] for r in valid), 1)

    return {
        "hr_bpm": hr,
        "respi_rate": rr,
        "prq": round(hr / rr, 2),
        "valid_readings": len(valid),
    }


def run_model(video_path: Path) -> dict:
    """
    Analyze a recording and return JSON-serializable results.

    Top-level vital signs represent the latest reading.
    The summary contains recording-level median estimates.
    """

    readings = analyze_file(str(video_path))

    measurements = [
        {
            "timestamp_s": reading.ts,
            "hr_bpm": reading.hr_bpm,
            "respi_rate": reading.respi_rate,
            "prq": reading.prq,
            "status": reading.status,
            "log_message": reading.log_message,
        }
        for reading in readings
    ]

    summary = recording_summary(measurements)

    if not measurements:
        return {
            "model": MODEL_NAME,
            "model_version": MODEL_VERSION,
            "status": "insufficient_data",
            "hr_bpm": None,
            "respi_rate": None,
            "prq": None,
            "summary": summary,
            "measurements": [],
            "message": "No readings were produced.",
        }

    latest = measurements[-1]

    return {
        "model": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "status": latest["status"],
        "hr_bpm": latest["hr_bpm"],
        "respi_rate": latest["respi_rate"],
        "prq": latest["prq"],
        "summary": summary,
        "measurements": measurements,
    }
