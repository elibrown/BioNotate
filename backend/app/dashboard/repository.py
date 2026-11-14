"""Replace get_repository with a database adapter when persistence is ready."""

import json
from pathlib import Path
from datetime import datetime
from typing import Protocol

from pydantic import BaseModel


class Metric(BaseModel):
    key: str
    label: str
    value: float | None
    unit: str
    lower: float
    upper: float
    history: list[float]


class Prediction(BaseModel):
    id: str
    target: str
    label: str
    score: float
    threshold: float
    observed_at: datetime
    model_version: str


class CrewMember(BaseModel):
    id: str
    name: str
    role: str
    observed_at: datetime
    metrics: list[Metric]
    predictions: list[Prediction] = []


class CrewRepository(Protocol):
    def list_crew(self) -> list[CrewMember]: ...


class DemoCrewRepository:
    """Join JSON fixtures by astronaut ID, reloading them on every request."""

    def __init__(self, directory: Path | None = None):
        self.directory = directory or Path(__file__).resolve().parents[3] / "data"
        self.evaluation_time = None
        self.stale_after_seconds = 300

    def read(self, name):
        return json.loads((self.directory / f"{name}.json").read_text())

    def list_crew(self) -> list[CrewMember]:
        astronauts = self.read("astronauts")
        metrics = self.read("metrics")
        predictions = self.read("predictions")
        rules = self.read("rules")
        self.stale_after_seconds = rules["stale_after_seconds"]
        parse_time = lambda value: datetime.fromisoformat(value.replace("Z", "+00:00"))
        # Replay the fixed demo at its latest observation, rather than claiming live data.
        times = [parse_time(row["observed_at"]) for row in metrics + predictions]
        self.evaluation_time = max(times) if times else None
        members = []
        for astronaut in astronauts:
            readings = []
            observed = []
            for key, rule in rules["metrics"].items():
                history = sorted([row for row in metrics if row["astronaut_id"] == astronaut["id"] and row["key"] == key], key=lambda row: parse_time(row["observed_at"]))
                if history:
                    observed.append(parse_time(history[-1]["observed_at"]))
                readings.append(Metric(key=key, **rule,
                                       value=history[-1]["value"] if history else None,
                                       history=[row["value"] for row in history if row["value"] is not None]))
            results = []
            for target, rule in rules["predictions"].items():
                matches = [row for row in predictions if row["astronaut_id"] == astronaut["id"] and row["target"] == target]
                if matches:
                    latest = max(matches, key=lambda row: parse_time(row["observed_at"]))
                    results.append(Prediction(**{k: v for k, v in latest.items() if k != "astronaut_id"}, **rule))
            members.append(CrewMember(**astronaut, metrics=readings, predictions=results,
                                      observed_at=min(observed) if observed else self.evaluation_time or datetime.fromtimestamp(0).astimezone()))
        return members


# TODO(@itamar): Replace DemoCrewRepository here with the database-backed
# CrewRepository adapter for users, metrics, and predictions joined by astronaut ID.
# Implement list_crew() returning CrewMember objects with latest metrics/history
# and latest predictions. Use timezone-aware timestamps; omit evaluation_time
# (the demo replay clock) so live freshness uses the current UTC time.
def get_repository() -> CrewRepository:
    return DemoCrewRepository()
