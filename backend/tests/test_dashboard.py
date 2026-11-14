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

    def test_dashboard_uses_persisted_samples_without_a_preview_mode(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from app import db
        from app.db_snapshot import initialize_database

        with TemporaryDirectory() as directory, patch.dict(os.environ, {
            'ASTROHEALTH_DB': str(Path(directory) / 'samples.db'),
        }):
            self.assertTrue(initialize_database())
            self.assertFalse(initialize_database())
            client = TestClient(app)
            sample = client.get('/api/dashboard').json()
            self.assertEqual(sample['mode'], 'live')
            self.assertEqual(sorted(member['status'] for member in sample['crew']),
                             ['alert', 'alert', 'normal', 'normal'])
            self.assertTrue(all(member['simulated'] for member in sample['crew']))
            db.add_measurement('A-01', 'temperature_c', 37.2, '°C')
            db.add_measurement('A-01', 'hr_bpm', 72, 'bpm', source='cardioresp')
            real = next(m for m in client.get('/api/dashboard').json()['crew'] if m['id']=='A-01')
            self.assertFalse(real['simulated'])
            self.assertEqual(real['metrics'][0]['value'], 72)
            temperature = next(m for m in real['manual_measurements'] if m['metric']=='temperature_c')
            self.assertEqual(temperature['value'], 37.2)
            self.assertNotIn('id="data-source"', client.get('/').text)

    def test_shared_snapshot_preserves_local_data(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        import sqlite3
        from app.db_snapshot import initialize_database

        with TemporaryDirectory() as directory:
            target = Path(directory) / 'runtime.sqlite3'
            with patch.dict(os.environ, {'ASTROHEALTH_DB': str(target)}):
                assert initialize_database()
                with sqlite3.connect(target) as connection:
                    assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
                    assert connection.execute('SELECT COUNT(*) FROM measurements').fetchone()[0] > 0
                    connection.execute("INSERT INTO astronauts(id,name) VALUES ('LOCAL', 'Local Crew')")
                assert not initialize_database()
                with sqlite3.connect(target) as connection:
                    assert connection.execute("SELECT name FROM astronauts WHERE id='LOCAL'").fetchone()[0] == 'Local Crew'
