from __future__ import annotations

import io
import json
import math
import struct
import wave

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from PIL import Image

from mada_agent.llm_client import LlamaClient
from mada_agent.main import create_app

from .conftest import HashEmbedding

LLAMA = "http://llama.test"


def _completion(decision: dict) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(decision)}}]})


def _decision(**kw):
    d = {"rationale": "test", "patient_is_responder": False, "chest_pain_reported": False,
         "observed_features": [], "action": "finalize", "check_ids": [], "protocol_ids": []}
    d.update(kw)
    return d


@pytest.fixture
def mock_llama():
    with respx.mock(base_url=LLAMA, assert_all_called=False) as m:
        yield m


@pytest.fixture
def client(settings, mock_llama):
    llm = LlamaClient(LLAMA, timeout_s=2)
    app = create_app(settings, llm=llm, embedding_factory=HashEmbedding, run_probe=False)
    with TestClient(app) as c:
        yield c


def _conv(*turns):
    return {"conversation": json.dumps({"turns": list(turns)})}


def _rt(text=None, answers=None, ts="2026-11-14T12:00:00Z"):
    return {"role": "responder", "timestamp": ts, "text": text, "check_answers": answers or {}}


def _at(asked=(), ts="2026-11-14T12:01:00Z"):
    return {"role": "agent", "timestamp": ts, "asked_check_ids": list(asked)}


def test_protocols_and_checks_endpoints(client):
    p = client.get("/api/v1/clinical/protocols").json()
    assert len(p["protocols"]) == 11 and len(p["first_steps"]) == 2
    c = client.get("/api/v1/clinical/checks").json()
    assert any(x["id"] == "GCS" and x["status"] == "SOURCED" for x in c["checks"])


def test_health_ok_when_probe_disabled(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["knowledge"]["protocols"] == 11


def test_model_finalize_returns_verbatim_steps_and_first_steps(client, mock_llama):
    route = mock_llama.post("/v1/chat/completions").mock(
        return_value=_completion(_decision(protocol_ids=["ANAPHYLAXIS"])))
    r = client.post("/api/v1/clinical/analyze",
                    data=_conv(_rt("she ate a ration bar, lips swelling, throat tight")))
    body = r.json()
    assert r.status_code == 200, body
    assert body["action"] == "finalize" and body["severity"] == "life_threatening"
    assert body["first_steps"][1].startswith("S2. CALL THE CREW MEDICAL OFFICER")
    assert body["protocols"][0]["steps"][1].startswith("2. EPINEPHRINE (IMMEDIATE): Inject Epinephrine 0.3 mg")
    sent = json.loads(route.calls.last.request.content)
    assert sent["response_format"]["type"] == "json_schema"
    assert "ANAPHYLAXIS" in sent["response_format"]["json_schema"]["schema"]["properties"]["protocol_ids"]["items"]["enum"]


def test_patient_history_reaches_llm_but_is_not_a_fast_path_check(client, mock_llama):
    route = mock_llama.post("/v1/chat/completions").mock(
        return_value=_completion(_decision()))
    conversation = {"turns": [_rt("feels lightheaded")], "patient_context": {
        "patient_id": "A-02", "retrieved_at": "2026-11-14T12:00:00Z",
        "measurements": [{
            "source": "manual", "metric": "hr_bpm", "unit": "bpm",
            "latest_value": 83, "latest_measured_at": "2026-11-14T11:55:00Z",
            "observation_count": 2, "delta_from_first": 3,
            "first_measured_at": "2026-11-13T11:55:00Z",
        }],
    }}
    response = client.post("/api/v1/clinical/analyze", data={"conversation": json.dumps(conversation)})
    assert response.status_code == 200, response.text
    assert route.called  # History cannot trigger a deterministic fast path.
    request = json.loads(route.calls.last.request.content)
    prompt = request["messages"][-1]["content"][-1]["text"]
    assert "PATIENT_RECORD_CONTEXT" in prompt
    assert '"patient_id":"A-02"' in prompt
    assert '"latest_value":83.0' in prompt
    assert "NOT symptoms" in prompt
    assert "PATIENT_RECORD_CONTEXT" not in request["messages"][0]["content"]


def test_unknown_protocol_ids_are_dropped(client, mock_llama):
    mock_llama.post("/v1/chat/completions").mock(
        return_value=_completion(_decision(protocol_ids=["MADE_UP", "STROKE"])))
    body = client.post("/api/v1/clinical/analyze", data=_conv(_rt("feels weird"))).json()
    assert body["protocols"] == [] and body["no_protocol_match"] and "Crew Medical Officer" in body["message"]


def test_fast_path_rule_skips_model(client, mock_llama):
    route = mock_llama.post("/v1/chat/completions")
    body = client.post("/api/v1/clinical/analyze", data=_conv(
        _rt("collapsed"), _at(["RESPONSIVENESS", "NORMAL_BREATHING"]),
        _rt(answers={"RESPONSIVENESS": "no_response", "NORMAL_BREATHING": "not_breathing"},
            ts="2026-11-14T12:02:00Z"))).json()
    assert not route.called
    assert body["decided_by"] == "fast_path_rule" and body["protocols"][0]["id"] == "CPR"


def test_chest_pain_forces_pneumothorax_checks(client, mock_llama):
    mock_llama.post("/v1/chat/completions").mock(return_value=_completion(
        _decision(chest_pain_reported=True, patient_is_responder=True, protocol_ids=["CHEST_PAIN"])))
    body = client.post("/api/v1/clinical/analyze", data=_conv(_rt("my chest hurts"))).json()
    assert body["action"] == "ask_checks"
    assert {c["id"] for c in body["next_checks"]} >= {"BREATHING_DIFFICULTY", "NECK_VEINS"}


def test_round_limit_forces_finalize(client, mock_llama):
    mock_llama.post("/v1/chat/completions").mock(return_value=_completion(
        _decision(action="ask_checks", check_ids=["PAIN"], protocol_ids=["RENAL_STONE_COLIC"])))
    turns = [_rt("severe pain in side and back coming in waves, blood in urine")]
    for i in range(3):
        turns += [_at(["PULSE_COUNT"], ts=f"2026-11-14T12:0{2*i+1}:00Z"),
                  _rt(answers={"PULSE_COUNT": 90}, ts=f"2026-11-14T12:0{2*i+2}:00Z")]
    body = client.post("/api/v1/clinical/analyze", data=_conv(*turns)).json()
    assert body["action"] == "finalize" and body["round"] == 3
    assert body["protocols"][0]["id"] == "RENAL_STONE_COLIC" and body["severity"] == "urgent"


def test_gcs_alert_in_response(client, mock_llama):
    mock_llama.post("/v1/chat/completions").mock(return_value=_completion(
        _decision(action="ask_checks", check_ids=["GCS"])))
    body = client.post("/api/v1/clinical/analyze", data=_conv(
        _rt("he hit his head", {"RESPONSIVENESS": "responds_to_voice", "GCS": {"eye": 4, "verbal": 5, "motor": 6}}),
        _at(["GCS"], ts="2026-11-14T12:05:00Z"),
        _rt(answers={"GCS": {"eye": 2, "verbal": 2, "motor": 5}}, ts="2026-11-14T12:10:00Z"))).json()
    assert body["gcs"]["latest"] == "E2 V2 M5" and body["gcs"]["total"] == 9
    assert body["gcs_alert"]["rule"] == "drop_eye_or_verbal_ge_3"


def test_model_down_gives_degraded_response(client, mock_llama):
    mock_llama.post("/v1/chat/completions").mock(side_effect=httpx.ConnectError("down"))
    body = client.post("/api/v1/clinical/analyze",
                       data=_conv(_rt("kidney stone flank pain blood in urine"))).json()
    assert body["degraded"] and body["decided_by"] == "retrieval_only"
    assert body["first_steps"] and body["protocols"]


def test_bad_json_from_model_gives_degraded(client, mock_llama):
    mock_llama.post("/v1/chat/completions").mock(return_value=httpx.Response(
        200, json={"choices": [{"message": {"content": "not json"}}]}))
    body = client.post("/api/v1/clinical/analyze", data=_conv(_rt("help"))).json()
    assert body["degraded"]


def test_conversation_validation(client):
    r = client.post("/api/v1/clinical/analyze", data={"conversation": "{not json"})
    assert r.status_code == 422
    r = client.post("/api/v1/clinical/analyze", data=_conv(_at(["PAIN"])))
    assert r.status_code == 422


def _png(w=2000, h=1000) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (255, 0, 0)).save(buf, format="PNG")
    return buf.getvalue()


