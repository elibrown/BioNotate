"""
Shared seed data (app/seed.py): export the database to a text file, and
load that file into an empty database when the backend starts.

Run from backend/:  python -m pytest -q
"""

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import db
from app.data import management as seed
from app.main import app


def counts() -> dict[str, int]:
    return {table: len(rows) for table, rows in db.dump_tables().items()}


class SeedTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.seed_file = self.dir / "seed" / "astrohealth_seed.json"

    def tearDown(self):
        self.tmp.cleanup()

    def use_db(self, name: str):
        return patch.dict(os.environ, {"ASTROHEALTH_DB": str(self.dir / name)})

    def fill_source_db(self):
        db.add_astronauts([{"id": "A-01", "name": "Ada", "role": "Commander"}])
        db.save_prediction(
            {"model": "cardioresp", "model_version": "0.2.0", "status": "ok"},
            astronaut_id="A-01",
            video_file="clip.mp4",
            measurements=[{"metric": "hr_bpm", "value": 72.0, "unit": "bpm", "offset_s": 30.0},
                          {"metric": "hr_bpm", "value": 73.5, "unit": "bpm", "offset_s": 31.0}],
        )
        db.add_measurement("A-01", "glucose_mg_dl", 95.0, unit="mg/dL",
                           measured_at="2026-11-14T08:00:00.000+00:00")

    def test_export_then_load_gives_the_same_rows(self):
        with self.use_db("source.db"):
            self.fill_source_db()
            seed.export_seed(self.seed_file)
            original = db.dump_tables()
        with self.use_db("fresh.db"):
            added = seed.load_seed_if_empty(self.seed_file)
            self.assertEqual(added, {"astronauts": 1, "predictions": 1, "measurements": 3})
            self.assertEqual(db.dump_tables(), original)   # same ids, links and values

    def test_file_has_one_row_per_line_and_is_stable(self):
        with self.use_db("source.db"):
            self.fill_source_db()
            seed.export_seed(self.seed_file)
            first = self.seed_file.read_bytes()
            seed.export_seed(self.seed_file)
            self.assertEqual(self.seed_file.read_bytes(), first)   # no churn in git
        text = first.decode("utf-8")
        self.assertNotIn("\r", text)
        self.assertEqual(json.loads(text)["measurements"][0]["metric"], "hr_bpm")
        row_lines = [l for l in text.splitlines() if l.startswith("    {")]
        self.assertEqual(len(row_lines), 5)   # 1 astronaut + 1 prediction + 3 measurements

    def test_database_with_data_is_not_touched(self):
        with self.use_db("source.db"):
            self.fill_source_db()
            seed.export_seed(self.seed_file)
        with self.use_db("mine.db"):
            db.add_measurement("A-09", "hr_bpm", 60.0)
            self.assertIsNone(seed.load_seed_if_empty(self.seed_file))
            self.assertEqual(counts(), {"astronauts": 0, "predictions": 0, "measurements": 1})

    def test_missing_seed_file_is_fine(self):
        with self.use_db("fresh.db"):
            self.assertIsNone(seed.load_seed_if_empty(self.dir / "nope.json"))

    def test_backend_startup_loads_the_seed(self):
        with self.use_db("source.db"):
            self.fill_source_db()
            seed.export_seed(self.seed_file)
        with self.use_db("fresh.db"), patch.object(seed, "SNAPSHOT_FILE", self.dir / "absent.db"), patch.object(seed, "SEED_FILE", self.seed_file), \
             patch("app.data.management.load_seed_if_empty.__defaults__", (self.seed_file,)):
            with TestClient(app) as client:   # "with" runs the startup code
                predictions = client.get("/api/predictions").json()
            self.assertEqual(len(predictions), 1)
            self.assertEqual(predictions[0]["astronaut_id"], "A-01")


if __name__ == "__main__":
    unittest.main()
