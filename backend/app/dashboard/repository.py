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

from pydantic import BaseModel, Field

from app import db
from app.manual_metrics import LABELS


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
    # None = no fixed alert level for this score (e.g. vocal_biomarker,
    # which alerts on a rising trend instead: rules.json "rising").
    threshold: float | None = None
    observed_at: datetime
    model_version: str
    # Set for scores that aren't 0-1 risks (e.g. "z-score"): the dashboard
    # then shows the raw value with this unit instead of a percentage.
    unit: str | None = None
    # Earlier scores, oldest first, ending with this one (for trend rules).
    history: list[float] = []


class CrewMember(BaseModel):
    id: str
    name: str
    role: str
    observed_at: datetime
    metrics: list[Metric]
    predictions: list[Prediction] = []
    manual_measurements: list[dict] = Field(default_factory=list)


class CrewRepository(Protocol):
    def list_crew(self) -> list[CrewMember]: ...


class DemoCrewRepository:
    """Join JSON fixtures by astronaut ID, reloading them on every request."""

    def __init__(self, directory: Path | None = None):
        self.directory = directory or Path(__file__).resolve().parents[3] / "data"
        self.evaluation_time = None
        self.stale_after_seconds = 300

    def read(self, name):
        return json.loads((self.directory / f"{name}.json").read_text(encoding='utf-8'))

    def list_crew(self) -> list[CrewMember]:
        astronauts = self.read("astronauts")
        metrics = self.read("metrics")
        predictions = self.read("predictions")
        rules = self.read("rules")
        self.stale_after_seconds = rules["stale_after_seconds"]
        self.combined_rules = rules.get("combined", {})
        self.rising_rules = rules.get("rising", {})
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
# measurements table: (optional source, metric). None selects any live source.
# Research mission-phase values never substitute for current vitals.
# Rule metrics with no entry here
# (e.g. "oxygen": no model measures it yet) are left off the dashboard.
DB_METRICS = {
    "heart_rate": (None, "hr_bpm"),
    "respiratory_rate": (None, "respi_rate"),
}

# Same idea for model scores shown under "Model predictions": key in
# rules.json "predictions" -> (source, metric) in the measurements table.
# The latest stored value is the score; recent values go in its history.
DB_PREDICTIONS = {
    "vocal_biomarker": ("voicebiomarker", "vocal_biomarker"),
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

    def load_manual_measurements(self, astronaut_id):
        rows = db.list_measurements(astronaut_id=astronaut_id, source="manual", limit=10000)
        latest = {}
        for row in rows:
            latest[row["metric"]] = {**row, "label": LABELS.get(row["metric"], row["metric"])}
        return list(latest.values())

    def list_crew(self) -> list[CrewMember]:
        rules = json.loads((self.data_dir / "rules.json").read_text(encoding='utf-8'))
        self.stale_after_seconds = rules["stale_after_seconds"]
        self.combined_rules = rules.get("combined", {})
        self.rising_rules = rules.get("rising", {})
        if db.roster_is_empty():
            # First run: fill the roster from the demo profiles.
            db.add_astronauts(json.loads((self.data_dir / "astronauts.json").read_text(encoding='utf-8')))

        members = []
        for astronaut in db.list_astronauts():
            metrics, observed = [], []
            for key, rule in rules["metrics"].items():
                if key not in DB_METRICS:
                    continue
                source, metric = DB_METRICS[key]
                rows = db.list_measurements(astronaut_id=astronaut["id"], source=source,
                                            metric=metric, context="live", limit=HISTORY_LENGTH)
                if rows:
                    observed.append(datetime.fromisoformat(rows[-1]["measured_at"]))
                metrics.append(Metric(key=key, **rule,
                                      value=rows[-1]["value"] if rows else None,
                                      history=[r["value"] for r in rows]))
            members.append(CrewMember(
                id=astronaut["id"],
                name=astronaut["name"],
                role=astronaut["role"] or "Not on roster",
                # Oldest of the latest readings; no data at all = very old (stale).
                observed_at=min(observed) if observed else datetime.fromtimestamp(0, timezone.utc),
                metrics=metrics,
                manual_measurements=self.load_manual_measurements(astronaut["id"]),
                predictions=self._predictions(db, astronaut["id"], rules["predictions"]),
            ))
        return members

    @staticmethod
    def _predictions(db, astronaut_id: str, rules: dict) -> list[Prediction]:
        """Latest stored score (plus recent history) for each rules.json prediction."""
        results = []
        for key, rule in rules.items():
            if key not in DB_PREDICTIONS:
                continue
            source, metric = DB_PREDICTIONS[key]
            rows = db.list_measurements(astronaut_id=astronaut_id, source=source,
                                        metric=metric, context="live", limit=HISTORY_LENGTH)
            if not rows:
                continue
            latest = rows[-1]
            run = db.get_prediction(latest["prediction_id"]) if latest["prediction_id"] else None
            results.append(Prediction(
                id=str(latest["prediction_id"] or latest["id"]),
                target=key,
                score=latest["value"],
                observed_at=datetime.fromisoformat(latest["measured_at"]),
                model_version=(run or {}).get("model_version") or source,
                history=[r["value"] for r in rows],
                **rule,
            ))
        return results


def get_repository() -> CrewRepository:
    if os.environ.get("ASTROHEALTH_DASHBOARD") == "demo":
        return DemoCrewRepository()
    return DatabaseCrewRepository()
