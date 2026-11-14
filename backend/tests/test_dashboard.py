import os
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.dashboard.repository import CrewMember, Metric, Prediction
from app.main import app
from app.routers.dashboard import combined_alerts, evaluate_member

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

    def test_combined_rule_needs_all_conditions(self):
        rules = {"both": {"label": "Both high", "all": [
            {"key": "heart", "above": 100}, {"key": "fatigue", "above": 0.5}]}}
        self.assertEqual(combined_alerts(member(value=110, score=0.6), rules)[0]["metric"], "both")
        self.assertEqual(combined_alerts(member(value=90, score=0.6), rules), [])
        self.assertEqual(combined_alerts(member(value=110, score=0.4), rules), [])
        self.assertEqual(combined_alerts(member(value=110), rules), [])   # no score at all

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

    def test_sample_preview_has_data_without_writing_database(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from app import db

        with TemporaryDirectory() as directory, patch.dict(os.environ, {
            'ASTROHEALTH_DB': str(Path(directory) / 'preview.db'),
            'ASTROHEALTH_DASHBOARD': 'live',
        }):
            client = TestClient(app)
            sample = client.get('/api/dashboard?demo=true')
            self.assertEqual(sample.status_code, 200)
            self.assertEqual(sample.json()['mode'], 'demo')
            self.assertTrue(all(member['predictions'] for member in sample.json()['crew']))
            self.assertTrue(all(metric['value'] is not None for member in sample.json()['crew'] for metric in member['metrics']))
            self.assertEqual(db.list_measurements(), [])
            self.assertEqual(client.get('/api/dashboard').json()['mode'], 'live')
