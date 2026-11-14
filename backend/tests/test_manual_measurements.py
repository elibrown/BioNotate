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

    def save(self, group, values):
        return self.client.post('/api/manual-measurements', json={
            "astronaut_id": "A-01", "group_id": group, "values": values,
            "measured_at": "2026-11-14T15:00:00+02:00",
        })

    def test_pressure_and_temperature_are_stored_and_displayed(self):
        response = self.save('BM08_PTT_Blood_Pressure', {"systolic_bp": 120, "diastolic_bp": 80})
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual({row['unit'] for row in response.json()}, {'mmHg'})
        self.assertEqual({row['measured_at'] for row in response.json()}, {'2026-11-14T13:00:00.000+00:00'})
        self.assertEqual(self.save('VITALS', {'temperature_c': 36.7}).status_code, 201)
        crew = self.client.get('/api/dashboard').json()['crew']
        manual = next(member for member in crew if member['id'] == 'A-01')['manual_measurements']
        self.assertEqual({row['metric'] for row in manual}, {'systolic_bp', 'diastolic_bp', 'temperature_c'})

    def test_invalid_panel_does_not_write_partial_readings(self):
        for group, values in [
            ('BM08_PTT_Blood_Pressure', {'systolic_bp': 120}),
            ('VITALS', {'unknown_analyte': 10}),
            ('BM05_Urine_Proteomics_UTI', {'protein': 10}),
            ('VITALS', {'temperature_c': 'NaN'}),
        ]:
            with self.subTest(group=group, values=values):
                self.assertEqual(self.save(group, values).status_code, 422)
        self.assertEqual(self.client.get('/api/measurements').json(), [])

    def test_catalogue_registers_all_twelve_biomarker_groups(self):
        groups = self.client.get('/api/measurement-catalog').json()['groups']
        self.assertEqual({group['id'].split('_')[0] for group in groups},
                         {'VITALS', *(f'BM{i:02}' for i in range(1, 13))})
