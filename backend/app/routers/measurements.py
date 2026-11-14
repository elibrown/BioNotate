"""
Health data routes, for the UI and for data that doesn't come from a model.

    GET  /api/biomarkers     the kinds of data we track (BM01 ... BM12, ...)
    POST /api/biomarkers     add a new kind of data
    GET  /api/measurements   values over time, filtered for a trend chart
    POST /api/measurements   add one value by hand (e.g. a lab result)
"""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app import db

router = APIRouter(prefix="/api", tags=["measurements"])


class NewBiomarker(BaseModel):
    code: str                       # e.g. BM13_Body_Mass
    name: str
    description: str | None = None


class NewMeasurement(BaseModel):
    astronaut_id: str
    biomarker: str                  # must be a known biomarker code
    metric: str                     # e.g. glucose_mg_dl
    value: float
    unit: str | None = None
    measured_at: datetime | None = None   # defaults to now


def _to_utc_iso(value: datetime) -> str:
    if value.tzinfo is None:            # no timezone given: assume UTC
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


@router.get("/biomarkers")
def list_biomarkers():
    return db.list_biomarkers()


@router.post("/biomarkers")
def add_biomarker(body: NewBiomarker):
    return db.add_biomarker(body.code, body.name, body.description)


@router.get("/measurements")
def list_measurements(
    astronaut_id: str | None = None,
    biomarker: str | None = None,
    metric: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(1000, ge=1, le=10000),
):
    return db.list_measurements(
        astronaut_id=astronaut_id,
        biomarker=biomarker,
        metric=metric,
        since=_to_utc_iso(since) if since else None,
        until=_to_utc_iso(until) if until else None,
        limit=limit,
    )


@router.post("/measurements")
def add_measurement(body: NewMeasurement):
    if not db.biomarker_exists(body.biomarker):
        raise HTTPException(
            status_code=400,
            detail=f"Unknown biomarker '{body.biomarker}'. See GET /api/biomarkers.",
        )
    return db.add_measurement(
        astronaut_id=body.astronaut_id,
        biomarker=body.biomarker,
        metric=body.metric,
        value=body.value,
        unit=body.unit,
        measured_at=_to_utc_iso(body.measured_at) if body.measured_at else None,
    )
