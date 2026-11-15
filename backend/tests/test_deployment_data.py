import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.main import app


class PackagedDataStartupTests(TestCase):
    def test_startup_exposes_all_biology_metrics_and_restart_does_not_duplicate(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ,
                ASTROHEALTH_DB=str(Path(directory) / 'deployed.db'),
                ASTROHEALTH_IMPORT_BIOLOGY='true'):
            with TestClient(app) as client:
                values = client.get('/api/measurements', params={'source': 'biologist_csv'}).json()
                self.assertEqual(len(values), 220)
                self.assertEqual({r['astronaut_id'] for r in values}, {'A-01', 'A-02', 'A-03', 'A-04'})
                for i in range(1, 5):
                    series = client.get('/api/measurements/trends', params={
                        'astronaut_id': f'A-{i:02d}', 'source': 'biologist_csv'}).json()['series']
                    self.assertEqual(len(series), 11)
                    self.assertTrue(all(len(item['points']) == 5 for item in series))
            with TestClient(app) as client:
                self.assertEqual(len(client.get('/api/measurements', params={'source': 'biologist_csv'}).json()), 220)
