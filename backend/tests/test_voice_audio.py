"""
Voice pipeline: five clips -> POST /api/audio -> voicebiomarker model ->
database -> dashboard prediction -> alerts from data/rules.json, including
the "combined" rule that looks at the vocal biomarker AND heart rate.

Most tests fake the model's output (fast). The test_real_model_* tests run
the real voicebiomarker model on the sample recordings in data/sample/voice/
(synthetic "voice": a buzz shaped like vowels), so they check the plumbing,
not the medicine.

Run from backend/:  python -m pytest -q
"""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.extractors import extract_measurements
from app.main import app
from app.models.voice_model import TASKS
from app.routers import audio, video

# Synthetic recordings (robotic "voice", made by make_clips.py in the same
# folder). Six days of the same fake person; the real model's score rises
# every day (about 0.75 -> 3.14).
SAMPLE_DIR = Path(__file__).resolve().parents[2] / "data" / "sample" / "voice"


def sample_day(n):
    return {task: (SAMPLE_DIR / f"day{n}" / f"{task}.wav").read_bytes() for task in TASKS}


# ---- fake model outputs

def voice_output(score, status="ok", reason=None):
    ok = status == "ok"
    return {"model": "voicebiomarker", "status": status, "reason": reason,
            "log_message": "", "vocal_biomarker": score if ok else None,
            "quartile": 3 if ok else None,
            "voice_quality": {"f0_median_hz": 208.9, "cpp_db": 15.11, "jitter_pct": None} if ok else {},
            "net_speech_s": 31.4, "windows_used": 2 if ok else 0,
            "model_version": "coswara-cm-0.1.0"}


def cardioresp_output(hr):
    reading = {"timestamp_s": 30.0, "hr_bpm": hr, "respi_rate": 14.0,
               "prq": hr / 14.0, "status": "ok", "log_message": ""}
    return {"model": "cardioresp", "model_version": "0.2.0", "status": "ok",
            "measurements": [reading]}


class ExtractorTests(unittest.TestCase):
    def test_ok_reading_gives_biomarker_and_voice_quality_rows(self):
        rows = extract_measurements(voice_output(0.23))
        self.assertEqual(rows, [
            {"metric": "vocal_biomarker", "value": 0.23, "unit": "z-score"},
            {"metric": "f0_median_hz", "value": 208.9, "unit": "Hz"},
            {"metric": "cpp_db", "value": 15.11, "unit": "dB"},
            # jitter_pct was null: skipped
        ])

    def test_rejected_reading_gives_no_rows(self):
        self.assertEqual(extract_measurements(voice_output(None, "rejected", "low_snr")), [])


def model_alerts(snapshot):
    # Missing-vital warnings share the status report but are not voice-model alerts.
    return [a for a in snapshot['alerts'] if a.get('kind') == 'threshold_or_trend']


class VoicePipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        tmp = Path(self.tmp.name)
        self.patches = [
            patch.dict(os.environ, {"ASTROHEALTH_DB": str(tmp / "test.db")}),
            patch.object(audio, "UPLOAD_DIR", tmp),
            patch.object(video, "UPLOAD_DIR", tmp),
        ]
        for p in self.patches:
            p.start()
        os.environ.pop("ASTROHEALTH_DASHBOARD", None)   # use the database
        self.client = TestClient(app)
        self.upload_dir = tmp

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def post_clips(self, astronaut_id="A-01", clips=None, name="clip.wav"):
        clips = clips or {task: b"fake" for task in TASKS}
        files = {task: (name, data, "audio/wav") for task, data in clips.items()}
        data = {"astronaut_id": astronaut_id} if astronaut_id else {}
        return self.client.post("/api/audio", data=data, files=files)

    def upload_audio(self, astronaut_id, output):
        with patch.object(audio, "run_model", return_value=output):
            r = self.post_clips(astronaut_id)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def upload_video(self, astronaut_id, hr):
        with patch.object(video, "run_model", return_value=cardioresp_output(hr)):
            r = self.client.post("/api/video", data={"astronaut_id": astronaut_id},
                                 files={"file": ("clip.mp4", b"fake", "video/mp4")})
        self.assertEqual(r.status_code, 200, r.text)

    def dashboard(self):
        snapshot = self.client.get("/api/dashboard").json()
        return snapshot, {m["id"]: m for m in snapshot["crew"]}

    def test_tasks_endpoint_lists_the_five_clips(self):
        tasks = self.client.get("/api/audio/tasks").json()
        self.assertEqual([t["field"] for t in tasks], list(TASKS))
        self.assertTrue(all(t["instruction"] for t in tasks))

    def test_rejects_unsupported_format(self):
        self.assertEqual(self.post_clips(name="clip.mp3").status_code, 400)

    def test_missing_clip_is_422(self):
        files = {task: ("clip.wav", b"x", "audio/wav") for task in TASKS[:4]}
        self.assertEqual(self.client.post("/api/audio", files=files).status_code, 422)

    def test_undecodable_audio_is_400_and_nothing_kept(self):
        r = self.post_clips()   # real model; b"fake" is not audio
        self.assertEqual(r.status_code, 400, r.text)
        self.assertEqual([p for p in self.upload_dir.iterdir() if p.is_dir()], [])

    def test_clips_saved_in_one_folder(self):
        body = self.upload_audio("A-01", voice_output(0.2))
        folder = self.upload_dir / body["saved_as"]
        self.assertEqual(sorted(p.stem for p in folder.iterdir()), sorted(TASKS))

    def test_ok_upload_shows_on_dashboard(self):
        body = self.upload_audio("A-01", voice_output(0.23))
        self.assertIn("vocal_biomarker", [m["metric"] for m in body["measurements"]])
        snapshot, crew = self.dashboard()
        [prediction] = crew["A-01"]["predictions"]
        self.assertEqual(prediction["target"], "vocal_biomarker")
        self.assertEqual(prediction["score"], 0.23)
        self.assertEqual(prediction["unit"], "z-score")
        self.assertEqual(prediction["model_version"], "coswara-cm-0.1.0")
        self.assertEqual(model_alerts(snapshot), [])

    def test_rejected_recording_is_saved_with_advice_but_no_measurements(self):
        output = {**voice_output(None, "rejected", "low_snr"), "advice": "Find a quieter place."}
        body = self.upload_audio("A-01", output)
        self.assertEqual(body["measurements"], [])
        self.assertEqual(body["result"]["status"], "rejected")
        _, crew = self.dashboard()
        self.assertEqual(crew["A-01"]["predictions"], [])

    def test_no_alert_for_a_high_score_alone(self):
        self.upload_audio("A-01", voice_output(3.5))   # no fixed numbers any more
        snapshot, crew = self.dashboard()
        self.assertEqual(model_alerts(snapshot), [])
        self.assertIsNone(crew["A-01"]["predictions"][0]["threshold"])

    def test_four_rising_checks_alert(self):
        for score in (0.75, 1.2, 2.01):
            self.upload_audio("A-01", voice_output(score))
        snapshot, _ = self.dashboard()
        self.assertEqual(model_alerts(snapshot), [])          # only 3 checks so far

        self.upload_audio("A-01", voice_output(2.34))     # 4th check, still rising
        snapshot, crew = self.dashboard()
        self.assertEqual(crew["A-01"]["status"], "alert")
        self.assertEqual([a["metric"] for a in model_alerts(snapshot)], ["vocal_biomarker_rising"])
        self.assertIn("0.75 → 1.2 → 2.01 → 2.34", model_alerts(snapshot)[0]["message"])

    def test_a_drop_breaks_the_trend(self):
        for score in (0.75, 1.2, 1.0, 2.01, 2.34):   # last 4: 1.2, 1.0, 2.01, 2.34
            self.upload_audio("A-01", voice_output(score))
        snapshot, _ = self.dashboard()
        self.assertEqual(model_alerts(snapshot), [])

    def test_trend_is_per_astronaut(self):
        for astronaut, score in [("A-01", 1), ("A-02", 2), ("A-01", 3), ("A-02", 4)]:
            self.upload_audio(astronaut, voice_output(score))
        snapshot, _ = self.dashboard()
        self.assertEqual(model_alerts(snapshot), [])          # 2 checks each

    def test_real_model_on_sample_recording(self):
        r = self.post_clips("A-03", clips=sample_day(1))
        self.assertEqual(r.status_code, 200, r.text)
        result = r.json()["result"]
        self.assertEqual(result["model"], "voicebiomarker")
        self.assertEqual(result["status"], "ok")
        self.assertIsNotNone(result["vocal_biomarker"])
        self.assertTrue(result["model_version"])

    def test_real_model_sample_days_rise_and_alert(self):
        scores = []
        for day in (3, 4, 5, 6):   # 4 checks
            r = self.post_clips("A-03", clips=sample_day(day))
            self.assertEqual(r.status_code, 200, r.text)
            scores.append(r.json()["result"]["vocal_biomarker"])
        self.assertEqual(scores, sorted(scores))          # each day higher
        snapshot, crew = self.dashboard()
        self.assertEqual(crew["A-03"]["status"], "alert")
        self.assertEqual([a["metric"] for a in model_alerts(snapshot)], ["vocal_biomarker_rising"])

if __name__ == "__main__":
    unittest.main()
