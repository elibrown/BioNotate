"""
Prediction history and alert routes, for the UI.

    GET  /api/predictions                  newest predictions (all astronauts)
    GET  /api/predictions?astronaut_id=A1  one astronaut's history
    GET  /api/predictions/{id}             one prediction
    GET  /api/alerts                       alerts nobody has acknowledged yet
    POST /api/alerts/{id}/ack              mark an alert as seen
"""

from fastapi import APIRouter, HTTPException, Query

from app import db

router = APIRouter(prefix="/api", tags=["predictions"])


@router.get("/predictions")
def list_predictions(
    astronaut_id: str | None = None,
    limit: int = Query(50, ge=1, le=500),
):
    return db.list_predictions(astronaut_id=astronaut_id, limit=limit)


@router.get("/predictions/{prediction_id}")
def get_prediction(prediction_id: int):
    prediction = db.get_prediction(prediction_id)
    if prediction is None:
        raise HTTPException(status_code=404, detail="Prediction not found.")
    return prediction


@router.get("/alerts")
def list_alerts(
    astronaut_id: str | None = None,
    include_acknowledged: bool = False,
    limit: int = Query(50, ge=1, le=500),
):
    return db.list_alerts(
        astronaut_id=astronaut_id,
        include_acknowledged=include_acknowledged,
        limit=limit,
    )


@router.post("/alerts/{prediction_id}/ack")
def acknowledge_alert(prediction_id: int):
    prediction = db.get_prediction(prediction_id)
    if prediction is None:
        raise HTTPException(status_code=404, detail="Prediction not found.")
    if not prediction["is_alert"]:
        raise HTTPException(status_code=400, detail="This prediction is not an alert.")
    return db.acknowledge_alert(prediction_id)
