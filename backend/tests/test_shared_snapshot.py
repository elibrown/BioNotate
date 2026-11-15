import os
import hashlib
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient
from app import db
from app import seed as management
from app.main import app


class SharedSnapshotTests(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.env = patch.dict(os.environ, ASTROHEALTH_DB=str(Path(self.tmp.name) / 'working.db'))
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_snapshot_contains_only_three_production_tables_and_biology(self):
        with sqlite3.connect(management.SNAPSHOT_FILE) as conn:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
            self.assertEqual(tables, set(db.SEED_TABLES))
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM measurements WHERE source='biologist_csv'").fetchone()[0], 220)
            self.assertEqual(conn.execute("SELECT DISTINCT dataset_id FROM measurements WHERE source='biologist_csv'").fetchall(), [(hashlib.sha256(management.BIOLOGY_FILE.read_bytes()).hexdigest(),)])
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM measurements WHERE source='shared_demo'").fetchone()[0], 9)
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0], 'ok')

    def test_merge_remaps_colliding_prediction_ids_and_preserves_local_records(self):
        original = db.save_prediction({'model': 'local_only', 'status': 'ok'}, 'A-01',
                                     measurements=[{'metric': 'hr_bpm', 'value': 73, 'unit': 'bpm'}])
        original_rows = db.list_measurements()
        management.load_snapshot()
        self.assertEqual(db.get_prediction(original['id'])['result'], original['result'])
        for row in original_rows:
            self.assertIn(row, db.list_measurements(limit=10000))
        conn = db._connect()
        self.assertFalse(conn.execute('PRAGMA foreign_key_check').fetchall())
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM measurements m JOIN predictions p ON p.id=m.prediction_id WHERE m.dataset_id LIKE 'shared-seed:%' AND m.source != p.model").fetchone()[0], 0)
        conn.close()
        before = db.dump_tables()
        self.assertEqual(management.load_snapshot(), dict.fromkeys(db.SEED_TABLES, 0))
        self.assertEqual(db.dump_tables(), before)

    def test_startup_has_complete_vitals_and_one_demo_warning(self):
        with TestClient(app) as client:
            crew = client.get('/api/dashboard').json()['crew']
            self.assertEqual(len(crew), 4)
            self.assertTrue(all(m['status'] != 'unknown' for m in crew))
            self.assertEqual(len(client.get('/api/measurements', params={'source':'biologist_csv'}).json()), 220)
            self.assertEqual(len(db.list_measurements(limit=10000)), 616)
            self.assertTrue(all(m['value'] is not None for person in crew for m in person['metrics']))
            victor = next(person for person in crew if person['id'] == 'A-02')
            self.assertEqual(victor['status'], 'alert')
            self.assertEqual(len(victor['issues']), 1)
            self.assertEqual(victor['issues'][0]['severity'], 'warning')
            self.assertIn('105 bpm', victor['issues'][0]['message'])
            db.add_measurement('A-01', 'hr_bpm', 130, 'bpm', '2026-11-16T00:00:00.000+00:00', source='manual')
            member = next(m for m in client.get('/api/dashboard').json()['crew'] if m['id'] == 'A-01')
            self.assertEqual(member['status'], 'alert')
            self.assertEqual(next(m for m in member['metrics'] if m['key'] == 'heart_rate')['value'], 130)
