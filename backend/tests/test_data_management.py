import os
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from app import db
from app.data import imports as biologist, management as data_management


class DataManagementTests(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'working.db'
        self.env = patch.dict(os.environ, ASTROHEALTH_DB=str(self.path),
                              ASTROHEALTH_IMPORT_BIOLOGY='true')
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_fresh_initialization_and_restart(self):
        first = data_management.initialize()
        self.assertEqual(first['biology']['inserted'], 220)
        before = data_management.status()
        live = db.dump_tables()
        second = data_management.initialize()
        self.assertIsNone(second['seed'])
        self.assertEqual(second['biology']['inserted'], 0)
        self.assertEqual(data_management.status(), before)
        self.assertEqual(db.dump_tables(), live)
        self.assertEqual(len(biologist.crew_datasets('A-01')[0]['observations']), 55)

    def test_existing_readings_survive_research_initialization(self):
        original = db.add_measurement('A-01', 'hr_bpm', 72, unit='bpm', source='cardioresp')
        result = data_management.initialize()
        self.assertIsNone(result['seed'])
        self.assertEqual(result['biology']['inserted'], 220)
        self.assertIn(original, db.list_measurements(context='live', limit=10000))
        self.assertEqual(len(db.list_measurements(context='research')), 220)
        self.assertEqual(len(biologist.crew_datasets('A-01')[0]['observations']), 55)

    def test_backup_restores_live_and_research_tables(self):
        data_management.initialize()
        target = Path(self.tmp.name) / 'backup.db'
        data_management.backup(target)
        with sqlite3.connect(target) as conn:
            for table, count in data_management.status()['counts'].items():
                self.assertEqual(conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0], count)
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(), [])
        with self.assertRaises(FileExistsError):
            data_management.backup(target)
        with self.assertRaises(FileExistsError):
            data_management.backup(self.path)

    def test_research_can_be_disabled(self):
        with patch.dict(os.environ, ASTROHEALTH_IMPORT_BIOLOGY='false'):
            self.assertIsNone(data_management.initialize()['biology'])
        self.assertEqual(len(db.list_measurements(context='research')), 0)

    def test_startup_refreshes_configured_crew_names_without_deleting_members_or_readings(self):
        db.add_astronauts([{'id': 'A-01', 'name': 'Alex Morgan'}, {'id': 'A-99', 'name': 'Extra member'}])
        original = db.add_measurement('A-01', 'hr_bpm', 72, source='cardioresp')
        data_management.initialize()
        roster = {r['id']: r['name'] for r in db.list_astronauts()}
        self.assertEqual(roster['A-01'], 'Reid Wiseman')
        self.assertEqual(roster['A-99'], 'Extra member')
        self.assertIn(original, db.list_measurements(context='live', limit=10000))
