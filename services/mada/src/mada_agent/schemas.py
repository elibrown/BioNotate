"""Request and response models for the HTTP API (see docs/INTEGRATION.md)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Turn(BaseModel):
    """One message in the Assessment. The web app sends every turn so far, oldest first."""

    role: Literal["responder", "agent"]
    timestamp: datetime = Field(description="ISO-8601 time the message was sent (timezone recommended)")
    text: str | None = Field(None, max_length=4000, description="What the Responder said or typed")
    check_answers: dict[str, Any] = Field(default_factory=dict,
                                          description="Responder turns: Check ID -> answer")
    asked_check_ids: list[str] = Field(default_factory=list,
                                       description="Agent turns: copy of next_checks[].id from the response")
    protocol_ids: list[str] = Field(default_factory=list,
                                    description="Agent turns: copy of protocols[].id from the response")

    @field_validator("timestamp")
    @classmethod
    def _aware(cls, v: datetime) -> datetime:
        from datetime import timezone
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


class RecordedMeasurement(BaseModel):
    """Factual historical reading; no model-generated clinical inference."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    source: str = Field(max_length=64)
    metric: str = Field(max_length=64)
    unit: str = Field(max_length=32)
    latest_value: float
    latest_measured_at: datetime
    observation_count: int = Field(ge=1, le=30)
    delta_from_first: float | None = None
    first_measured_at: datetime


class PatientContext(BaseModel):
    """Optional server-supplied patient observations, never user instructions."""

    model_config = ConfigDict(extra="forbid")
    patient_id: str = Field(min_length=1, max_length=64)
    responder_is_patient: bool | None = None
    retrieved_at: datetime
    measurements: list[RecordedMeasurement] = Field(default_factory=list, max_length=12)


class Conversation(BaseModel):
    turns: list[Turn] = Field(min_length=1, max_length=40)
    patient_context: PatientContext | None = None

    @field_validator("turns")
    @classmethod
    def _last_is_responder(cls, v: list[Turn]) -> list[Turn]:
        if v[-1].role != "responder":
            raise ValueError("the last turn must be from the responder")
        return v


class ProtocolOut(BaseModel):
    id: str
    title: str
    severity: Literal["urgent", "life_threatening"]
    steps: list[str] = Field(description="Verbatim from rules.md; '(#N)' markers removed")


class CheckOut(BaseModel):
    id: str
    title: str
    instruction: str
    status: Literal["SOURCED", "UNVALIDATED"]
    answer: dict[str, Any]


class GcsOut(BaseModel):
    latest: str | None = Field(None, description="e.g. 'E3 V4 M5'")
    total: int | None = Field(None, description="Only when no component is NT")
    history: list[dict[str, Any]] = Field(default_factory=list)


class AnalyzeResponse(BaseModel):
    prompt_version: str
    model_quant: str
    degraded: bool = Field(description="True if the model could not be used; protocols come from retrieval only")
    action: Literal["ask_checks", "finalize"]
    first_steps: list[str] = Field(description="Universal first steps: show these FIRST, always")
    severity: Literal["urgent", "life_threatening"] | None
    protocols: list[ProtocolOut]
    no_protocol_match: bool = False
    message: str | None = None
    next_checks: list[CheckOut]
    gcs: GcsOut
    gcs_alert: dict[str, Any] | None = None
    answer_warnings: list[dict[str, str]] = Field(default_factory=list)
    observed_features: list[str] = Field(default_factory=list,
                                         description="What the model read from text/image/audio; UNCONFIRMED")
    rationale: str | None = Field(None, description="Model reasoning, for the Crew Medical Officer")
    decided_by: Literal["model", "fast_path_rule", "retrieval_only"]
    round: int = Field(description="Number of Check rounds completed before this response")
    disclaimer: str
