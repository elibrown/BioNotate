"""
Where the dashboard gets crew data from.

DatabaseCrewRepository (the default) reads the SQLite database (app/db.py):
the astronauts roster and the measurements saved from uploaded videos.
DemoCrewRepository reads the JSON demo files in data/. Set the environment
variable ASTROHEALTH_DASHBOARD=demo to use it instead.
"""

import json
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Protocol

from pydantic import BaseModel

from app import db
from app.measurement_catalog import FIELD_BY_KEY


EPOCH = datetime.fromtimestamp(0, timezone.utc)


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


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
    manual_measurements: list[dict] = []


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

    def metrics_for(self, astronaut_id, rows, rules):
        metrics, observed = [], []
        for key, rule in rules.items():
            history = sorted(
                [row for row in rows if row["astronaut_id"] == astronaut_id and row["key"] == key],
                key=lambda row: parse_time(row["observed_at"]),
            )
            if history:
                observed.append(parse_time(history[-1]["observed_at"]))
            metrics.append(Metric(
                key=key, **rule, value=history[-1]["value"] if history else None,
                history=[row["value"] for row in history if row["value"] is not None],
            ))
        return metrics, observed

    def predictions_for(self, astronaut_id, rows, rules):
        predictions = []
        for target, rule in rules.items():
            matches = [row for row in rows
                       if row["astronaut_id"] == astronaut_id and row["target"] == target]
            if matches:
                latest = max(matches, key=lambda row: parse_time(row["observed_at"]))
                predictions.append(Prediction(
                    **{key: value for key, value in latest.items() if key != "astronaut_id"}, **rule,
                ))
        return predictions

    def list_crew(self) -> list[CrewMember]:
        metrics, predictions, rules = self.read("metrics"), self.read("predictions"), self.read("rules")
        self.stale_after_seconds = rules["stale_after_seconds"]
        times = [parse_time(row["observed_at"]) for row in metrics + predictions]
        self.evaluation_time = max(times) if times else None
        members = []
        for astronaut in self.read("astronauts"):
            readings, observed = self.metrics_for(astronaut["id"], metrics, rules["metrics"])
            members.append(CrewMember(
                **astronaut, metrics=readings,
                predictions=self.predictions_for(astronaut["id"], predictions, rules["predictions"]),
                observed_at=min(observed) if observed else self.evaluation_time or EPOCH,
            ))
        return members


DATA_DIR = Path(__file__).resolve().parents[3] / "data"

# Dashboard metric key (in data/rules.json) -> where it is stored in the
# measurements table: (source, metric). Rule metrics with no entry here
# (e.g. "oxygen": no model measures it yet) are left off the dashboard.
DB_METRICS = {
    "heart_rate": ("cardioresp", "hr_bpm"),
}

# How many recent readings to send for the trend line.
HISTORY_LENGTH = 60


class DatabaseCrewRepository:
    """
    Crew from the `astronauts` table, metrics from the `measurements` table.
    Labels, units and ranges still come from data/rules.json.
    No evaluation_time: freshness is judged against the current time.
    """

    mode = "live"
    metric_sources = DB_METRICS

    def __init__(self, data_dir: Path | None = None):
        self.data_dir = data_dir or DATA_DIR
        self.stale_after_seconds = 300

    def load_rules(self):
        rules = json.loads((self.data_dir / "rules.json").read_text())
        self.stale_after_seconds = rules["stale_after_seconds"]
        return rules["metrics"]

    def load_roster(self):
        if db.roster_is_empty():
            db.add_astronauts(json.loads((self.data_dir / "astronauts.json").read_text()))
        return db.list_astronauts()

    def load_metrics(self, astronaut_id, rules):
        metrics, observed = [], []
        for key, rule in rules.items():
            if key not in self.metric_sources:
                continue
            source, metric = self.metric_sources[key]
            rows = db.list_measurements(
                astronaut_id=astronaut_id, source=source, metric=metric, limit=HISTORY_LENGTH,
            )
            if rows:
                observed.append(parse_time(rows[-1]["measured_at"]))
            metrics.append(Metric(key=key, **rule,
                                  value=rows[-1]["value"] if rows else None,
                                  history=[row["value"] for row in rows]))
        return metrics, observed

    def load_manual_measurements(self, astronaut_id):
        rows = db.list_measurements(astronaut_id=astronaut_id, source="manual", limit=10000)
        latest = {}
        for row in rows:
            definition = FIELD_BY_KEY.get(row["metric"], {})
            latest[row["metric"]] = {
                **row, "label": definition.get("label", row["metric"]),
                "group_id": definition.get("group_id"),
            }
        return list(latest.values())

    def build_member(self, astronaut, rules):
        metrics, observed = self.load_metrics(astronaut["id"], rules)
        return CrewMember(
            id=astronaut["id"], name=astronaut["name"],
            role=astronaut["role"] or "Not on roster",
            observed_at=min(observed) if observed else EPOCH,
            metrics=metrics, manual_measurements=self.load_manual_measurements(astronaut["id"]),
            predictions=[],  # cardioresp produces measurements, not risk scores
        )

    def list_crew(self) -> list[CrewMember]:
        rules = self.load_rules()
        return [self.build_member(astronaut, rules) for astronaut in self.load_roster()]


class SimulationDatabaseRepository(DatabaseCrewRepository):
    """Replay only explicitly seeded synthetic readings, using fixture time."""

    mode = "simulation"
    metric_sources = {"heart_rate": ("simulation", "heart_rate"),
                      "oxygen": ("simulation", "oxygen")}

    def list_crew(self) -> list[CrewMember]:
        members = super().list_crew()
        self.evaluation_time = max((member.observed_at for member in members), default=None)
        return members


def get_repository() -> CrewRepository:
    if os.environ.get("ASTROHEALTH_DASHBOARD") == "demo":
        return DemoCrewRepository()
    # Prefer real model readings as soon as they exist; never relabel them as simulation.
    if db.list_measurements(source="simulation", limit=1) and not db.list_measurements(source="cardioresp", limit=1):
        return SimulationDatabaseRepository()
    return DatabaseCrewRepository()
