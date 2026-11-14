import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


class ManualMeasurementTests(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.environment = patch.dict(os.environ, {
            "ASTROHEALTH_DB": str(Path(self.tmp.name) / "manual.db"),
            "ASTROHEALTH_DASHBOARD": "live",
        })
        self.environment.start()
        self.client = TestClient(app)
        self.client.get('/api/dashboard')  # initialize crew roster

    def tearDown(self):
        self.environment.stop()
        self.tmp.cleanup()

    def save(self, metric, value):
        return self.client.post('/api/manual-measurements', json={
            "astronaut_id": "A-01", "metric": metric, "value": value,
            "measured_at": "2026-11-14T15:00:00+02:00",
        })

    def test_each_save_creates_one_row_visible_in_details(self):
        for count, (metric, value) in enumerate([
            ('systolic_bp', 120), ('diastolic_bp', 80), ('glucose', 95), ('temperature_c', 36.7),
        ], 1):
            response = self.save(metric, value)
            self.assertEqual(response.status_code, 201, response.text)
            self.assertEqual(response.json()['metric'], metric)
            self.assertEqual(response.json()['measured_at'], '2026-11-14T13:00:00.000+00:00')
            self.assertEqual(len(self.client.get('/api/measurements').json()), count)
        crew = self.client.get('/api/dashboard').json()['crew']
        self.assertEqual(len(next(member for member in crew if member['id'] == 'A-01')['manual_measurements']), 4)

    def test_invalid_or_bulk_input_does_not_write(self):
        self.assertEqual(self.save('unknown', 10).status_code, 422)
        self.assertEqual(self.save('glucose', 'NaN').status_code, 422)
        response = self.client.post('/api/manual-measurements', json={
            'astronaut_id': 'A-01', 'group_id': 'blood_pressure',
            'values': {'systolic_bp': 120, 'diastolic_bp': 80},
            'measured_at': '2026-11-14T13:00:00Z',
        })
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.get('/api/measurements').json(), [])

    def test_page_and_catalogue(self):
        page = self.client.get('/measurements')
        self.assertEqual(page.status_code, 200)
        self.assertIn('id="manual-value"', page.text)
        self.assertNotIn('id="manual-fields"', page.text)
        self.assertEqual(len(self.client.get('/api/measurement-catalog').json()['metrics']), 4)
