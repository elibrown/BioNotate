"""
Health data routes, for the UI and for data that doesn't come from a model.

    GET  /api/measurements   readings over time, filtered for a trend chart
    POST /api/measurements   add one value by hand (e.g. a lab result)
"""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat

from app import db
from app.data import trends
from app.manual_metrics import METRICS, METRIC_BY_KEY

router = APIRouter(prefix="/api", tags=["measurements"])


class NewMeasurement(BaseModel):
    astronaut_id: str
    metric: str                     # e.g. glucose_mg_dl
    value: float
    unit: str | None = None
    measured_at: datetime | None = None   # defaults to now
    source: str = "manual"          # where the value came from


@router.get("/measurements")
def list_measurements(
    astronaut_id: str | None = None,
    source: str | None = None,
    metric: str | None = None,
    context: Literal["live", "research"] | None = None,
    dataset_id: str | None = None,
    prediction_id: int | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(1000, ge=1, le=10000),
):
    return db.list_measurements(
        astronaut_id=astronaut_id,
        source=source,
        metric=metric,
        prediction_id=prediction_id, context=context, dataset_id=dataset_id,
        since=db.to_iso(since) if since else None,
        until=db.to_iso(until) if until else None,
        limit=limit,
    )


@router.post("/measurements")
def add_measurement(body: NewMeasurement):
    return db.add_measurement(
        astronaut_id=body.astronaut_id,
        metric=body.metric,
        value=body.value,
        unit=body.unit,
        measured_at=db.to_iso(body.measured_at) if body.measured_at else None,
        source=body.source,
    )


class ManualMeasurement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    astronaut_id: str = Field(min_length=1, max_length=64, pattern=r".*\S.*")
    metric: str
    value: FiniteFloat
    measured_at: datetime


@router.get("/measurement-catalog")
def measurement_catalog():
    return {"metrics": METRICS}


@router.post("/manual-measurements", status_code=201)
def add_manual_measurement(body: ManualMeasurement):
    metric = METRIC_BY_KEY.get(body.metric)
    if metric is None:
        raise HTTPException(422, "Choose a supported metric.")
    if body.measured_at.tzinfo is None:
        raise HTTPException(422, "Measurement time must include a timezone.")
    if body.astronaut_id not in {row["id"] for row in db.list_astronauts()}:
        raise HTTPException(422, "Choose an astronaut from the crew roster.")
    return db.add_measurement(
        astronaut_id=body.astronaut_id, metric=body.metric, value=body.value,
        unit=metric["unit"], measured_at=db.to_iso(body.measured_at), source="manual",
    )


@router.get('/measurements/trends')
def measurement_trends(astronaut_id: str, metric: str | None = None,
                       source: str | None = None,
                       context: Literal['live', 'research'] | None = None,
                       dataset_id: str | None = None):
    return {'astronaut_id': astronaut_id, 'series': trends.measurement_trends(
        astronaut_id, metric=metric, source=source, context=context, dataset_id=dataset_id)}