def _wav(seconds: float, rate=44100) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        n = int(seconds * rate)
        w.writeframes(b"".join(struct.pack("<hh", int(3000 * math.sin(i / 20)), 0) for i in range(n)))
    return buf.getvalue()


def test_image_and_audio_are_sent_to_model(client, mock_llama):
    route = mock_llama.post("/v1/chat/completions").mock(
        return_value=_completion(_decision(protocol_ids=["ANAPHYLAXIS"])))
    r = client.post("/api/v1/clinical/analyze", data=_conv(_rt("rash after food")),
                    files={"image": ("rash.png", _png(), "image/png"),
                           "audio": ("breath.wav", _wav(2.0), "audio/wav")})
    assert r.status_code == 200, r.text
    content = json.loads(route.calls.last.request.content)["messages"][-1]["content"]
    types = [p["type"] for p in content]
    assert types[:2] == ["image_url", "input_audio"]
    img = Image.open(io.BytesIO(__import__("base64").b64decode(content[0]["image_url"]["url"].split(",")[1])))
    assert max(img.size) <= 896
    wav = wave.open(io.BytesIO(__import__("base64").b64decode(content[1]["input_audio"]["data"])))
    assert wav.getframerate() == 16000 and wav.getnchannels() == 1


def test_media_errors(client):
    r = client.post("/api/v1/clinical/analyze", data=_conv(_rt("x")),
                    files={"audio": ("long.wav", _wav(31.5, rate=8000), "audio/wav")})
    assert r.status_code == 413
    r = client.post("/api/v1/clinical/analyze", data=_conv(_rt("x")),
                    files={"image": ("x.png", b"not an image", "image/png")})
    assert r.status_code == 400
    r = client.post("/api/v1/clinical/analyze", data=_conv(_rt("x")),
                    files={"image": ("x.pdf", b"%PDF", "application/pdf")})
    assert r.status_code == 415


def test_checks_the_responder_could_not_do_are_not_reasked(client, mock_llama):
    mock_llama.post("/v1/chat/completions").mock(return_value=_completion(
        _decision(action="ask_checks", chest_pain_reported=True, patient_is_responder=True,
                  check_ids=["NECK_VEINS", "PULSE_COUNT"], protocol_ids=["CHEST_PAIN"])))
    body = client.post("/api/v1/clinical/analyze", data=_conv(
        _rt("chest pain"), _at(["BREATHING_DIFFICULTY", "NECK_VEINS"]),
        _rt("I can't check those", answers={}, ts="2026-11-14T12:03:00Z"))).json()
    assert [c["id"] for c in body["next_checks"]] == ["PULSE_COUNT"]
