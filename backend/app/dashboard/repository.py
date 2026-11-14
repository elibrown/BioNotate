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

from app.measurement_catalog import FIELD_BY_KEY


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

    def __init__(self, data_dir: Path | None = None):
        self.data_dir = data_dir or DATA_DIR
        self.stale_after_seconds = 300

    def list_crew(self) -> list[CrewMember]:
        from app import db   # here, not at the top, to keep imports one-way

        rules = json.loads((self.data_dir / "rules.json").read_text())
        self.stale_after_seconds = rules["stale_after_seconds"]
        if db.roster_is_empty():
            # First run: fill the roster from the demo profiles.
            db.add_astronauts(json.loads((self.data_dir / "astronauts.json").read_text()))

        members = []
        for astronaut in db.list_astronauts():
            metrics, observed = [], []
            for key, rule in rules["metrics"].items():
                if key not in DB_METRICS:
                    continue
                source, metric = DB_METRICS[key]
                rows = db.list_measurements(astronaut_id=astronaut["id"], source=source,
                                            metric=metric, limit=HISTORY_LENGTH)
                if rows:
                    observed.append(datetime.fromisoformat(rows[-1]["measured_at"]))
                metrics.append(Metric(key=key, **rule,
                                      value=rows[-1]["value"] if rows else None,
                                      history=[r["value"] for r in rows]))
            manual_rows = db.list_measurements(astronaut_id=astronaut["id"], source="manual", limit=10000)
            latest_manual = {}
            for row in manual_rows:
                definition = FIELD_BY_KEY.get(row["metric"], {})
                latest_manual[row["metric"]] = {
                    **row,
                    "label": definition.get("label", row["metric"]),
                    "group_id": definition.get("group_id"),
                }
            members.append(CrewMember(
                id=astronaut["id"],
                name=astronaut["name"],
                role=astronaut["role"] or "Not on roster",
                # Oldest of the latest readings; no data at all = very old (stale).
                observed_at=min(observed) if observed else datetime.fromtimestamp(0, timezone.utc),
                metrics=metrics,
                manual_measurements=list(latest_manual.values()),
                # Risk-score predictions (rules.json "predictions") need a model
                # that outputs scores; cardioresp doesn't, so none yet.
                predictions=[],
            ))
        return members


def get_repository() -> CrewRepository:
    if os.environ.get("ASTROHEALTH_DASHBOARD") == "demo":
        return DemoCrewRepository()
    return DatabaseCrewRepository()
