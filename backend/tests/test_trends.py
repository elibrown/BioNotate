import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from app import db
from app.data import trends


class TrendCalculationTests(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.env = patch.dict(os.environ, ASTROHEALTH_DB=str(Path(self.tmp.name) / 'trends.db'))
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_calculates_net_change_in_time_order_and_keeps_sources_separate(self):
        for hour, value in [(3, 75), (1, 70), (2, 80)]:
            db.add_measurement('A-01', 'hr_bpm', value, unit='bpm', source='cardioresp',
                               measured_at=f'2026-11-15T0{hour}:00:00.000+00:00')
        db.add_measurement('A-01', 'hr_bpm', 95, unit='bpm', source='manual')
        series = trends.measurement_trends('A-01', metric='hr_bpm')
        self.assertEqual(len(series), 2)
        model = next(s for s in series if s['source'] == 'cardioresp')
        self.assertEqual([p['value'] for p in model['points']], [70, 80, 75])
        self.assertEqual(model['summary']['delta'], 5)
        self.assertEqual(model['summary']['minimum'], 70)
        self.assertEqual(model['summary']['maximum'], 80)
        self.assertAlmostEqual(model['summary']['percent_change'], 100 * 5 / 70)
        self.assertEqual(model['summary']['direction'], 'rising')  # net change, not monotonicity
        single = next(s for s in series if s['source'] == 'manual')
        self.assertIsNone(single['summary']['delta'])
        self.assertEqual(single['summary']['direction'], 'insufficient_data')

    def test_zero_baseline_has_no_percentage_and_missing_crew_has_no_series(self):
        for hour, value in [(1, 0), (2, 5)]:
            db.add_measurement('A-01', 'example', value, measured_at=f'2026-11-15T0{hour}:00:00+00:00')
        summary = trends.measurement_trends('A-01')[0]['summary']
        self.assertEqual(summary['delta'], 5)
        self.assertIsNone(summary['percent_change'])
        self.assertEqual(trends.measurement_trends('A-99'), [])

    def test_metric_and_unit_aliases_share_canonical_identity(self):
        db.add_measurement('A-01', 'heart_rate', 75, unit='BPM', source='simulation')
        db.add_measurement('A-01', 'hr_bpm', 72, unit='bpm', source='cardioresp')
        for key in ('hr_bpm', 'heart_rate'):
            series = trends.measurement_trends('A-01', metric=key)
            self.assertEqual(len(series), 2)
            self.assertEqual({s['metric'] for s in series}, {'hr_bpm'})
            self.assertEqual({s['unit'] for s in series}, {'bpm'})
        self.assertEqual(db.list_measurements(source='simulation')[0]['metric'], 'heart_rate')
