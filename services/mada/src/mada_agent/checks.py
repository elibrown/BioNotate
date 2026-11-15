"""Check answers: validation, deterministic fast-path rules and the chest-pain rule."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .gcs import GcsError, GcsReading, parse_reading
from .knowledge import KnowledgeBase


@dataclass
class AnswerState:
    """All Check answers in a conversation, after validation."""

    latest: dict[str, Any] = field(default_factory=dict)  # check id -> latest valid value
    gcs_readings: list[GcsReading] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)  # invalid answers to re-measure

    @property
    def answered(self) -> set[str]:
        return set(self.latest)


def _validate_value(kb: KnowledgeBase, check_id: str, value: Any) -> Any:
    check = kb.checks[check_id]
    a = check.answer
    t = a["type"]
    if t == "choice":
        if value not in a["options"]:
            raise ValueError(f"must be one of {a['options']}")
        return value
    if t == "multi_choice":
        vals = value if isinstance(value, list) else [value]
        bad = [v for v in vals if v not in a["options"]]
        if bad or not vals:
            raise ValueError(f"values must be from {a['options']}")
        return vals
    if t == "number":
        if isinstance(value, dict):  # e.g. PAIN: {"score": 7, "text": "left flank"}
            num, extra = value.get("value", value.get("score")), value
        else:
            num, extra = value, None
        if isinstance(num, bool) or not isinstance(num, (int, float)):
            raise ValueError("must be a number")
        lo, hi = a["plausible"]
        if not lo <= num <= hi:
            raise ValueError(f"{num} {a.get('unit', '')} is not physically plausible "
                             f"(expected {lo}-{hi}); please measure again")
        return extra if extra is not None else num
    if t == "audio":
        return value  # the recording itself arrives as the request's audio file
    raise ValueError(f"unsupported answer type {t}")


def collect_answers(kb: KnowledgeBase, turns: list[Any]) -> AnswerState:
    """Validate every Check answer in the Responder's turns (later answers override earlier ones)."""
    state = AnswerState()
    for turn in turns:
        if turn.role != "responder":
            continue
        ts: datetime = turn.timestamp
        for check_id, value in (turn.check_answers or {}).items():
            if check_id not in kb.checks:
                state.warnings.append({"check_id": check_id, "problem": "unknown Check; ignored"})
                continue
            if check_id == "GCS":
                try:
                    reading = parse_reading(value, ts)
                except GcsError as exc:
                    state.warnings.append({"check_id": check_id, "problem": str(exc)})
                    continue
                state.gcs_readings.append(reading)
                state.latest[check_id] = reading.as_dict()
                continue
            try:
                state.latest[check_id] = _validate_value(kb, check_id, value)
            except ValueError as exc:
                state.latest.pop(check_id, None)
                state.warnings.append({"check_id": check_id, "problem": str(exc)})
    return state


def _matches(answers: dict[str, Any], cond: dict[str, list[str]]) -> bool:
    for cid, allowed in cond.items():
        v = answers.get(cid)
        vals = v if isinstance(v, list) else [v]
        if not any(x in allowed for x in vals):
            return False
    return True


def fast_path(kb: KnowledgeBase, answers: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    """Return (protocol_id, rule) if a deterministic fast-path rule fires on the Check answers."""
    for rule in kb.fast_path_rules:
        if _matches(answers, rule["when"]) and not (rule.get("unless") and _matches(answers, rule["unless"])):
            return rule["protocol"], rule
    return None


def needs_gcs(answers: dict[str, Any]) -> bool:
    """Unresponsive-but-breathing (or not clearly alert) Patient with no GCS yet -> ask GCS."""
    resp = answers.get("RESPONSIVENESS")
    return resp in {"responds_to_voice", "responds_only_to_touch", "no_response"} and "GCS" not in answers


def chest_pain_present(answers: dict[str, Any], model_flag: bool) -> bool:
    return model_flag or answers.get("CHEST_PAIN") == "yes"


def missing_chest_pain_checks(kb: KnowledgeBase, answers: dict[str, Any]) -> list[str]:
    return [c for c in kb.chest_pain_required_checks if c not in answers]
