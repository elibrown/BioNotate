"""
Prediction storage (SQLite).

Every model result is saved here so we can look at an astronaut's history
and show alerts in the UI.

- The database is ONE file: backend/astrohealth.db (git-ignored).
  Set the ASTROHEALTH_DB environment variable to use another path (tests do).
- We use Python's built-in sqlite3 module: no extra install, no ORM.
- The model output is stored as JSON text in `result_json`, so the real
  model can return any shape without changing the table.

The rest of the app only calls the functions below; no SQL anywhere else.
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]   # .../backend
DEFAULT_DB_PATH = BACKEND_DIR / "astrohealth.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS predictions (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    astronaut_id       TEXT,                 -- may be NULL (it's optional on upload)
    created_at         TEXT    NOT NULL,     -- UTC, ISO 8601, e.g. 2026-11-14T11:50:00+00:00
    video_file         TEXT,                 -- name of the file in backend/uploads/
    status             TEXT,                 -- copied from result["status"] if present
    is_alert           INTEGER NOT NULL DEFAULT 0,   -- 1 = needs attention
    alert_acknowledged INTEGER NOT NULL DEFAULT 0,   -- 1 = someone saw it in the UI
    result_json        TEXT    NOT NULL      -- the full model output, as JSON
);
CREATE INDEX IF NOT EXISTS idx_predictions_astronaut
    ON predictions (astronaut_id, created_at);
CREATE INDEX IF NOT EXISTS idx_predictions_alerts
    ON predictions (is_alert, alert_acknowledged);
"""


def _db_path() -> Path:
    return Path(os.environ.get("ASTROHEALTH_DB", DEFAULT_DB_PATH))


def _connect() -> sqlite3.Connection:
    # A new connection per call keeps things simple and thread-safe
    # (FastAPI runs normal `def` routes in a thread pool).
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row   # rows behave like dicts
    return conn


def init_db() -> None:
    """Create the table if it doesn't exist yet. Safe to call many times."""
    with _connect() as conn:
        conn.executescript(SCHEMA)
    conn.close()


def is_alert(result: dict) -> bool:
    """
    >>> THE ALERT RULE. Change this once the real model output is known. <<<

    Right now a prediction is an alert if the model says so explicitly
    ("alert": true), or if its "status" is anything other than "normal".
    """
    if "alert" in result:
        return bool(result["alert"])
    status = result.get("status")
    return status is not None and str(status).lower() != "normal"


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "astronaut_id": row["astronaut_id"],
        "created_at": row["created_at"],
        "video_file": row["video_file"],
        "status": row["status"],
        "is_alert": bool(row["is_alert"]),
        "alert_acknowledged": bool(row["alert_acknowledged"]),
        "result": json.loads(row["result_json"]),
    }


def save_prediction(
    result: dict,
    astronaut_id: str | None = None,
    video_file: str | None = None,
) -> dict:
    """Store one model result and return it as saved (with its new id)."""
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    status = result.get("status")
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO predictions
                (astronaut_id, created_at, video_file, status, is_alert, result_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                astronaut_id,
                created_at,
                video_file,
                None if status is None else str(status),
                int(is_alert(result)),
                json.dumps(result, default=str),
            ),
        )
        new_id = cur.lastrowid
    conn.close()
    return get_prediction(new_id)


def get_prediction(prediction_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM predictions WHERE id = ?", (prediction_id,)
        ).fetchone()
    conn.close()
    return _row_to_dict(row) if row else None


def list_predictions(astronaut_id: str | None = None, limit: int = 50) -> list[dict]:
    """Newest first. Pass astronaut_id to get one astronaut's history."""
    query = "SELECT * FROM predictions"
    params: list = []
    if astronaut_id is not None:
        query += " WHERE astronaut_id = ?"
        params.append(astronaut_id)
    query += " ORDER BY created_at DESC, id DESC LIMIT ?"
    params.append(limit)
    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def list_alerts(
    astronaut_id: str | None = None,
    include_acknowledged: bool = False,
    limit: int = 50,
) -> list[dict]:
    """Alerts, newest first. By default only the ones nobody has acknowledged."""
    query = "SELECT * FROM predictions WHERE is_alert = 1"
    params: list = []
    if not include_acknowledged:
        query += " AND alert_acknowledged = 0"
    if astronaut_id is not None:
        query += " AND astronaut_id = ?"
        params.append(astronaut_id)
    query += " ORDER BY created_at DESC, id DESC LIMIT ?"
    params.append(limit)
    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def acknowledge_alert(prediction_id: int) -> dict | None:
    """Mark an alert as seen. Returns the updated row, or None if no such id."""
    with _connect() as conn:
        conn.execute(
            "UPDATE predictions SET alert_acknowledged = 1 WHERE id = ?",
            (prediction_id,),
        )
    conn.close()
    return get_prediction(prediction_id)
