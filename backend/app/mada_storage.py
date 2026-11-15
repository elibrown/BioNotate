"""Patient-linked MADA sessions and descriptive histories in the existing SQLite DB.

A session retains text/check turns and model responses so the stateless MADA
service can be called again. Binary media is NEVER persisted here. In a real
medical deployment, protect these endpoints and encrypt/retain data by policy.
"""
from __future__ import annotations

import json
import math
import sqlite3
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from statistics import median

from app import db


def patient_context(patient_id: str, max_metrics: int = 12) -> dict:
    """Bounded, factual DB context for MADA: values + provenance, not diagnosis.

    Only the authoritative patient ID is accepted; never use responder identity
    to select measurements. No names, full time series, or free-form reports
    are forwarded to the model. Trends are numeric descriptions only.
    """
    if get_patient(patient_id) is None:
        raise ValueError("Patient must be present in the crew roster.")
    candidates = patient_trends(patient_id)["metrics"]
    # Take a small number of the most recently observed source/metric combinations.
    candidates.sort(key=lambda m: m["latest"]["measured_at"], reverse=True)
    measurements = []
    for m in candidates:
        latest = m["latest"]
        try:
            value = float(latest["value"])
            delta = float(m["delta"]) if m["delta"] is not None else None
        except (TypeError, ValueError):
            continue
        if not math.isfinite(value) or (delta is not None and not math.isfinite(delta)):
            continue
        measurements.append({
            "source": str(m["source"])[:64],
            "metric": str(m["metric"])[:64],
            "unit": str(m["unit"] or "")[:32],
            "latest_value": value,
            "latest_measured_at": latest["measured_at"],
            "observation_count": m["observations"],
            "delta_from_first": delta,
            "first_measured_at": m["first"]["measured_at"],
        })
        if len(measurements) >= max_metrics:
            break
    return {
        "patient_id": patient_id,
        "retrieved_at": db.to_iso(datetime.now(timezone.utc)),
        "measurements": measurements,
    }


def list_registered_patients() -> list[dict]:
    """Return only registered crew, not unknown IDs seen in uploaded readings."""
    conn = db._connect()
    try:
        return [dict(r) for r in conn.execute(
            "SELECT id, name, role FROM astronauts ORDER BY id"
        )]
    finally:
        conn.close()


def get_patient(patient_id: str) -> dict | None:
    """Only registered patients/crew members are valid; no silent creation."""
    conn = db._connect()
    try:
        row = conn.execute(
            "SELECT id, name, role FROM astronauts WHERE id = ?", (patient_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_assessment(assessment_id: str) -> dict | None:
    conn = db._connect()
    try:
        row = conn.execute(
            "SELECT * FROM mada_assessments WHERE id = ?", (assessment_id,)
        ).fetchone()
        return _assessment_row(row) if row else None
    finally:
        conn.close()


def _assessment_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "patient_id": row["patient_id"],
        "responder_id": row["responder_id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "action": row["action"],
        "turns": json.loads(row["turns_json"]),
        "latest_response": json.loads(row["latest_response_json"]),
    }


def save_assessment(
    *, patient_id: str, responder_id: str | None, turns: list[dict],
    response: dict, previous: dict | None = None,
) -> dict:
    """Create/advance one patient's assessment using optimistic concurrency.

    If a second browser tab submitted from the same previous turn, reject that
    stale write rather than losing an answer or mixing conversations.
    """
    now = db.to_iso(datetime.now(timezone.utc))
    action = str(response["action"])
    turns_json = json.dumps(turns, ensure_ascii=False)
    response_json = json.dumps(response, ensure_ascii=False)
    conn = db._connect()
    try:
        with conn:
            if previous is None:
                assessment_id = uuid.uuid4().hex
                conn.execute(
                    """INSERT INTO mada_assessments
                       (id, patient_id, responder_id, created_at, updated_at, action,
                        turns_json, latest_response_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (assessment_id, patient_id, responder_id, now, now, action,
                     turns_json, response_json),
                )
            else:
                assessment_id = previous["id"]
                previous_json = json.dumps(previous["turns"], ensure_ascii=False)
                cur = conn.execute(
                    """UPDATE mada_assessments SET updated_at = ?, action = ?,
                        turns_json = ?, latest_response_json = ?
                        WHERE id = ? AND patient_id = ? AND turns_json = ?""",
                    (now, action, turns_json, response_json, assessment_id,
                     patient_id, previous_json),
                )
                if cur.rowcount != 1:
                    raise ValueError("Assessment was updated elsewhere. Reload before continuing.")
    finally:
        conn.close()
    return get_assessment(assessment_id)


def list_assessments(patient_id: str, limit: int = 25) -> list[dict]:
    conn = db._connect()
    try:
        rows = conn.execute(
            """SELECT id, patient_id, responder_id, created_at, updated_at,
                      action, latest_response_json
               FROM mada_assessments WHERE patient_id = ?
               ORDER BY updated_at DESC, id DESC LIMIT ?""",
            (patient_id, limit),
        ).fetchall()
        return [
            {"id": r["id"], "patient_id": r["patient_id"],
             "responder_id": r["responder_id"], "created_at": r["created_at"],
             "updated_at": r["updated_at"], "action": r["action"],
             "latest_response": json.loads(r["latest_response_json"])}
            for r in rows
        ]
    finally:
        conn.close()


def patient_trends(patient_id: str) -> dict:
    """Describe observed changes, not infer diagnosis or whether a change is good.

    Multiple points within one video/voice prediction are collapsed to their
    median; otherwise a 30-second clip could misleadingly count as 30 sessions.
    Manual readings count individually. Sources and units are never mixed.
    """
    readings = db.list_measurements(astronaut_id=patient_id, limit=10000)
    grouped: dict[tuple, list[dict]] = defaultdict(list)
    for row in readings:
        # A numeric prediction ID may be absent for manual measurements.
        event_id = ("prediction", row["prediction_id"]) if row["prediction_id"] is not None \
            else ("reading", row["id"])
        grouped[(row["source"], row["metric"], row["unit"], event_id)].append(row)

    events: dict[tuple, list[dict]] = defaultdict(list)
    for (source, metric, unit, _event), rows in grouped.items():
        events[(source, metric, unit)].append({
            "measured_at": max(r["measured_at"] for r in rows),
            "value": round(float(median(r["value"] for r in rows)), 4),
            "reading_count": len(rows),
        })

    metrics = []
    for (source, metric, unit), samples in sorted(events.items()):
        samples.sort(key=lambda r: r["measured_at"])
        samples = samples[-30:]
        first, last = samples[0], samples[-1]
        change = round(last["value"] - first["value"], 4) if len(samples) > 1 else None
        direction = "insufficient_data" if change is None else (
            "stable" if abs(change) < 1e-8 else "increasing" if change > 0 else "decreasing"
        )
        metrics.append({
            "source": source, "metric": metric, "unit": unit,
            "observations": len(samples), "first": first, "latest": last,
            "delta": change, "direction": direction,
            "points": samples,
            "summary": (
                f"{metric}: only one independent observation ({last['value']} {unit or ''})."
                if change is None else
                f"{metric} ({source}): {first['value']} to {last['value']} {unit or ''} "
                f"across {len(samples)} observations; {direction} by {abs(change)}."
            ),
        })
    return {
        "patient_id": patient_id,
        "metrics": metrics,
        "summary": (
            "No recorded measurements for this patient." if not metrics else
            "Descriptive changes only; not a diagnosis. Each model run counts as one observation."
        ),
    }
