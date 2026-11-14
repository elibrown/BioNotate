
"""Tests for video upload validation."""

from io import BytesIO

from fastapi.testclient import TestClient

from app.main import app
from app.routers import video


def test_invalid_recording_returns_422(monkeypatch, tmp_path):
    """Invalid recordings return HTTP 422 and are deleted."""

    # Save uploads to a temporary test directory.
    monkeypatch.setattr(video, "UPLOAD_DIR", tmp_path)

    # Simulate the cardioresp model rejecting a short recording.
    def fake_run_model(path):
        assert path.exists()
        raise ValueError(
            "recording is 10.0 s long; at least 30 s is required"
        )

    monkeypatch.setattr(video, "run_model", fake_run_model)

    client = TestClient(app)

    response = client.post(
        "/api/video",
        files={
            "file": ("short_video.mp4", BytesIO(b"fake video data"), "video/mp4")
        },
        data={"astronaut_id": "test-001"},
    )

    assert response.status_code == 422
    assert "at least 30 s is required" in response.json()["detail"]

    # The rejected upload should not remain on disk.
    assert list(tmp_path.iterdir()) == []
