"""
Health data routes, for the UI and for data that doesn't come from a model.

    GET  /api/measurements   readings over time, filtered for a trend chart
    POST /api/measurements   add one value by hand (e.g. a lab result)
"""

from datetime import datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app import db

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
    prediction_id: int | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(1000, ge=1, le=10000),
):
    return db.list_measurements(
        astronaut_id=astronaut_id,
        source=source,
        metric=metric,
        prediction_id=prediction_id,
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
