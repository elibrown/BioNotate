import os
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.dashboard.repository import CrewMember, Metric, Prediction
from app.main import app
from app.routers.dashboard import evaluate_member

NOW = datetime(2026, 11, 14, tzinfo=timezone.utc)


def member(value=72, age=0, score=None):
    return CrewMember(
        id="A-01", name="Test Crew", role="Engineer",
        observed_at=NOW - timedelta(seconds=age),
        metrics=[Metric(key="heart", label="Heart rate", value=value,
                        unit="bpm", lower=50, upper=100, history=[])],
        predictions=[] if score is None else [Prediction(
            id="P-01", target="fatigue", label="Fatigue risk", score=score,
            threshold=0.7, observed_at=NOW, model_version="demo")],
    )


class DashboardTests(unittest.TestCase):
    def test_metric_status_and_freshness(self):
        for value, age, expected in [
            (50, 0, "normal"), (100, 0, "normal"),
            (49, 0, "alert"), (101, 0, "alert"),
            (None, 0, "unknown"), (72, 301, "unknown"),
            (101, 301, "alert"),
        ]:
            with self.subTest(value=value, age=age):
                result, alerts = evaluate_member(member(value, age), NOW, 300)
                self.assertEqual(result["status"], expected)
                self.assertEqual(result["stale"], age > 300)
                self.assertEqual(bool(alerts), expected == "alert")
                if alerts:
                    self.assertEqual(alerts[0]["crew_id"], "A-01")

    def test_prediction_threshold(self):
        for score, expected in [(0.69, "normal"), (0.7, "alert"), (0.8, "alert")]:
            with self.subTest(score=score):
                result, alerts = evaluate_member(member(score=score), NOW, 300)
                self.assertEqual(result["status"], expected)
                if alerts:
                    self.assertEqual(alerts[0]["metric"], "fatigue")

    def test_demo_api_joins_data(self):
        with patch.dict(os.environ, {"ASTROHEALTH_DASHBOARD": "demo"}):
            response = TestClient(app).get("/api/dashboard")
        self.assertEqual(response.status_code, 200)
        snapshot = response.json()
        self.assertTrue(snapshot["crew"])
        for crew in snapshot["crew"]:
            self.assertTrue(crew["metrics"])
            self.assertTrue(crew["predictions"])
        crew_ids = {crew["id"] for crew in snapshot["crew"]}
        self.assertTrue(snapshot["alerts"])
        self.assertTrue(all(alert["crew_id"] in crew_ids for alert in snapshot["alerts"]))
