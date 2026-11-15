from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from mada_agent import checks as chk
from mada_agent.gcs import GcsError, check_trend, parse_reading
from mada_agent.knowledge import display_step

T0 = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)


# ---------- knowledge ----------
def test_all_protocols_loaded_with_severity(kb):
    assert len(kb.protocols) == 11
    assert kb.life_threatening_ids == {"CPR", "CHOKING", "ANAPHYLAXIS", "PNEUMOTHORAX", "CO2_TOXIC_INHALATION"}
    assert kb.max_severity(["CHEST_PAIN", "CPR"]) == "life_threatening"
    assert kb.max_severity(["CHEST_PAIN"]) == "urgent"
    assert kb.max_severity([]) is None


def test_universal_first_steps_call_crew_medical_officer(kb):
    s1, s2 = kb.universal_first_steps[:2]
    assert s1.startswith("S1. SCENE SAFETY") and "trigger" in s1
    assert "Crew Medical Officer" in s2 and "CMO" not in s2


def test_display_strips_only_biomarker_markers():
    raw = "1. LOCATE SOURCE: Inspect skin wounds/rash (#12), urine strip (#5), and blood CBC/CRP (#1, #3)."
    assert display_step(raw) == "1. LOCATE SOURCE: Inspect skin wounds/rash, urine strip, and blood CBC/CRP."
    keep = "5. NITROGLYCERIN: If Systolic BP > 100 mmHg, give Nitroglycerin 0.4 mg (max 3 doses)."
    assert display_step(keep) == keep


def test_steps_are_verbatim_apart_from_markers(kb):
    for p in kb.protocols.values():
        for raw, shown in zip(p.steps, p.display_steps):
            assert shown.replace(" ", "") in raw.replace(" ", "") or "(#" in raw


def test_no_user_facing_text_says_cmo(kb):
    texts = list(kb.universal_first_steps) + [c.instruction for c in kb.checks.values()]
    assert not any("CMO" in t for t in texts)


# ---------- GCS ----------
def test_gcs_reporting_and_nt():
    r = parse_reading({"eye": 3, "verbal": 4, "motor": 5}, T0)
    assert r.components == "E3 V4 M5" and r.total == 12
    nt = parse_reading({"eye": 3, "verbal": "NT", "motor": 5}, T0)
    assert nt.components == "E3 VNT M5" and nt.total is None


@pytest.mark.parametrize("bad", [{"eye": 5, "verbal": 4, "motor": 5}, {"eye": 0, "verbal": 4, "motor": 5},
                                 {"eye": 3, "verbal": 4}, "E3V4M5", {"eye": True, "verbal": 4, "motor": 5}])
def test_gcs_rejects_out_of_range(bad):
    with pytest.raises(GcsError):
        parse_reading(bad, T0)


def _r(e, v, m, minutes):
    return parse_reading({"eye": e, "verbal": v, "motor": m}, T0 + timedelta(minutes=minutes))


def test_gcs_alert_eye_or_verbal_drop_3():
    a = check_trend([_r(4, 5, 6, 0), _r(4, 2, 6, 5)])
    assert a and a.rule == "drop_eye_or_verbal_ge_3"
    assert "E4 V5 M6 → E4 V2 M6" in a.message and "Crew Medical Officer" in a.message


def test_gcs_alert_motor_drop_2():
    a = check_trend([_r(4, 5, 6, 0), _r(4, 5, 4, 5)])
    assert a and a.rule == "drop_motor_ge_2"


def test_gcs_one_point_drop_needs_30_minutes():
    assert check_trend([_r(4, 5, 6, 0), _r(4, 4, 6, 5), _r(4, 4, 6, 20)]) is None
    a = check_trend([_r(4, 5, 6, 0), _r(4, 4, 6, 5), _r(4, 4, 6, 36)])
    assert a and a.rule == "sustained_drop_1_ge_30min"


def test_gcs_recovered_drop_is_not_sustained():
    assert check_trend([_r(4, 5, 6, 0), _r(4, 4, 6, 5), _r(4, 5, 6, 20), _r(4, 4, 6, 40)]) is None


def test_gcs_ignores_nt_components():
    a = parse_reading({"eye": 4, "verbal": 5, "motor": 6}, T0)
    b = parse_reading({"eye": 4, "verbal": "NT", "motor": 6}, T0 + timedelta(minutes=60))
    assert check_trend([a, b]) is None


# ---------- Checks ----------
def _turn(answers, minutes=0, role="responder"):
    return SimpleNamespace(role=role, timestamp=T0 + timedelta(minutes=minutes), check_answers=answers)


def test_implausible_number_becomes_warning(kb):
    st = chk.collect_answers(kb, [_turn({"PULSE_COUNT": 400, "BREATH_COUNT": 18})])
    assert "PULSE_COUNT" not in st.latest and st.latest["BREATH_COUNT"] == 18
    assert st.warnings[0]["check_id"] == "PULSE_COUNT"


def test_unknown_check_and_bad_option_warn(kb):
    st = chk.collect_answers(kb, [_turn({"BLOOD_SUGAR": 140, "NECK_VEINS": "purple"})])
    assert {w["check_id"] for w in st.warnings} == {"BLOOD_SUGAR", "NECK_VEINS"}


def test_fast_path_cpr_and_choking(kb):
    assert chk.fast_path(kb, {"RESPONSIVENESS": "no_response", "NORMAL_BREATHING": "abnormal_or_gasping"})[0] == "CPR"
    assert chk.fast_path(kb, {"SPEAK_OR_COUGH": "cannot_speak_or_cough"})[0] == "CHOKING"
    # an unresponsive Patient who cannot speak is not a choking fast path
    assert chk.fast_path(kb, {"SPEAK_OR_COUGH": "cannot_speak_or_cough", "RESPONSIVENESS": "no_response",
                              "NORMAL_BREATHING": "normal"}) is None
    assert chk.fast_path(kb, {"RESPONSIVENESS": "no_response", "NORMAL_BREATHING": "normal"}) is None


def test_needs_gcs_and_chest_pain_rule(kb):
    assert chk.needs_gcs({"RESPONSIVENESS": "responds_to_voice"})
    assert not chk.needs_gcs({"RESPONSIVENESS": "alert_and_talking"})
    assert chk.missing_chest_pain_checks(kb, {"NECK_VEINS": "bulging"}) == ["BREATHING_DIFFICULTY"]
    assert chk.chest_pain_present({"CHEST_PAIN": "yes"}, False)
