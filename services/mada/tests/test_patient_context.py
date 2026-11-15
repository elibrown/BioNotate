"""Historical measurements inform the model but never impersonate Check answers."""

import json

import pytest
from pydantic import ValidationError

from mada_agent.prompt_templates import PROMPT_VERSION, render_patient_context
from mada_agent.schemas import Conversation


CONTEXT = {
    "patient_id": "A-02", "responder_is_patient": False, "retrieved_at": "2026-11-14T12:00:00Z",
    "measurements": [{
        "source": "manual", "metric": "hr_bpm", "unit": "bpm",
        "latest_value": 79.0, "latest_measured_at": "2026-11-14T11:58:00Z",
        "observation_count": 2, "delta_from_first": 3.0,
        "first_measured_at": "2026-11-13T11:58:00Z",
    }],
}
TURN = {"role": "responder", "timestamp": "2026-11-14T12:00:00Z", "text": "my crewmate fainted"}


def test_optional_patient_context_is_compatible_with_old_conversations():
    conv = Conversation.model_validate({"turns": [TURN]})
    assert conv.patient_context is None
    assert render_patient_context(conv.patient_context) == ""


def test_patient_context_is_model_visible_and_labeled_untrusted():
    conv = Conversation.model_validate({"turns": [TURN], "patient_context": CONTEXT})
    rendered = render_patient_context(conv.patient_context)
    assert "PATIENT_RECORD_CONTEXT" in rendered
    assert "NOT symptoms" in rendered
    assert '"patient_id":"A-02"' in rendered
    assert '"responder_is_patient":false' in rendered
    assert '"metric":"hr_bpm"' in rendered
    assert PROMPT_VERSION == "v4"


@pytest.mark.parametrize("corruption", [
    {"measurements": CONTEXT["measurements"] * 13},
    {"measurements": [{**CONTEXT["measurements"][0], "latest_value": float("nan")}]},
    {"measurements": [{**CONTEXT["measurements"][0], "diagnosis": "extra"}]},
])
def test_invalid_patient_context_is_rejected(corruption):
    with pytest.raises(ValidationError):
        Conversation.model_validate({"turns": [TURN], "patient_context": {**CONTEXT, **corruption}})
