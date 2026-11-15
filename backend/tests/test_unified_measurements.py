import os
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app import db
from app.data import imports as biologist, management as data_management
from app.routers.measurements import router


class UnifiedMeasurementsTests(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'production.db'
        self.env = patch.dict(os.environ, ASTROHEALTH_DB=str(self.path), ASTROHEALTH_IMPORT_BIOLOGY='true')
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_production_has_only_three_domain_tables_and_all_sources_are_queryable(self):
        live = db.add_measurement('A-01', 'hr_bpm', 72, source='cardioresp', unit='bpm')
        data_management.initialize()
        with db._connect() as conn:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        self.assertEqual(tables, {'astronauts', 'predictions', 'measurements'})
        self.assertIn(live, db.list_measurements(context='live', limit=10000))
        rows = db.list_measurements(context='research')
        self.assertEqual(len(rows), 220)
        self.assertTrue(all(r['measured_at'] is None and r['phase_index'] is not None for r in rows))
        self.assertIn('BM03_IL6', {r['metric'] for r in rows})
        self.assertIn('BM05_LCN2', {r['metric'] for r in rows})
        app = FastAPI()
        app.include_router(router)
        response = TestClient(app).get('/api/measurements/trends', params={'astronaut_id': 'A-01', 'metric': 'hr_bpm'})
        self.assertEqual(response.status_code, 200)
        series = response.json()['series']
        self.assertEqual({s['source'] for s in series}, {'cardioresp', 'biologist_csv', 'shared_demo'})
        self.assertEqual({s['axis'] for s in series}, {'timestamp', 'mission_phase'})
        self.assertEqual(len(next(s for s in series if s['source'] == 'biologist_csv')['points']), 5)
        self.assertEqual(len(next(s for s in series if s['source'] == 'shared_demo')['points']), 1)

    def test_legacy_research_moves_to_draft_and_measurements_atomically(self):
        original = db.add_measurement('A-01', 'hr_bpm', 70, source='cardioresp')
        conn = db._connect()
        conn.executescript(biologist.DRAFT_SCHEMA.replace('draft.', ''))
        with conn:
            conn.execute("INSERT INTO research_datasets(id, filename) VALUES ('legacy', 'old.csv')")
            conn.execute("INSERT INTO research_crew_links VALUES ('legacy','A-01','Astronaut 1')")
            conn.execute("INSERT INTO research_observations VALUES ('legacy',2,'Astronaut 1',1,'Baseline','BM03_CRP',2.87)")
        conn.close()
        biologist.connect().close()
        self.assertEqual(db.list_measurements(context='live'), [original])
        rows = db.list_measurements(context='research')
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]['metric'], rows[0]['value']), ('BM03_IL6', 2.87))
        biologist.connect().close()
        self.assertEqual(len(db.list_measurements(context='research')), 1)
        with sqlite3.connect(biologist.draft_path()) as draft:
            self.assertEqual(draft.execute('SELECT COUNT(*) FROM research_observations').fetchone()[0], 1)
        with db._connect() as conn:
            self.assertFalse(conn.execute("SELECT name FROM sqlite_master WHERE name LIKE 'research_%'").fetchall())

    def test_graph_compatibility_uses_production_not_draft_values(self):
        result = biologist.import_csv(data_management.BIOLOGY_FILE)
        with sqlite3.connect(biologist.draft_path()) as draft:
            draft.execute('UPDATE research_observations SET value=999')
        rows = biologist.crew_datasets('A-01')[0]['observations']
        self.assertFalse(any(r['value'] == 999 for r in rows))
        self.assertEqual(len(rows), 55)

    def test_legacy_timestamp_schema_upgrade_preserves_ids_values_and_times(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute('CREATE TABLE measurements (id INTEGER PRIMARY KEY AUTOINCREMENT, '
                         'astronaut_id TEXT, source TEXT NOT NULL, metric TEXT NOT NULL, '
                         'value REAL NOT NULL, unit TEXT, measured_at TEXT NOT NULL, '
                         'offset_s REAL, prediction_id INTEGER)')
            conn.execute("INSERT INTO measurements VALUES (17,'A-01','cardioresp','hr_bpm',72,'bpm',"
                         "'2026-11-15T00:00:00.000+00:00',30,NULL)")
        row = db.list_measurements()[0]
        self.assertEqual((row['id'], row['value'], row['measured_at'], row['context']),
                         (17, 72, '2026-11-15T00:00:00.000+00:00', 'live'))
        self.assertGreater(db.add_measurement('A-01', 'hr_bpm', 73)['id'], 17)
        biologist.import_csv(data_management.BIOLOGY_FILE)
        self.assertEqual(len(db.list_measurements(context='research')), 220)
