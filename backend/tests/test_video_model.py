
"""Tests for the cardiorespiratory model adapter."""

from pathlib import Path

from cardioresp import Reading

from app.models import video_model


def test_model_success(monkeypatch):
    """Verify that successful readings become API results."""

    fake_readings = [
        Reading(
            ts=29.0,
            hr_bpm=None,
            respi_rate=None,
            prq=None,
            status="warming_up",
            log_message="collecting data",
        ),
        Reading(
            ts=31.0,
            hr_bpm=72.5,
            respi_rate=15.0,
            prq=4.83,
            status="ok",
            log_message="ok",
        ),
    ]

    def fake_analyze_file(path):
        assert path == "test.mp4"
        return fake_readings

    monkeypatch.setattr(
        video_model, "analyze_file", fake_analyze_file
    )

    result = video_model.run_model(Path("test.mp4"))

    assert result["model"] == "cardioresp"
    assert result["model_version"] == "0.2.0"
    assert result["status"] == "ok"
    assert result["hr_bpm"] == 72.5
    assert result["respi_rate"] == 15.0
    assert result["prq"] == 4.83

    assert len(result["measurements"]) == 2
    assert result["measurements"][0]["status"] == "warming_up"
    assert result["measurements"][1]["timestamp_s"] == 31.0


def test_model_partial(monkeypatch):
    """HR can be available while RR and PRQ are unavailable."""

    monkeypatch.setattr(
        video_model,
        "analyze_file",
        lambda path: [
            Reading(31.0, 70.0, None, None, "partial",
                    "breathing rate unavailable")
        ],
    )

    result = video_model.run_model(Path("test.mp4"))

    assert result["status"] == "partial"
    assert result["hr_bpm"] == 70.0
    assert result["respi_rate"] is None
    assert result["prq"] is None


def test_model_no_face(monkeypatch):
    """Missing face data should not produce vital signs."""

    monkeypatch.setattr(
        video_model,
        "analyze_file",
        lambda path: [
            Reading(31.0, None, None, None,
                    "no_face", "no face detected")
        ],
    )

    result = video_model.run_model(Path("test.mp4"))

    assert result["status"] == "no_face"
    assert result["hr_bpm"] is None
    assert result["respi_rate"] is None
    assert result["prq"] is None


def test_model_no_readings(monkeypatch):
    """An empty model response should be handled safely."""

    monkeypatch.setattr(
        video_model,
        "analyze_file",
        lambda path: [],
    )

    result = video_model.run_model(Path("test.mp4"))

    assert result["status"] == "insufficient_data"
    assert result["hr_bpm"] is None
    assert result["respi_rate"] is None
    assert result["prq"] is None
    assert result["measurements"] == []


def test_recording_summary_uses_valid_readings(monkeypatch):
    """Summary uses medians and excludes invalid readings."""

    fake_readings = [
        Reading(30.0, 80.0, 10.0, 8.0, "ok", "ok"),
        Reading(31.0, 70.0, 14.0, 5.0, "ok", "ok"),
        Reading(32.0, 75.0, 12.0, 6.25, "ok", "ok"),
        Reading(
            33.0, None, None, None,
            "no_face", "no face detected"
        ),
    ]

    monkeypatch.setattr(
        video_model,
        "analyze_file",
        lambda path: fake_readings,
    )

    result = video_model.run_model(Path("test.mp4"))

    # Latest reading has no usable data.
    assert result["status"] == "no_face"
    assert result["hr_bpm"] is None

    # Summary still uses the three successful readings.
    assert result["summary"] == {
        "hr_bpm": 75.0,
        "respi_rate": 12.0,
        "prq": 6.25,
        "valid_readings": 3,
    }
