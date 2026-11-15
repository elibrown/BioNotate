import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from app import db
from app.data import imports as biologist


class BiologistTests(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.env = patch.dict(os.environ, ASTROHEALTH_DB=str(Path(self.tmp.name) / 'research.db'))
        self.env.start()
        self.csv = Path(self.tmp.name) / 'input.csv'

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_supplied_dataset_roundtrip_and_idempotency(self):
        path = Path(__file__).resolve().parents[2] / 'docs/biologist_docs/Unified_12_Biomarkers_Dataset - temp table.csv'
        result = biologist.import_csv(path)
        self.assertEqual(result['inserted'], 361)
        self.assertEqual(biologist.import_csv(path)['inserted'], 0)
        rows = biologist.observations(result['dataset_id'])
        self.assertEqual(len({row['subject_id'] for row in rows}), 12)
        self.assertEqual(len(biologist.observations(result['dataset_id'], 'I4_C001')), 27)
        self.assertEqual(db.list_measurements(), [])
        self.assertEqual(db.list_astronauts(), [])

    def test_invalid_file_does_not_partially_import(self):
        self.csv.write_text('Astronaut_ID,Chronological_Day,Timepoint_Label,BM01_WBC\nA,1,T1,7\nA,2,T2,nan\n')
        with self.assertRaises(ValueError):
            biologist.import_csv(self.csv)
        self.assertEqual(biologist.datasets(), [])

    def test_blanks_are_missing_and_values_preserved(self):
        self.csv.write_text('Astronaut_ID,Chronological_Day,Timepoint_Label,BM01_WBC,BM03_CRP\nA,-3,L-3,0,\n')
        result = biologist.import_csv(self.csv)
        rows = biologist.observations(result['dataset_id'])
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]['value'], rows[0]['timepoint']), (0, -3))

    def test_api_reads_imported_database(self):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from app.routers.research import router
        app = FastAPI()
        app.include_router(router)
        self.csv.write_text('Astronaut_ID,Chronological_Day,Timepoint_Label,BM01_WBC\nA,1,T1,7\n')
        result = biologist.import_csv(self.csv)
        client = TestClient(app)
        self.assertEqual(len(client.get('/api/research/datasets').json()['datasets']), 1)
        response = client.get('/api/research/datasets/' + result['dataset_id'])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['observations'][0]['value'], 7)
        self.assertEqual(client.get('/api/research/datasets/missing').status_code, 404)

    def test_final_format_preserves_raw_keys_and_labels_phases(self):
        path = Path(__file__).resolve().parents[2] / 'docs/biologist_docs/Four_Astronauts_12_Biomarkers - final table.csv'
        result = biologist.import_csv(path)
        self.assertEqual(result['inserted'], 220)
        self.assertEqual(biologist.import_csv(path)['inserted'], 0)
        rows = biologist.observations(result['dataset_id'])
        self.assertEqual(len({r['subject_id'] for r in rows}), 4)
        self.assertEqual(len({r['timepoint'] for r in rows}), 5)
        self.assertFalse(any(r['metric'] == 'BM12_Skin_Score' for r in rows))
        self.assertTrue(any(r['metric'] == 'BM03_CRP' for r in rows))
        self.assertEqual(rows[0]['timepoint_label'], 'Pre-flight baseline')
        self.assertEqual(len(db.list_measurements()), 220)

    def test_invalid_final_timepoint(self):
        self.csv.write_text('Astronaut_ID,Timepoint,BM01_WBC\nA,6,7\n')
        with self.assertRaises(ValueError):
            biologist.import_csv(self.csv)
        self.assertEqual(biologist.datasets(), [])

    def test_each_crew_member_gets_only_assigned_profile(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.routers.research import router
        path = Path(__file__).resolve().parents[2] / 'docs/biologist_docs/Four_Astronauts_12_Biomarkers - final table.csv'
        biologist.import_csv(path)
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        for i in range(1, 5):
            data = client.get(f'/api/research/crew/A-{i:02d}').json()
            self.assertEqual(len(data['datasets']), 1)
            rows = data['datasets'][0]['observations']
            self.assertEqual(len(rows), 55)
            self.assertEqual({r['subject_id'] for r in rows}, {f'Astronaut {i}'})
            self.assertEqual(data['catalog']['BM03_CRP']['canonical_code'], 'BM03_IL6')
        self.assertEqual(client.get('/api/research/crew/A-99').json()['datasets'], [])
        self.assertEqual(len(db.list_measurements()), 220)
