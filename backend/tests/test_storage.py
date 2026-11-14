"""
Tests for saving predictions and measurements (app/db.py and its routes).

Each test uses its own throwaway database and upload folder.
Run from backend/:  python -m pytest -q
"""

import os
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.routers import video


def reading(t, status, hr=None, rr=None, prq=None):
    return {"timestamp_s": t, "hr_bpm": hr, "respi_rate": rr, "prq": prq,
            "status": status, "log_message": ""}


# Shape of the real cardioresp model output, with one reading of each status.
CARDIO_RESULT = {
    "model": "cardioresp",
    "model_version": "0.2.0",
    "status": "ok",
    "hr_bpm": 72.4,
    "respi_rate": 14.2,
    "prq": 5.1,
    "summary": {"hr_bpm": 72.0, "respi_rate": 14.0, "prq": 5.14, "valid_readings": 2},
    "measurements": [
        reading(29.0, "warming_up"),                       # skipped: no values
        reading(30.0, "ok", hr=71.8, rr=13.9, prq=5.17),   # 3 rows
        reading(31.0, "partial", hr=72.0),                 # 1 row: HR only
        reading(32.0, "no_face"),                          # skipped
        reading(33.0, "ok", hr=72.4, rr=14.2, prq=5.1),    # 3 rows
    ],
}


