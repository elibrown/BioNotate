"""Polling API: derive alerts from the latest stored observations."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.dashboard.repository import CrewRepository, get_repository

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard")
def dashboard(repository: CrewRepository = Depends(get_repository)):
    now = datetime.now(timezone.utc)
    crew, alerts = [], []
    members = repository.list_crew()
    evaluation_time = getattr(repository, "evaluation_time", None) or now
    for member in members:
        stale = (evaluation_time - member.observed_at).total_seconds() > getattr(repository, "stale_after_seconds", 300)
        member_alerts = []
        for metric in member.metrics:
            if metric.value is not None and not metric.lower <= metric.value <= metric.upper:
                member_alerts.append({
                    "id": f"{member.id}:{metric.key}:{member.observed_at.isoformat()}",
                    "crew_id": member.id, "crew_name": member.name,
                    "metric": metric.key,
                    "message": f"{metric.label}: {metric.value:g} {metric.unit} outside configured range {metric.lower:g}–{metric.upper:g} {metric.unit}",
                    "observed_at": member.observed_at,
                })
        for prediction in member.predictions:
            if prediction.score >= prediction.threshold:
                member_alerts.append({
                    "id": f"{member.id}:prediction:{prediction.id}",
                    "crew_id": member.id, "crew_name": member.name,
                    "metric": prediction.target,
                    "message": f"{prediction.label}: {prediction.score:.0%} meets configured alert threshold {prediction.threshold:.0%}",
                    "observed_at": prediction.observed_at,
                })
            stale = stale or (evaluation_time - prediction.observed_at).total_seconds() > getattr(repository, "stale_after_seconds", 300)
        alerts.extend(member_alerts)
        missing = not member.metrics or any(m.value is None for m in member.metrics)
        crew.append({**member.model_dump(), "stale": stale,
                     "status": "alert" if member_alerts else "unknown" if stale or missing else "normal"})
    return {"mode": "demo", "generated_at": now, "demo_as_of": evaluation_time, "crew": crew, "alerts": alerts}
