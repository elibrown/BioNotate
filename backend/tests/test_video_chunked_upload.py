"""Tests for uploading a video in pieces and analysing it in the background."""

from fastapi.testclient import TestClient

from app.main import app
from app.routers import video


def upload_in_pieces(client, data: bytes, chunk_size: int, filename="face.mp4"):
    start = client.post(
        "/api/video/uploads",
        json={"filename": filename, "size": len(data), "astronaut_id": "test-001"},
    )
    assert start.status_code == 200, start.text
    upload_id = start.json()["upload_id"]
    for offset in range(0, len(data), chunk_size):
        piece = client.put(
            f"/api/video/uploads/{upload_id}?offset={offset}",
            content=data[offset:offset + chunk_size],
        )
        assert piece.status_code == 200, piece.text
    return upload_id


def wait_for_job(client, upload_id):
    for _ in range(50):
        job = client.get(f"/api/video/jobs/{upload_id}?wait=1").json()
        if job["status"] != "processing":
            return job
    raise AssertionError("job never finished")


def test_pieces_are_joined_and_analysed(monkeypatch, tmp_path):
    monkeypatch.setattr(video, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(video, "CHUNK_SIZE", 4)
    data = b"0123456789abcdefXYZ"
    seen = {}

    def fake_run_model(path):
        seen["bytes"] = path.read_bytes()
        return {"model": "fake", "status": "ok", "hr_bpm": 70.0, "respi_rate": 15.0,
                "prq": 4.67, "summary": {}, "measurements": []}

    monkeypatch.setattr(video, "run_model", fake_run_model)
    client = TestClient(app)

    upload_id = upload_in_pieces(client, data, chunk_size=4)
    # Re-sending a piece (e.g. after a network error) must not corrupt the file.
    assert client.put(f"/api/video/uploads/{upload_id}?offset=4", content=data[4:8]).status_code == 200
    for offset in range(8, len(data), 4):
        client.put(f"/api/video/uploads/{upload_id}?offset={offset}", content=data[offset:offset + 4])

    assert client.post(f"/api/video/uploads/{upload_id}/finish").status_code == 200
    job = wait_for_job(client, upload_id)

    assert job["status"] == "done", job
    assert job["astronaut_id"] == "test-001"
    assert job["filename"] == "face.mp4"
    assert seen["bytes"] == data


def test_rejected_recording_reports_error_and_is_deleted(monkeypatch, tmp_path):
    monkeypatch.setattr(video, "UPLOAD_DIR", tmp_path)

    def fake_run_model(path):
        raise ValueError("recording is 10.0 s long; at least 30 s is required")

    monkeypatch.setattr(video, "run_model", fake_run_model)
    client = TestClient(app)

    upload_id = upload_in_pieces(client, b"short video", chunk_size=1024)
    client.post(f"/api/video/uploads/{upload_id}/finish")
    job = wait_for_job(client, upload_id)

    assert job["status"] == "error"
    assert "at least 30 s is required" in job["detail"]
    assert list(tmp_path.iterdir()) == []


def test_incomplete_upload_cannot_finish(monkeypatch, tmp_path):
    monkeypatch.setattr(video, "UPLOAD_DIR", tmp_path)
    client = TestClient(app)
    start = client.post("/api/video/uploads", json={"filename": "a.mp4", "size": 10}).json()
    client.put(f"/api/video/uploads/{start['upload_id']}?offset=0", content=b"12345")

    response = client.post(f"/api/video/uploads/{start['upload_id']}/finish")
    assert response.status_code == 409


def test_unknown_upload_gives_readable_error():
    client = TestClient(app)
    response = client.get("/api/video/jobs/does-not-exist")
    assert response.status_code == 404
    assert "upload the video again" in response.json()["detail"]


def test_wrong_file_type_rejected():
    client = TestClient(app)
    response = client.post("/api/video/uploads", json={"filename": "notes.txt", "size": 10})
    assert response.status_code == 400
