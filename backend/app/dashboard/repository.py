"""
Where the dashboard gets crew data from.

DatabaseCrewRepository (the default) reads the SQLite database (app/db.py):
the astronauts roster and the measurements saved from uploaded videos.
Synthetic samples, if present, are read from the same database and labeled.
"""

import json
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
    simulated: bool = False
    manual_measurements: list[dict] = Field(default_factory=list)


class CrewRepository(Protocol):
    def list_crew(self) -> list[CrewMember]: ...


DATA_DIR = Path(__file__).resolve().parents[3] / "data"

# Dashboard metric key (in data/rules.json) -> where it is stored in the
# measurements table: (source, metric). Rule metrics with no entry here
# (e.g. "oxygen": no model measures it yet) are left off the dashboard.
DB_METRICS = {
    "heart_rate": ("cardioresp", "hr_bpm"),
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
        sample_rows = db.list_measurements(astronaut_id=astronaut_id, source="simulation", limit=10000)
        latest = {row["metric"]: {**row, "label": LABELS[row["metric"]], "simulated": True}
                  for row in sample_rows if row["metric"] in LABELS}
        for row in rows:
            latest[row["metric"]] = {**row, "label": LABELS.get(row["metric"], row["metric"])}
        return list(latest.values())

    def load_metrics(self, astronaut_id, rules):
        has_model = bool(db.list_measurements(astronaut_id=astronaut_id, source="cardioresp", limit=1))
        metrics, observed = [], []
        for key, rule in rules.items():
            if has_model and key not in DB_METRICS:
                continue
            source, metric = DB_METRICS[key] if has_model else ("simulation", key)
            rows = db.list_measurements(astronaut_id=astronaut_id, source=source,
                                        metric=metric, limit=HISTORY_LENGTH)
            if rows:
                observed.append(datetime.fromisoformat(rows[-1]["measured_at"]))
            # Keep a missing HR placeholder; omit other absent sample metrics.
            if not rows and key not in DB_METRICS:
                continue
            metrics.append(Metric(key=key, **rule,
                                  value=rows[-1]["value"] if rows else None,
                                  history=[row["value"] for row in rows]))
        return metrics, observed, bool(observed) and not has_model

    def list_crew(self) -> list[CrewMember]:
        rules = json.loads((self.data_dir / "rules.json").read_text())
        self.stale_after_seconds = rules["stale_after_seconds"]
        self.combined_rules = rules.get("combined", {})
        self.rising_rules = rules.get("rising", {})
        if db.roster_is_empty():
            db.add_astronauts(json.loads((self.data_dir / "astronauts.json").read_text()))
        members = []
        for astronaut in db.list_astronauts():
            metrics, observed, simulated = self.load_metrics(astronaut["id"], rules["metrics"])
            members.append(CrewMember(
                id=astronaut["id"], name=astronaut["name"],
                role=astronaut["role"] or "Not on roster",
                observed_at=min(observed) if observed else datetime.fromtimestamp(0, timezone.utc),
                metrics=metrics, simulated=simulated,
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
                                        metric=metric, limit=HISTORY_LENGTH)
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
    return DatabaseCrewRepository()
