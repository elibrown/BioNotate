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
        if prediction.threshold is None or prediction.score < prediction.threshold:
            continue
        alerts.append({
            "id": f"{member.id}:prediction:{prediction.id}",
            "crew_id": member.id,
            "crew_name": member.name,
            "metric": prediction.target,
            "message": (
                f"{prediction.label}: {prediction.score:g} {prediction.unit} meets "
                f"configured alert threshold {prediction.threshold:g} {prediction.unit}"
                if prediction.unit else
                f"{prediction.label}: {prediction.score:.0%} meets configured "
                f"alert threshold {prediction.threshold:.0%}"
            ),
            "observed_at": prediction.observed_at,
        })
    return alerts


def combined_alerts(member: CrewMember, combined_rules: dict) -> list[dict]:
    """
    Rules that look at several values at once, possibly from different
    models (rules.json "combined"). A rule fires when ALL its conditions
    hold. A condition names a metric key or a prediction target, plus
    "above" and/or "below" (strict). A missing value never matches.
    """
    latest = {m.key: m.value for m in member.metrics}
    latest.update({p.target: p.score for p in member.predictions})

    def holds(condition: dict) -> bool:
        value = latest.get(condition["key"])
        if value is None:
            return False
        if "above" in condition and not value > condition["above"]:
            return False
        if "below" in condition and not value < condition["below"]:
            return False
        return True

    alerts = []
    for key, rule in combined_rules.items():
        if not rule["all"] or not all(holds(c) for c in rule["all"]):
            continue
        values = ", ".join(f"{c['key']} {latest[c['key']]:g}" for c in rule["all"])
        alerts.append({
            "id": f"{member.id}:combined:{key}",
            "crew_id": member.id,
            "crew_name": member.name,
            "metric": key,
            "message": f"{rule['label']}: {values}",
            "observed_at": member.observed_at,
        })
    return alerts


def rising_alerts(member: CrewMember, rising_rules: dict) -> list[dict]:
    """
    Trend rules (rules.json "rising"): alert when the last `checks` values
    of a prediction each went UP compared with the one before, e.g.
    checks = 4 means c1 < c2 < c3 < c4. No fixed numbers involved.
    """
    by_target = {p.target: p for p in member.predictions}
    alerts = []
    for key, rule in rising_rules.items():
        prediction = by_target.get(rule["key"])
        if prediction is None:
            continue
        last = prediction.history[-rule["checks"]:]
        if len(last) < rule["checks"] or not all(a < b for a, b in zip(last, last[1:])):
            continue
        alerts.append({
            "id": f"{member.id}:rising:{key}:{prediction.id}",
            "crew_id": member.id,
            "crew_name": member.name,
            "metric": key,
            "message": f"{rule['label']}: last {rule['checks']} checks "
                       + " → ".join(f"{v:g}" for v in last),
            "observed_at": prediction.observed_at,
        })
    return alerts


def is_stale(member: CrewMember, evaluation_time: datetime, max_age: int) -> bool:
    """Treat a member as stale when any included observation is too old."""
    if member.simulated:
        return False  # Static samples are labeled examples, not live telemetry.
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
                    max_age: int, combined_rules: dict | None = None,
                    rising_rules: dict | None = None) -> tuple[dict, list[dict]]:
    """Combine alert rules, freshness, and status for one crew member."""
    alerts = (metric_alerts(member) + prediction_alerts(member)
              + combined_alerts(member, combined_rules or {})
              + rising_alerts(member, rising_rules or {}))
    stale = is_stale(member, evaluation_time, max_age)
    result = {**member.model_dump(), "stale": stale,
              "status": member_status(member, alerts, stale)}
    return result, alerts


def build_snapshot(repository: CrewRepository, now: datetime) -> dict:
    """Read the source and assemble the dashboard response."""
    members = repository.list_crew()
    evaluation_time = getattr(repository, "evaluation_time", None) or now
    max_age = getattr(repository, "stale_after_seconds", 300)
    combined_rules = getattr(repository, "combined_rules", {})
    rising_rules = getattr(repository, "rising_rules", {})
    crew, alerts = [], []
    for member in members:
        result, member_alerts = evaluate_member(member, evaluation_time, max_age,
                                                 combined_rules, rising_rules)
        crew.append(result)
        alerts.extend(member_alerts)
    return {"mode": getattr(repository, "mode", "demo"), "generated_at": now,
            "demo_as_of": evaluation_time,
            "crew": crew, "alerts": alerts}


@router.get("/dashboard")
def dashboard(repository: CrewRepository = Depends(get_repository)):
    return build_snapshot(repository, datetime.now(timezone.utc))
