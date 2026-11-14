"""
Voice pipeline: five clips -> POST /api/audio -> voicebiomarker model ->
database -> dashboard prediction -> alerts from data/rules.json, including
the "combined" rule that looks at the vocal biomarker AND heart rate.

Most tests fake the model's output (fast). test_real_model_on_synthetic_voice
runs the real voicebiomarker model on synthetic "voice" (a buzz shaped like
vowels), so it checks the plumbing, not the medicine.

Run from backend/:  python -m pytest -q
"""

import io
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient
from scipy.signal import lfilter

from app.extractors import extract_measurements
from app.main import app
from app.models.voice_model import TASKS
from app.routers import audio, video

SR = 16000
RNG = np.random.default_rng(0)


# ---- synthetic voice (same idea as the voicebiomarker package's own tests)

def vowel(seconds, f0=120.0, formants=(700, 1200, 2500)):
    """A pulse train (the vocal folds) through three resonances (the mouth)."""
    src = np.zeros(int(seconds * SR))
    t = 0.0
    while t < seconds:
        src[int(t * SR)] = 1.0
        t += (1 / f0) * (1 + 0.01 * RNG.standard_normal())
    y = src
    for f in formants:
        r = np.exp(-np.pi * 80 / SR)
        y = lfilter([1 - r], [1, -2 * r * np.cos(2 * np.pi * f / SR), r * r], y)
    return y / (np.max(np.abs(y)) + 1e-9) * 0.3


def counting(seconds, fast=False):
    """Short voiced bursts with pauses, like counting out loud."""
    on, off = (0.25, 0.1) if fast else (0.4, 0.25)
    parts, total = [], 0.0
    while total < seconds:
        parts += [vowel(on, f0=110 + 30 * RNG.random(), formants=(500 + 400 * RNG.random(), 1500, 2500)),
                  np.zeros(int(off * SR))]
        total += on + off
    return np.concatenate(parts)


def wav(y):
    y = (y + 1e-4 * RNG.standard_normal(y.size)).astype(np.float32)
    buf = io.BytesIO()
    sf.write(buf, y, SR, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def synthetic_recording():
    return {
        "counting_normal": wav(counting(14)),
        "counting_fast": wav(counting(10, fast=True)),
        "vowel_a": wav(vowel(6, formants=(750, 1200, 2500))),
        "vowel_e": wav(vowel(6, formants=(450, 2000, 2700))),
        "vowel_o": wav(vowel(6, formants=(500, 900, 2400))),
    }


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
        self.assertEqual(snapshot["alerts"], [])

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
        self.assertEqual(snapshot["alerts"], [])
        self.assertIsNone(crew["A-01"]["predictions"][0]["threshold"])

    def test_four_rising_checks_alert(self):
        for score in (0.75, 1.2, 2.01):
            self.upload_audio("A-01", voice_output(score))
        snapshot, _ = self.dashboard()
        self.assertEqual(snapshot["alerts"], [])          # only 3 checks so far

        self.upload_audio("A-01", voice_output(2.34))     # 4th check, still rising
        snapshot, crew = self.dashboard()
        self.assertEqual(crew["A-01"]["status"], "alert")
        self.assertEqual([a["metric"] for a in snapshot["alerts"]], ["vocal_biomarker_rising"])
        self.assertIn("0.75 → 1.2 → 2.01 → 2.34", snapshot["alerts"][0]["message"])

    def test_a_drop_breaks_the_trend(self):
        for score in (0.75, 1.2, 1.0, 2.01, 2.34):   # last 4: 1.2, 1.0, 2.01, 2.34
            self.upload_audio("A-01", voice_output(score))
        snapshot, _ = self.dashboard()
        self.assertEqual(snapshot["alerts"], [])

    def test_trend_is_per_astronaut(self):
        for astronaut, score in [("A-01", 1), ("A-02", 2), ("A-01", 3), ("A-02", 4)]:
            self.upload_audio(astronaut, voice_output(score))
        snapshot, _ = self.dashboard()
        self.assertEqual(snapshot["alerts"], [])          # 2 checks each

    def test_real_model_on_synthetic_voice(self):
        r = self.post_clips("A-03", clips=synthetic_recording())
        self.assertEqual(r.status_code, 200, r.text)
        result = r.json()["result"]
        self.assertEqual(result["model"], "voicebiomarker")
        self.assertIn(result["status"], ("ok", "rejected"))
        self.assertTrue(result["model_version"])
        if result["status"] == "ok":
            self.assertIsNotNone(result["vocal_biomarker"])
        print("\nreal model on synthetic voice:", result["status"], result["reason"],
              result["vocal_biomarker"], result["log_message"])


if __name__ == "__main__":
    unittest.main()
