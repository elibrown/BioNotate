"""
End to end: upload a video -> model output is saved -> dashboard shows it.

Only the model itself is faked (it needs a real face video); everything
after it is the real code: upload route, extractor, SQLite, dashboard
repository, dashboard rules and alerts.
"""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.routers import video


def cardioresp_output(*heart_rates):
    readings = [
        {"timestamp_s": 30.0 + i, "hr_bpm": hr, "respi_rate": 14.0, "prq": hr / 14.0,
         "status": "ok", "log_message": ""}
        for i, hr in enumerate(heart_rates)
    ]
    return {"model": "cardioresp", "model_version": "0.2.0", "status": "ok",
            "hr_bpm": heart_rates[-1], "respi_rate": 14.0, "prq": heart_rates[-1] / 14.0,
            "summary": {}, "measurements": readings}


class EndToEndTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        tmp = Path(self.tmp.name)
        self.patches = [
            patch.dict(os.environ, {"ASTROHEALTH_DB": str(tmp / "test.db")}),
            patch.object(video, "UPLOAD_DIR", tmp),
        ]
        for p in self.patches:
            p.start()
        os.environ.pop("ASTROHEALTH_DASHBOARD", None)   # use the database
        self.client = TestClient(app)

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def upload(self, astronaut_id, output):
        with patch.object(video, "run_model", return_value=output):
            r = self.client.post("/api/video", data={"astronaut_id": astronaut_id},
                                 files={"file": ("clip.mp4", b"fake", "video/mp4")})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def crew(self):
        snapshot = self.client.get("/api/dashboard").json()
        self.assertEqual(snapshot["mode"], "live")
        return snapshot, {m["id"]: m for m in snapshot["crew"]}

    def test_before_any_upload_everyone_is_unknown(self):
        snapshot, crew = self.crew()
        self.assertEqual(set(crew), {"A-01", "A-02", "A-03", "A-04"})   # roster seeded
        self.assertEqual(crew["A-01"]["name"], "Alex Morgan")
        self.assertTrue(all(m["status"] == "unknown" for m in crew.values()))
        self.assertEqual(snapshot["alerts"], [])

    def test_upload_shows_up_on_dashboard(self):
        self.upload("A-01", cardioresp_output(70, 72, 71))
        _, crew = self.crew()
        a01 = crew["A-01"]
        self.assertEqual(a01["status"], "normal")
        self.assertFalse(a01["stale"])
        hr = {m["key"]: m for m in a01["metrics"]}["heart_rate"]
        self.assertEqual(hr["value"], 71)              # latest reading
        self.assertEqual(hr["history"], [70, 72, 71])  # oldest -> newest
        self.assertEqual(crew["A-02"]["status"], "unknown")   # no data yet

    def test_high_heart_rate_raises_dashboard_alert(self):
        self.upload("A-02", cardioresp_output(128, 131, 130))
        snapshot, crew = self.crew()
        self.assertEqual(crew["A-02"]["status"], "alert")
        self.assertEqual([a["crew_id"] for a in snapshot["alerts"]], ["A-02"])
        self.assertIn("Heart rate", snapshot["alerts"][0]["message"])

    def test_new_astronaut_id_appears_on_dashboard(self):
        self.upload("X-99", cardioresp_output(75, 76))
        _, crew = self.crew()
        self.assertIn("X-99", crew)
        self.assertEqual(crew["X-99"]["role"], "Not on roster")
        self.assertEqual(crew["X-99"]["status"], "normal")


if __name__ == "__main__":
    unittest.main()
