
from pathlib import Path

from app.models import video_model


def test_heart_rate_model_success(monkeypatch):
    """Verify that rPPG readings become valid API results."""

    def fake_estimate_video(path):
        assert path == "test.mp4"
        return [
            (30.0, 72.5),
            (31.0, 73.2),
        ]

    monkeypatch.setattr(
        video_model,
        "estimate_video",
        fake_estimate_video,
    )

    result = video_model.run_model(Path("test.mp4"))

    assert result["status"] == "ok"
    assert result["model"] == "rppg"
    assert result["hr_bpm"] == 73.2
    assert len(result["measurements"]) == 2


def test_heart_rate_model_insufficient_data(monkeypatch):
    """Verify behavior when no HR estimate is available."""

    monkeypatch.setattr(
        video_model,
        "estimate_video",
        lambda path: [],
    )

    result = video_model.run_model(Path("test.mp4"))

    assert result["status"] == "insufficient_data"
    assert result["hr_bpm"] is None
    assert result["measurements"] == []
