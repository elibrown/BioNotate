"""
Health data routes, for the UI and for data that doesn't come from a model.

    GET  /api/measurements   readings over time, filtered for a trend chart
    POST /api/measurements   add one value by hand (e.g. a lab result)
"""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, FiniteFloat

from app import db
from app.measurement_catalog import GROUPS, GROUP_BY_ID

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


# The catalogue fixes analyte keys/units; the generic legacy endpoint above
# remains available to existing integrations.


class ManualPanel(BaseModel):
    astronaut_id: str = Field(min_length=1, max_length=64, pattern=r".*\S.*")
    group_id: str
    values: dict[str, FiniteFloat] = Field(min_length=1, max_length=32)
    measured_at: datetime


@router.get("/measurement-catalog")
def measurement_catalog():
    return {"provisional": True, "groups": GROUPS}


@router.post("/manual-measurements", status_code=201)
def add_manual_panel(body: ManualPanel):
    panel = GROUP_BY_ID.get(body.group_id)
    if panel is None or not panel["fields"]:
        raise HTTPException(422, "This measurement group has no agreed numeric format yet.")
    fields = {item["key"]: item for item in panel["fields"]}
    if body.values.keys() - fields.keys():
        raise HTTPException(422, "Unknown analyte for this measurement group.")
    pressure_keys = {"systolic_bp", "diastolic_bp"}
    if body.values.keys() & pressure_keys and not pressure_keys <= body.values.keys():
        raise HTTPException(422, "Enter both systolic and diastolic blood pressure.")
    if body.measured_at.tzinfo is None:
        raise HTTPException(422, "Measurement time must include a timezone.")
    if body.astronaut_id not in {row["id"] for row in db.list_astronauts()}:
        raise HTTPException(422, "Choose an astronaut from the crew roster.")
    rows = [{"metric": key, "value": value, "unit": fields[key]["unit"]}
            for key, value in body.values.items()]
    return db.add_manual_measurements(body.astronaut_id, rows, db.to_iso(body.measured_at))
