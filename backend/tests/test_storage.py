"""
Tests for saving predictions and measurements (app/db.py and its routes).

Each test uses its own throwaway database and upload folder.
Run from backend/:  python -m unittest discover tests
"""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.routers import video

# Shape of the real rPPG model output.
RPPG_RESULT = {
    "model": "rppg",
    "model_version": "0.1.0",
    "status": "ok",
    "hr_bpm": 62.2,
    "measurements": [
        {"timestamp_s": 30.01, "hr_bpm": 62.6},
        {"timestamp_s": 31.01, "hr_bpm": 62.4},
    ],
}


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

    def test_rppg_upload_saves_prediction_and_heart_rate(self):
        body = self.upload(RPPG_RESULT)
        self.assertFalse(body["is_alert"])   # status "ok" is not an alert
        self.assertEqual(len(body["measurements"]), 1)
        m = body["measurements"][0]
        self.assertEqual(
            (m["astronaut_id"], m["biomarker"], m["metric"], m["value"], m["unit"], m["source"]),
            ("A-07", "BM06_HR_HRV_RMSSD", "hr_bpm", 62.2, "bpm", "rppg"),
        )
        self.assertEqual(m["prediction_id"], body["prediction_id"])

        prediction = self.client.get(f"/api/predictions/{body['prediction_id']}").json()
        self.assertEqual(prediction["model"], "rppg")
        self.assertEqual(prediction["status"], "ok")
        self.assertEqual(prediction["result"], RPPG_RESULT)   # full output kept

    def test_unknown_model_saves_prediction_without_measurements(self):
        body = self.upload({"model": "something-new", "weird": [1, 2]})
        self.assertEqual(body["measurements"], [])
        self.assertEqual(len(self.client.get("/api/predictions").json()), 1)

    def test_history_is_per_astronaut(self):
        self.upload(RPPG_RESULT, "A-07")
        self.upload(RPPG_RESULT, "B-01")
        self.upload(RPPG_RESULT, "A-07")
        a07 = self.client.get("/api/predictions", params={"astronaut_id": "A-07"}).json()
        self.assertEqual(len(a07), 2)
        self.assertGreater(a07[0]["id"], a07[1]["id"])   # newest first
        hr = self.client.get(
            "/api/measurements", params={"astronaut_id": "A-07", "metric": "hr_bpm"}
        ).json()
        self.assertEqual(len(hr), 2)

    def test_alerts_and_acknowledge(self):
        self.upload(RPPG_RESULT)
        bad = self.upload({**RPPG_RESULT, "status": "tachycardia"})
        flagged = self.upload({"model": "x", "alert": True}, astronaut_id=None)
        alerts = self.client.get("/api/alerts").json()
        self.assertEqual([a["id"] for a in alerts], [flagged["prediction_id"], bad["prediction_id"]])

        ack = self.client.post(f"/api/alerts/{bad['prediction_id']}/ack")
        self.assertTrue(ack.json()["alert_acknowledged"])
        self.assertEqual(len(self.client.get("/api/alerts").json()), 1)
        all_alerts = self.client.get("/api/alerts", params={"include_acknowledged": True}).json()
        self.assertEqual(len(all_alerts), 2)

        ok_id = self.client.get("/api/predictions").json()[-1]["id"]
        self.assertEqual(self.client.post(f"/api/alerts/{ok_id}/ack").status_code, 400)
        self.assertEqual(self.client.get("/api/predictions/999").status_code, 404)

    def test_biomarkers_list_and_add(self):
        codes = [b["code"] for b in self.client.get("/api/biomarkers").json()]
        self.assertEqual(len(codes), 12)
        self.assertIn("BM06_HR_HRV_RMSSD", codes)
        self.client.post("/api/biomarkers", json={"code": "BM13_Body_Mass", "name": "Body mass"})
        self.assertEqual(len(self.client.get("/api/biomarkers").json()), 13)

    def test_manual_measurement_and_time_filter(self):
        for day, value in [("2026-11-10", 95), ("2026-11-12", 101), ("2026-11-14", 110)]:
            r = self.client.post("/api/measurements", json={
                "astronaut_id": "A-07",
                "biomarker": "BM02_CMP_Glucose_Ca_Renal",
                "metric": "glucose_mg_dl",
                "value": value,
                "unit": "mg/dL",
                "measured_at": f"{day}T08:00:00Z",
            })
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json()["source"], "manual")
            self.assertIsNone(r.json()["prediction_id"])

        trend = self.client.get("/api/measurements", params={
            "astronaut_id": "A-07", "biomarker": "BM02_CMP_Glucose_Ca_Renal",
            "since": "2026-11-11T00:00:00Z",
        }).json()
        self.assertEqual([m["value"] for m in trend], [101, 110])   # oldest first

        bad = self.client.post("/api/measurements", json={
            "astronaut_id": "A-07", "biomarker": "NOPE", "metric": "x", "value": 1,
        })
        self.assertEqual(bad.status_code, 400)


if __name__ == "__main__":
    unittest.main()
