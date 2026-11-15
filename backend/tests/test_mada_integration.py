"""AstroHealth <-> MADA contract tests, without a GPU or remote model server."""
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app import db
from app.main import app
from app import mada_client, mada_storage


FIRST_STEPS = ["S1. SCENE SAFETY: Check surroundings.", "S2. CALL THE CREW MEDICAL OFFICER: Alert them now."]
ASK_CHECKS = {
    "prompt_version": "v3", "model_quant": "Gemma 4 E2B", "degraded": False,
    "action": "ask_checks", "first_steps": FIRST_STEPS, "severity": None,
    "protocols": [], "no_protocol_match": False, "message": None,
    "next_checks": [{"id": "BREATHING_DIFFICULTY", "title": "Breathing difficulty",
                     "instruction": "Observe speech.", "status": "UNVALIDATED",
                     "answer": {"type": "choice", "options": ["no_difficulty", "severe_single_words_or_cannot_speak"]}}],
    "gcs": {"latest": None, "total": None, "history": []}, "gcs_alert": None,
    "answer_warnings": [], "observed_features": [], "rationale": "Unconfirmed",
    "decided_by": "model", "round": 0, "disclaimer": "Prototype only",
}
FINAL = {
    **ASK_CHECKS, "action": "finalize", "severity": "urgent", "next_checks": [],
    "protocols": [{"id": "CHEST_PAIN", "title": "CHEST PAIN", "severity": "urgent",
                   "steps": ["1. Contact Crew Medical Officer."]}],
    "round": 1,
}


class MadaIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.env = patch.dict(os.environ, {
            "ASTROHEALTH_DB": str(Path(self.tmp.name) / "test.db"),
            "MADA_DEMO_ENABLED": "1", "MADA_SERVICE_URL": "http://mada.test:8000",
        })
        self.env.start()
        self.client = TestClient(app)
        db.add_astronauts([
            {"id": "A-01", "name": "Alex", "role": "Engineer"},
            {"id": "A-02", "name": "Sam", "role": "Scientist"},
        ])

    def tearDown(self):
        self.client.close()
        self.env.stop()
        self.tmp.cleanup()

    def send(self, result, **fields):
        with patch.object(mada_client, "request_mada", new_callable=AsyncMock, return_value=result) as mocked:
            response = self.client.post("/api/mada/assess", data={
                "patient_id": "A-02", "responder_id": "A-01", "text": "Having chest pain", **fields,
            })
        return response, mocked

    def test_patient_is_a_roster_identity(self):
        patients = self.client.get("/api/patients")
        self.assertEqual(patients.status_code, 200)
        self.assertEqual({p["id"] for p in patients.json()}, {"A-01", "A-02"})
        r, mock = self.send(FINAL, patient_id="X-99")
        self.assertEqual(r.status_code, 422)
        mock.assert_not_awaited()

    def test_assessment_saved_with_distinct_patient_and_responder(self):
        r, mock = self.send(ASK_CHECKS)
        self.assertEqual(r.status_code, 200, r.text)
        result = r.json()
        self.assertEqual(result["patient"]["id"], "A-02")
        self.assertEqual(result["responder_id"], "A-01")
        self.assertEqual(result["assessment"]["first_steps"], FIRST_STEPS)
        mock.assert_awaited_once()
        detail = self.client.get(f"/api/mada/assessments/{result['assessment_id']}")
        self.assertEqual(detail.status_code, 200)
        saved = detail.json()
        self.assertEqual(saved["patient_id"], "A-02")
        self.assertEqual(saved["responder_id"], "A-01")
        self.assertEqual(saved["turns"][0]["text"], "Having chest pain")
        self.assertEqual(saved["turns"][1]["asked_check_ids"], ["BREATHING_DIFFICULTY"])
        self.assertEqual(len(self.client.get("/api/patients/A-02/mada-assessments").json()), 1)
        self.assertEqual(self.client.get("/api/patients/A-01/mada-assessments").json(), [])

    def test_followup_sends_full_conversation_and_saves_final(self):
        first, _ = self.send(ASK_CHECKS)
        assessment_id = first.json()["assessment_id"]
        r, mocked = self.send(FINAL, assessment_id=assessment_id,
                              check_answers='{"BREATHING_DIFFICULTY":"no_difficulty"}', text="")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["assessment_id"], assessment_id)
        call = mocked.await_args
        conversation = __import__('json').loads(call.kwargs["data"]["conversation"])
        self.assertEqual([t["role"] for t in conversation["turns"]],
                         ["responder", "agent", "responder"])
        self.assertEqual(conversation["turns"][2]["check_answers"],
                         {"BREATHING_DIFFICULTY": "no_difficulty"})
        self.assertTrue(all('T' in t['timestamp'] for t in conversation['turns']))
        stored = self.client.get(f"/api/mada/assessments/{assessment_id}").json()
        self.assertEqual(len(stored["turns"]), 4)
        self.assertEqual(stored["turns"][3]["protocol_ids"], ["CHEST_PAIN"])
        self.assertEqual(stored["latest_response"]["action"], "finalize")

    def test_cross_patient_followup_forbidden(self):
        first, _ = self.send(ASK_CHECKS)
        r, mock = self.send(FINAL, assessment_id=first.json()["assessment_id"], patient_id="A-01")
        self.assertEqual(r.status_code, 409)
        mock.assert_not_awaited()

    def test_reject_bad_media_and_empty_assessment(self):
        with patch.object(mada_client, 'request_mada', new_callable=AsyncMock) as upstream:
            bad = self.client.post('/api/mada/assess', data={"patient_id": "A-02", "text": "hello"},
                                   files={"image": ("test.txt", b"bad", "text/plain")})
        self.assertEqual(bad.status_code, 415)
        upstream.assert_not_awaited()
        empty = self.client.post('/api/mada/assess', data={"patient_id": "A-02", "text": ""})
        self.assertEqual(empty.status_code, 422)

    def test_disabled_gate_blocks_sensitive_history_and_assessment(self):
        os.environ["MADA_DEMO_ENABLED"] = "0"
        self.assertEqual(self.client.get("/api/mada/status").json()["demo_enabled"], False)
        self.assertEqual(self.client.post('/api/mada/assess', data={"patient_id": "A-02", "text": "Hello"}).status_code, 503)
        self.assertEqual(self.client.get('/api/patients/A-02/mada-assessments').status_code, 503)
        # Metric trends are still available through existing public dashboard APIs.
        self.assertEqual(self.client.get('/api/patients/A-02/trends').status_code, 200)

    def test_trend_collapses_many_samples_from_one_prediction(self):
        # Two video runs (3 points each); one manual observation for another metric.
        for values in ((70, 71, 72), (80, 81, 82)):
            db.save_prediction(
                {"model": "cardioresp", "status": "ok", "model_version": "0.2"},
                astronaut_id="A-02",
                measurements=[{"metric": "hr_bpm", "value": value,
                               "unit": "bpm", "offset_s": i} for i, value in enumerate(values)],
            )
        db.add_measurement("A-02", "temperature_c", 36.5, "C", source="manual")
        report = self.client.get('/api/patients/A-02/trends').json()
        hr = next(m for m in report['metrics'] if m['metric'] == 'hr_bpm')
        self.assertEqual(hr['observations'], 2)
        self.assertEqual(hr['first']['value'], 71)
        self.assertEqual(hr['latest']['value'], 81)
        self.assertEqual(hr['delta'], 10)
        self.assertEqual(hr['direction'], 'increasing')
        temp = next(m for m in report['metrics'] if m['metric'] == 'temperature_c')
        self.assertEqual(temp['direction'], 'insufficient_data')
        self.assertEqual(self.client.get('/api/patients/UNKNOWN/trends').status_code, 422)

    def test_patient_context_is_sent_from_selected_patient_only(self):
        # A-02: one prediction is three HR readings, but only one observation.
        db.save_prediction(
            {"model": "cardioresp", "status": "ok", "model_version": "0.2"},
            astronaut_id="A-02", measurements=[
                {"metric": "hr_bpm", "value": v, "unit": "bpm", "offset_s": i}
                for i, v in enumerate([70, 71, 72])],
        )
        db.save_prediction(
            {"model": "cardioresp", "status": "ok", "model_version": "0.2"},
            astronaut_id="A-02", measurements=[
                {"metric": "hr_bpm", "value": v, "unit": "bpm", "offset_s": i}
                for i, v in enumerate([80, 81, 82])],
        )
        # This must NEVER be included with a different selected patient.
        db.add_measurement("A-01", "secret_other_person", 999, "X", source="manual")
        result, mocked = self.send(FINAL)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["patient_context_metrics_sent"], 1)
        conversation = __import__('json').loads(mocked.await_args.kwargs["data"]["conversation"])
        self.assertEqual(conversation["patient_context"]["patient_id"], "A-02")
        self.assertIs(conversation["patient_context"]["responder_is_patient"], False)
        self.assertEqual(len(conversation["patient_context"]["measurements"]), 1)
        metric = conversation["patient_context"]["measurements"][0]
        self.assertEqual(metric["metric"], "hr_bpm")
        self.assertEqual(metric["latest_value"], 81)
        self.assertEqual(metric["observation_count"], 2)
        self.assertEqual(metric["delta_from_first"], 10)
        self.assertNotIn("secret_other_person", str(conversation))
        self.assertNotIn("Sam", str(conversation))  # No patient name needed by model.

    def test_followup_refreshes_patient_context_and_never_uses_responder_data(self):
        first, mocked = self.send(ASK_CHECKS)
        self.assertEqual(first.status_code, 200)
        initial = __import__('json').loads(mocked.await_args.kwargs["data"]["conversation"])
        self.assertEqual(initial["patient_context"]["measurements"], [])
        db.add_measurement("A-02", "temperature_c", 36.5, "C", source="manual")
        follow, mocked = self.send(
            FINAL, assessment_id=first.json()["assessment_id"], text="",
            check_answers='{"BREATHING_DIFFICULTY":"no_difficulty"}',
        )
        self.assertEqual(follow.status_code, 200, follow.text)
        later = __import__('json').loads(mocked.await_args.kwargs["data"]["conversation"])
        self.assertEqual(later["patient_context"]["patient_id"], "A-02")
        self.assertEqual(later["patient_context"]["measurements"][0]["metric"], "temperature_c")
        self.assertEqual(len(later["turns"]), 3)
        self.assertNotIn("patient_context", str(mada_storage.get_assessment(follow.json()["assessment_id"])["turns"]))

    def test_patient_responder_match_is_explicit_to_agent(self):
        result, mocked = self.send(FINAL, responder_id="A-02")
        self.assertEqual(result.status_code, 200, result.text)
        conv = __import__('json').loads(mocked.await_args.kwargs["data"]["conversation"])
        self.assertIs(conv["patient_context"]["responder_is_patient"], True)

    def test_context_is_bounded_for_large_patient_history(self):
        for i in range(20):
            db.add_measurement("A-02", f"metric_{i:02}", i, "unit", source="manual")
        result, mocked = self.send(FINAL)
        self.assertEqual(result.status_code, 200, result.text)
        conversation = __import__('json').loads(mocked.await_args.kwargs["data"]["conversation"])
        self.assertEqual(len(conversation["patient_context"]["measurements"]), 12)
        self.assertEqual(result.json()["patient_context_metrics_sent"], 12)

    def test_unconfigured_model_rejected_without_creating_session(self):
        os.environ.pop("MADA_SERVICE_URL")
        response = self.client.post('/api/mada/assess', data={
            "patient_id": "A-02", "text": "headache",
        })
        self.assertEqual(response.status_code, 503)
        self.assertEqual(mada_storage.list_assessments("A-02"), [])

    def test_media_forwarded_only_not_stored(self):
        with patch.object(mada_client, 'request_mada', new_callable=AsyncMock, return_value=FINAL) as upstream:
            r = self.client.post('/api/mada/assess', data={"patient_id": "A-02", "text": "Cough"},
                                 files={"audio": ("voice.webm", b"fake-audio-bytes", "audio/webm")})
        self.assertEqual(r.status_code, 200, r.text)
        audio = upstream.await_args.kwargs["files"]["audio"]
        self.assertEqual(audio[0], "voice.webm")
        self.assertEqual(audio[1], b"fake-audio-bytes")
        saved = mada_storage.get_assessment(r.json()["assessment_id"])
        self.assertNotIn('fake-audio-bytes', str(saved))

    def test_ui_page_and_static_assets(self):
        self.assertEqual(self.client.get('/mada').status_code, 200)
        self.assertIn('Identify the Patient', self.client.get('/mada').text)
        self.assertEqual(self.client.get('/static/mada.js').status_code, 200)


if __name__ == '__main__':
    unittest.main()
