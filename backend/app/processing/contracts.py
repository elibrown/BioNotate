"""Transport-independent input and prediction envelopes."""
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping, Protocol


class Modality(str, Enum):
    VIDEO = "video"
    AUDIO = "audio"
    METRICS = "metrics"


@dataclass(frozen=True)
class InputData:
    request_id: str
    modality: Modality
    source: Path | Mapping[str, float]
    astronaut_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.request_id, str) or not self.request_id.strip():
            raise ValueError("request_id must be a nonempty string")
        object.__setattr__(self, "modality", Modality(self.modality))


@dataclass(frozen=True)
class PredictionRequest:
    request_id: str
    modality: Modality
    payload: dict
    astronaut_id: str | None = None

    def to_dict(self) -> dict:
        """Build an envelope suitable for a future prediction client."""
        return {
            "request_id": self.request_id,
            "modality": self.modality.value,
            "astronaut_id": self.astronaut_id,
            "payload": self.payload,
        }


class Processor(Protocol):
    def process(self, data: InputData) -> PredictionRequest:
        """Validate and transform input; do not run inference or send HTTP."""
        ...
