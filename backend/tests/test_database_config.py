"""Cloud configuration must never silently select a different database."""
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient
from app import db
from app.main import app


class DatabaseConfigTests(unittest.TestCase):
    def test_incomplete_cloud_configuration_fails(self):
        for url, token in [('libsql://example.turso.io', ''), ('', 'token')]:
            with self.subTest(url=url), patch.dict(os.environ, {
                'TURSO_DATABASE_URL': url, 'TURSO_AUTH_TOKEN': token,
            }):
                with self.assertRaisesRegex(RuntimeError, 'Set both'):
                    db._connect()

    def test_startup_does_not_insert_measurements_or_predictions(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {
            'ASTROHEALTH_DB': str(Path(directory) / 'empty.db'),
            'TURSO_DATABASE_URL': '', 'TURSO_AUTH_TOKEN': '',
        }):
            with TestClient(app) as client:
                self.assertEqual(client.get('/api/measurements').json(), [])
                self.assertEqual(client.get('/api/predictions').json(), [])

    def test_dashboard_uses_one_connection_for_all_crew(self):
        from app.dashboard.repository import DatabaseCrewRepository
        with TemporaryDirectory() as directory, patch.dict(os.environ, {
            'ASTROHEALTH_DB': str(Path(directory) / 'dashboard.db'),
            'TURSO_DATABASE_URL': '', 'TURSO_AUTH_TOKEN': '',
        }):
            db.add_astronauts([{'id': 'A-01', 'name': 'One'}, {'id': 'A-02', 'name': 'Two'}])
            db.add_measurement('A-01', 'hr_bpm', 72, 'bpm')
            db.add_measurement('A-02', 'hr_bpm', 80, 'bpm')
            with patch.object(db, '_connect', wraps=db._connect) as connect:
                crew = DatabaseCrewRepository().list_crew()
            self.assertEqual(connect.call_count, 1)
            self.assertEqual([next(m.value for m in person.metrics if m.key == 'heart_rate') for person in crew], [72, 80])

    def test_cached_dashboard_invalidates_after_a_committed_reading(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {
            'ASTROHEALTH_DB': str(Path(directory) / 'cache.db'),
            'TURSO_DATABASE_URL': '', 'TURSO_AUTH_TOKEN': '',
        }):
            db.add_astronauts([{'id': 'A-01', 'name': 'One'}])
            db.add_measurement('A-01', 'hr_bpm', 72, 'bpm')
            with patch.object(db, '_fetch_dashboard_readings', wraps=db._fetch_dashboard_readings) as fetch:
                first = db.dashboard_readings(60)
                self.assertEqual(db.dashboard_readings(60), first)
                self.assertEqual(fetch.call_count, 1)
                db.add_measurement('A-01', 'hr_bpm', 105, 'bpm')
                self.assertEqual(db.dashboard_readings(60)[-1]['value'], 105)
                self.assertEqual(fetch.call_count, 2)

    def test_dashboard_cache_expires_for_other_developers_writes(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {
            'ASTROHEALTH_DB': str(Path(directory) / 'expiry.db'),
            'TURSO_DATABASE_URL': '', 'TURSO_AUTH_TOKEN': '',
        }):
            db.add_astronauts([{'id': 'A-01', 'name': 'One'}])
            with patch.object(db.time, 'monotonic', return_value=100) as clock, \
                 patch.object(db, '_fetch_dashboard_readings', wraps=db._fetch_dashboard_readings) as fetch:
                db.dashboard_readings(60)
                clock.return_value = 106
                db.dashboard_readings(60)
                self.assertEqual(fetch.call_count, 2)
