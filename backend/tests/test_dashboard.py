import unittest
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import app
from app.dashboard.repository import CrewMember, Metric, get_repository


class Repository:
    def __init__(self, members):
        self.members = members

    def list_crew(self):
        return self.members


class DashboardTests(unittest.TestCase):
    def tearDown(self):
        app.dependency_overrides.clear()

    def snapshot(self, value=72, age=0):
        member = CrewMember(id='test', name='Test Crew', role='Engineer',
                            observed_at=datetime.now(timezone.utc) - timedelta(seconds=age),
                            metrics=[Metric(key='heart', label='Heart rate', value=value,
                                            unit='bpm', lower=50, upper=100, history=[])])
        app.dependency_overrides[get_repository] = lambda: Repository([member])
        response = TestClient(app).get('/api/dashboard')
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_bounds_are_inclusive(self):
        for value in (50, 72, 100):
            data = self.snapshot(value)
            self.assertEqual(data['crew'][0]['status'], 'normal')
            self.assertEqual(data['alerts'], [])

    def test_abnormal_reading_links_alert_to_member_and_is_stable(self):
        data = self.snapshot(101)
        self.assertEqual(data['crew'][0]['status'], 'alert')
        self.assertEqual(data['alerts'][0]['crew_id'], 'test')
        self.assertEqual(TestClient(app).get('/api/dashboard').json()['alerts'], data['alerts'])

    def test_missing_or_stale_data_is_unknown(self):
        self.assertEqual(self.snapshot(None)['crew'][0]['status'], 'unknown')
        self.assertEqual(self.snapshot(72, 301)['crew'][0]['status'], 'unknown')

    def test_stale_abnormal_reading_keeps_exception(self):
        data = self.snapshot(101, 301)
        self.assertTrue(data['crew'][0]['stale'])
        self.assertEqual(len(data['alerts']), 1)

    def test_empty_repository_and_pages(self):
        app.dependency_overrides[get_repository] = lambda: Repository([])
        client = TestClient(app)
        self.assertEqual(client.get('/api/dashboard').json()['crew'], [])
        for path in ('/', '/upload', '/static/dashboard.js', '/static/dashboard.css'):
            self.assertEqual(client.get(path).status_code, 200)


class DemoDataTests(unittest.TestCase):
    def test_fixture_join_and_rule_changes_are_reloaded(self):
        import json
        import shutil
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from app.dashboard.repository import DemoCrewRepository
        from app.routers.dashboard import dashboard

        source = Path(__file__).resolve().parents[2] / 'data'
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('astronauts', 'metrics', 'predictions', 'rules'):
                shutil.copyfile(source / f'{name}.json', root / f'{name}.json')
            repository = DemoCrewRepository(root)
            data = dashboard(repository)
            self.assertEqual(len(data['crew']), 4)
            jordan = next(m for m in data['crew'] if m['id'] == 'A-03')
            self.assertEqual(jordan['status'], 'normal')
            self.assertEqual(jordan['predictions'][0]['score'], .2)
            self.assertEqual(jordan['metrics'][0]['history'], [66, 67, 68])
            rules = json.loads((root / 'rules.json').read_text())
            rules['predictions']['fatigue_risk']['threshold'] = .2
            (root / 'rules.json').write_text(json.dumps(rules))
            data = dashboard(repository)
            self.assertEqual(next(m for m in data['crew'] if m['id'] == 'A-03')['status'], 'alert')
            self.assertTrue(any(a['crew_id'] == 'A-03' and a['metric'] == 'fatigue_risk' for a in data['alerts']))
            rows = json.loads((root / 'metrics.json').read_text())
            (root / 'metrics.json').write_text(json.dumps([r for r in rows if r['astronaut_id'] != 'A-01' or r['key'] != 'oxygen']))
            rules['predictions']['fatigue_risk']['threshold'] = .7
            (root / 'rules.json').write_text(json.dumps(rules))
            self.assertEqual(next(m for m in dashboard(repository)['crew'] if m['id'] == 'A-01')['status'], 'unknown')
