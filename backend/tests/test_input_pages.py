import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import db
from app.main import app
from app.routers import audio
from app.seed_demo import seed_dashboard


class InputPageTests(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.environment = patch.dict(os.environ, {
            'ASTROHEALTH_DB': str(Path(self.tmp.name) / 'test.db'),
            'ASTROHEALTH_DASHBOARD': 'live',
        })
        self.environment.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.environment.stop()
        self.tmp.cleanup()

    def test_seed_is_repeatable_and_replay_yields_statuses(self):
        self.assertGreater(seed_dashboard(), 0)
        self.assertEqual(seed_dashboard(), 0)
        snapshot = self.client.get('/api/dashboard').json()
        self.assertEqual(snapshot['mode'], 'simulation')
        self.assertEqual(sorted(member['status'] for member in snapshot['crew']),
                         ['alert', 'alert', 'normal', 'normal'])
        self.assertFalse(any(member['stale'] for member in snapshot['crew']))
        db.add_measurement('A-01', 'hr_bpm', 72, 'bpm', source='cardioresp')
        self.assertEqual(self.client.get('/api/dashboard').json()['mode'], 'live')

    def test_audio_saves_without_claiming_analysis(self):
        with patch.object(audio, 'UPLOAD_DIR', Path(self.tmp.name)):
            response = self.client.post('/api/audio', files={'file': ('check.wav', b'audio fixture')})
            self.assertEqual(response.status_code, 201)
            result = response.json()
            self.assertEqual(result['analysis_status'], 'not_implemented')
            self.assertEqual((Path(self.tmp.name) / result['saved_as']).read_bytes(), b'audio fixture')
            self.assertEqual(self.client.post('/api/audio', files={'file': ('empty.wav', b'')}).status_code, 400)
            self.assertEqual(self.client.post('/api/audio', files={'file': ('bad.txt', b'x')}).status_code, 400)

    def test_all_pages_share_sidebar_links(self):
        for path in ('/', '/measurements', '/upload', '/audio'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            for href in ('/', '/measurements', '/upload', '/audio'):
                self.assertIn(f'href="{href}"', response.text)
