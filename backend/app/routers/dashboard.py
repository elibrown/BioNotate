"""Polling API: derive alerts from the latest stored observations."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.dashboard.repository import CrewMember, CrewRepository, get_repository

router = APIRouter(prefix="/api", tags=["dashboard"])


def metric_alerts(member: CrewMember) -> list[dict]:
    """Check latest metric values against inclusive configured ranges."""
    alerts = []
    for metric in member.metrics:
        if metric.value is None or metric.lower <= metric.value <= metric.upper:
            continue
        alerts.append({
            "id": f"{member.id}:{metric.key}:{member.observed_at.isoformat()}",
            "crew_id": member.id,
            "crew_name": member.name,
            "metric": metric.key,
            "message": (
                f"{metric.label}: {metric.value:g} {metric.unit} outside configured "
                f"range {metric.lower:g}–{metric.upper:g} {metric.unit}"
            ),
            "observed_at": member.observed_at,
        })
    return alerts


def prediction_alerts(member: CrewMember) -> list[dict]:
    """Check latest prediction scores against inclusive alert thresholds."""
    alerts = []
    for prediction in member.predictions:
        if prediction.score < prediction.threshold:
            continue
        alerts.append({
            "id": f"{member.id}:prediction:{prediction.id}",
            "crew_id": member.id,
            "crew_name": member.name,
            "metric": prediction.target,
            "message": (
                f"{prediction.label}: {prediction.score:.0%} meets configured "
                f"alert threshold {prediction.threshold:.0%}"
            ),
            "observed_at": prediction.observed_at,
        })
    return alerts


def is_stale(member: CrewMember, evaluation_time: datetime, max_age: int) -> bool:
    """Treat a member as stale when any included observation is too old."""
    timestamps = [member.observed_at, *(p.observed_at for p in member.predictions)]
    return any((evaluation_time - timestamp).total_seconds() > max_age
               for timestamp in timestamps)


def member_status(member: CrewMember, alerts: list[dict], stale: bool) -> str:
    """Alerts take priority over missing or stale data."""
    if alerts:
        return "alert"
    if stale or not member.metrics or any(m.value is None for m in member.metrics):
        return "unknown"
    return "normal"


def evaluate_member(member: CrewMember, evaluation_time: datetime,
                    max_age: int) -> tuple[dict, list[dict]]:
    """Combine alert rules, freshness, and status for one crew member."""
    alerts = metric_alerts(member) + prediction_alerts(member)
    stale = is_stale(member, evaluation_time, max_age)
    result = {**member.model_dump(), "stale": stale,
              "status": member_status(member, alerts, stale)}
    return result, alerts


def build_snapshot(repository: CrewRepository, now: datetime) -> dict:
    """Read the source and assemble the dashboard response."""
    members = repository.list_crew()
    evaluation_time = getattr(repository, "evaluation_time", None) or now
    max_age = getattr(repository, "stale_after_seconds", 300)
    crew, alerts = [], []
    for member in members:
        result, member_alerts = evaluate_member(member, evaluation_time, max_age)
        crew.append(result)
        alerts.extend(member_alerts)
    return {"mode": getattr(repository, "mode", "demo"), "generated_at": now,
            "demo_as_of": evaluation_time,
            "crew": crew, "alerts": alerts}


@router.get("/dashboard")
def dashboard(repository: CrewRepository = Depends(get_repository)):
    return build_snapshot(repository, datetime.now(timezone.utc))