def with_hr(*hrs):
    """A cardioresp result whose "ok" readings have these heart rates."""
    return {**CARDIO_RESULT,
            "measurements": [reading(30.0 + i, "ok", hr=hr, rr=14.0, prq=hr / 14.0)
                             for i, hr in enumerate(hrs)]}


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        tmp = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {"ASTROHEALTH_DB": str(tmp / "test.db")})
        self.uploads = patch.object(video, "UPLOAD_DIR", tmp)
        self.env.start()
        self.uploads.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.uploads.stop()
        self.env.stop()
        self.tmp.cleanup()

    def upload(self, result, astronaut_id="A-07"):
        data = {"astronaut_id": astronaut_id} if astronaut_id else {}
        with patch.object(video, "run_model", return_value=result):
            response = self.client.post(
                "/api/video",
                files={"file": ("clip.mp4", b"fake video", "video/mp4")},
                data=data,
            )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_cardioresp_upload_saves_every_reading(self):
        body = self.upload(CARDIO_RESULT)
        self.assertFalse(body["is_alert"])
        saved = [(m["offset_s"], m["metric"], m["value"], m["unit"])
                 for m in body["measurements"]]
        self.assertEqual(sorted(saved), sorted([
            (30.0, "hr_bpm", 71.8, "bpm"),
            (30.0, "respi_rate", 13.9, "breaths/min"),
            (30.0, "prq", 5.17, None),
            (31.0, "hr_bpm", 72.0, "bpm"),          # partial: HR only
            (33.0, "hr_bpm", 72.4, "bpm"),
            (33.0, "respi_rate", 14.2, "breaths/min"),
            (33.0, "prq", 5.1, None),
        ]))
        for m in body["measurements"]:
            self.assertEqual(m["astronaut_id"], "A-07")
            self.assertEqual(m["source"], "cardioresp")
            self.assertEqual(m["prediction_id"], body["prediction_id"])

        # Each reading's time = upload time + its offset in the video.
        hr = [m for m in body["measurements"] if m["metric"] == "hr_bpm"]
        times = [datetime.fromisoformat(m["measured_at"]) for m in hr]
        self.assertEqual((times[1] - times[0]).total_seconds(), 1.0)
        self.assertEqual((times[2] - times[0]).total_seconds(), 3.0)

        prediction = self.client.get(f"/api/predictions/{body['prediction_id']}").json()
        self.assertEqual(prediction["model"], "cardioresp")
        self.assertEqual(prediction["status"], "ok")
        self.assertEqual(prediction["result"], CARDIO_RESULT)   # full output kept

    def test_no_valid_readings_saves_no_measurements_and_no_alert(self):
        empty = {**CARDIO_RESULT, "status": "insufficient_data", "measurements": []}
        body = self.upload(empty)
        self.assertEqual(body["measurements"], [])
        self.assertFalse(body["is_alert"])   # bad video is not a health alert
        self.assertEqual(self.client.get("/api/predictions").json()[0]["status"],
                         "insufficient_data")

    def test_unknown_model_saves_prediction_without_measurements(self):
        body = self.upload({"model": "something-new", "weird": [1, 2]})
        self.assertEqual(body["measurements"], [])
        self.assertEqual(len(self.client.get("/api/predictions").json()), 1)

    def test_history_is_per_astronaut(self):
        self.upload(CARDIO_RESULT, "A-07")
        self.upload(CARDIO_RESULT, "B-01")
        self.upload(CARDIO_RESULT, "A-07")
        a07 = self.client.get("/api/predictions", params={"astronaut_id": "A-07"}).json()
        self.assertEqual(len(a07), 2)
        self.assertGreater(a07[0]["id"], a07[1]["id"])   # newest first
        hr = self.client.get(
            "/api/measurements",
            params={"astronaut_id": "A-07", "source": "cardioresp", "metric": "hr_bpm"}
        ).json()
        self.assertEqual(len(hr), 6)   # 3 HR readings per video x 2 videos
        times = [m["measured_at"] for m in hr]
        self.assertEqual(times, sorted(times))   # oldest first, ready for a chart

        one_video = self.client.get(
            "/api/measurements", params={"prediction_id": a07[0]["id"]}
        ).json()
        self.assertEqual(len(one_video), 7)

    def test_alert_uses_median_not_single_readings(self):
        calm = self.upload(with_hr(72, 74, 130, 73))    # one noisy reading
        self.assertFalse(calm["is_alert"])
        high = self.upload(with_hr(125, 131, 128))      # median 128 > 120
        self.assertTrue(high["is_alert"])
        low = self.upload(with_hr(38, 36, 39))          # median 38 < 40
        self.assertTrue(low["is_alert"])

    def test_alerts_and_acknowledge(self):
        self.upload(CARDIO_RESULT)
        self.upload({**CARDIO_RESULT, "status": "no_face"})   # data quality only
        bad = self.upload(with_hr(150, 152))
        flagged = self.upload({"model": "x", "alert": True}, astronaut_id=None)
        alerts = self.client.get("/api/alerts").json()
        self.assertEqual([a["id"] for a in alerts], [flagged["prediction_id"], bad["prediction_id"]])

        ack = self.client.post(f"/api/alerts/{bad['prediction_id']}/ack")
        self.assertTrue(ack.json()["alert_acknowledged"])
        self.assertEqual(len(self.client.get("/api/alerts").json()), 1)
        all_alerts = self.client.get("/api/alerts", params={"include_acknowledged": True}).json()
        self.assertEqual(len(all_alerts), 2)

        ok_id = self.client.get("/api/predictions").json()[-1]["id"]   # first upload
        self.assertEqual(self.client.post(f"/api/alerts/{ok_id}/ack").status_code, 400)
        self.assertEqual(self.client.get("/api/predictions/999").status_code, 404)

    def test_manual_measurement_and_time_filter(self):
        for day, value in [("2026-11-10", 95), ("2026-11-12", 101), ("2026-11-14", 110)]:
            r = self.client.post("/api/measurements", json={
                "astronaut_id": "A-07",
                "metric": "glucose_mg_dl",
                "value": value,
                "unit": "mg/dL",
                "measured_at": f"{day}T08:00:00Z",
            })
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json()["source"], "manual")
            self.assertIsNone(r.json()["prediction_id"])
            self.assertIsNone(r.json()["offset_s"])

        trend = self.client.get("/api/measurements", params={
            "astronaut_id": "A-07", "source": "manual", "metric": "glucose_mg_dl",
            "since": "2026-11-11T00:00:00Z",
        }).json()
        self.assertEqual([m["value"] for m in trend], [101, 110])   # oldest first

        # "since" exactly at a reading's time includes it.
        exact = self.client.get("/api/measurements", params={
            "metric": "glucose_mg_dl", "since": "2026-11-14T08:00:00Z",
            "until": "2026-11-14T08:00:00Z",
        }).json()
        self.assertEqual([m["value"] for m in exact], [110])


if __name__ == "__main__":
    unittest.main()
