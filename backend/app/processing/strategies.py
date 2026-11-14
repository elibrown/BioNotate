"""Modality-specific processing, independent of API routes and model code."""
import math
from collections.abc import Callable, Mapping
from pathlib import Path

from .contracts import InputData, Modality, PredictionRequest

MediaAdapter = Callable[[Path], dict]


def _envelope(data: InputData, payload: dict) -> PredictionRequest:
    return PredictionRequest(data.request_id, data.modality, payload, data.astronaut_id)


class _MediaProcessor:
    modality: Modality
    extensions: frozenset[str]

    def __init__(self, adapter: MediaAdapter | None = None):
        self.adapter = adapter

    def process(self, data: InputData) -> PredictionRequest:
        if data.modality != self.modality:
            raise ValueError(f"Expected {self.modality.value} input")
        if not isinstance(data.source, Path):
            raise ValueError("Media input must be a local pathlib.Path")
        if data.source.suffix.lower() not in self.extensions:
            raise ValueError(f"Unsupported {self.modality.value} extension")
        if not data.source.is_file():
            raise ValueError("Media input must reference an existing file")
        if data.source.stat().st_size == 0:
            raise ValueError("Media input must not be empty")
        if self.adapter is None:
            raise NotImplementedError(
                f"Configure a model-specific {self.modality.value} preprocessing adapter"
            )
        payload = self.adapter(data.source)
        if not isinstance(payload, dict):
            raise TypeError("Preprocessing adapter must return a payload dictionary")
        return _envelope(data, payload)


class VideoProcessor(_MediaProcessor):
    modality = Modality.VIDEO
    extensions = frozenset({".mp4", ".mov", ".avi", ".mkv", ".webm"})


class AudioProcessor(_MediaProcessor):
    modality = Modality.AUDIO
    extensions = frozenset({".wav", ".mp3", ".flac", ".ogg", ".m4a", ".webm"})


class MetricsProcessor:
    def process(self, data: InputData) -> PredictionRequest:
        if data.modality != Modality.METRICS:
            raise ValueError("Expected metrics input")
        if not isinstance(data.source, Mapping) or not data.source:
            raise ValueError("Metrics must be a nonempty mapping of names to numbers")
        values = {}
        for name, value in data.source.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError("Metric names must be nonempty strings")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"Metric {name} must be numeric")
            try:
                number = float(value)
            except OverflowError as exc:
                raise ValueError(f"Metric {name} must be finite") from exc
            if not math.isfinite(number):
                raise ValueError(f"Metric {name} must be finite")
            values[name] = number
        return _envelope(data, {"metrics": values})
