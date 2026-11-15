"""
Storage (SQLite): predictions and measurements.

Three tables:

  astronauts    The crew roster: id, name, role. Filled from
                data/astronauts.json the first time the dashboard runs.

  predictions   One row per model run (e.g. one uploaded video).
                Keeps the model's FULL output as JSON plus its status,
                and whether it is an alert for the UI.

  measurements  The health data we present and analyse for trends.
                One row = one reading of one metric, e.g.
                (A-07, cardioresp, hr_bpm, 71.8 bpm, 12:19:31).
                A video gives many rows: every reading the model made.
                (The dashboard reads astronauts + measurements through
                app/dashboard/repository.py.)
                `source` is where it came from (the model name, or "manual"
                for values typed in by hand) and `metric` is what it is.

"Long" format for measurements (one value per row, instead of one column per
metric) is what lets each model bring its own metrics without touching the
schema, and makes "HR for astronaut A-07 over the last week" one simple query.

- The database is ONE file: backend/astrohealth.db (git-ignored).
  Set the ASTROHEALTH_DB environment variable to use another path (tests do).
- We use Python's built-in sqlite3 module: no extra install, no ORM.
- The rest of the app only calls the functions below; no SQL anywhere else.
"""

import json
import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median

BACKEND_DIR = Path(__file__).resolve().parents[1]   # .../backend
DEFAULT_DB_PATH = BACKEND_DIR / "astrohealth.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS astronauts (
    id    TEXT PRIMARY KEY,                  -- e.g. A-01, same as astronaut_id elsewhere
    name  TEXT NOT NULL,
    role  TEXT
);

CREATE TABLE IF NOT EXISTS predictions (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    astronaut_id       TEXT,                 -- may be NULL (optional on upload)
    created_at         TEXT    NOT NULL,     -- UTC, ISO 8601
    video_file         TEXT,                 -- uploaded file name in backend/uploads/ (video or audio)
    model              TEXT,                 -- result["model"], e.g. "cardioresp"
    model_version      TEXT,                 -- result["model_version"]
    status             TEXT,                 -- result["status"], e.g. "ok"
    is_alert           INTEGER NOT NULL DEFAULT 0,   -- 1 = needs attention
    alert_acknowledged INTEGER NOT NULL DEFAULT 0,   -- 1 = someone handled it in the UI
    result_json        TEXT    NOT NULL      -- the full model output, as JSON
);
CREATE INDEX IF NOT EXISTS idx_predictions_astronaut
    ON predictions (astronaut_id, created_at);
CREATE INDEX IF NOT EXISTS idx_predictions_alerts
    ON predictions (is_alert, alert_acknowledged);

CREATE TABLE IF NOT EXISTS measurements (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    astronaut_id  TEXT,
    source        TEXT    NOT NULL,          -- model name (e.g. "cardioresp") or "manual"
    metric        TEXT    NOT NULL,          -- e.g. hr_bpm, respi_rate, glucose_mg_dl
    value         REAL    NOT NULL,
    unit          TEXT,                      -- e.g. bpm, breaths/min, mg/dL
    measured_at   TEXT    NOT NULL,          -- UTC, ISO 8601 with milliseconds
    offset_s      REAL,                      -- seconds into the video; NULL if manual
    prediction_id INTEGER REFERENCES predictions(id)   -- NULL if entered by hand
);
CREATE INDEX IF NOT EXISTS idx_measurements_trend
    ON measurements (astronaut_id, source, metric, measured_at);


-- MADA retains the stateless agent's text/check conversation for follow-up
-- turns. The patient must be a real roster member, distinct from responder.
CREATE TABLE IF NOT EXISTS mada_assessments (
    id                    TEXT PRIMARY KEY,
    patient_id            TEXT NOT NULL REFERENCES astronauts(id),
    responder_id          TEXT,
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL,
    action                TEXT NOT NULL,
    turns_json            TEXT NOT NULL,
    latest_response_json  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mada_patient_history
    ON mada_assessments (patient_id, updated_at);
"""

# Normal ranges used for alerts: (source, metric) -> (low, high).
# If the MEDIAN of a video's readings is outside its range, the prediction
# is an alert. (The median, so one noisy reading doesn't raise an alert.)
# PLACEHOLDER values, not clinical advice: set them with whoever owns the
# medical side. Respiratory rate is left out on purpose: the cardioresp
# README says RR is not validated well enough to act on.
ALERT_RANGES = {
    ("cardioresp", "hr_bpm"): (40.0, 120.0),
}

_initialized: set[str] = set()


def _db_path() -> Path:
    return Path(os.environ.get("ASTROHEALTH_DB", DEFAULT_DB_PATH))


def _connect() -> sqlite3.Connection:
    """
    Open the database, creating the tables the first time.
    A new connection per call keeps things simple and thread-safe
    (FastAPI runs normal `def` routes in a thread pool).
    """
    path = _db_path()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row             # rows behave like dicts
    conn.execute("PRAGMA foreign_keys = ON")   # SQLite needs this per connection
    if str(path) not in _initialized:
        conn.executescript(SCHEMA)
        _initialized.add(str(path))
    return conn


def to_iso(moment: datetime) -> str:
    """
    The one time format we store: UTC, ISO 8601, milliseconds, e.g.
    2026-11-14T12:19:31.010+00:00. Same length every time, so comparing the
    text gives the same answer as comparing the times ("since" filters).
    A time without a timezone is taken to be UTC.
    """
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat(timespec="milliseconds")


def init_db() -> None:
    """Create the tables if they don't exist yet. Safe to call many times."""
    _connect().close()


# --------------------------------------------------------------------------
# Astronauts (crew roster)
# --------------------------------------------------------------------------

def list_astronauts() -> list[dict]:
    """
    The roster, plus any astronaut_id that has data but isn't on the roster
    (e.g. someone typed a new ID on upload), listed with their ID as name.
    """
    conn = _connect()
    rows = conn.execute(
        """
        SELECT id, name, role FROM astronauts
        UNION
        SELECT DISTINCT astronaut_id, astronaut_id, NULL FROM measurements
         WHERE astronaut_id IS NOT NULL
           AND astronaut_id NOT IN (SELECT id FROM astronauts)
        ORDER BY id
        """
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_astronauts(astronauts: list[dict]) -> None:
    """Add roster entries ({id, name, role}); existing IDs are left as they are."""
    conn = _connect()
    with conn:
        conn.executemany(
            "INSERT OR IGNORE INTO astronauts (id, name, role) VALUES (:id, :name, :role)",
            [{"role": None, **a} for a in astronauts],
        )
    conn.close()


# --------------------------------------------------------------------------
# Shared seed data (data/seed/astrohealth_seed.json, committed to git)
# --------------------------------------------------------------------------

# Parents before children, so prediction_id in measurements always points
# at a row that is already there.
SEED_TABLES = ("astronauts", "predictions", "measurements")


def dump_tables() -> dict[str, list[dict]]:
    """Every row of every seed table, sorted by id (a stable order for git)."""
    conn = _connect()
    data = {
        table: [dict(r) for r in conn.execute(f"SELECT * FROM {table} ORDER BY id")]
        for table in SEED_TABLES
    }
    conn.close()
    return data


def has_data() -> bool:
    """True if there is at least one prediction or measurement."""
    conn = _connect()
    row = conn.execute(
        "SELECT 1 FROM predictions UNION ALL SELECT 1 FROM measurements LIMIT 1"
    ).fetchone()
    conn.close()
    return row is not None


def load_tables(data: dict[str, list[dict]]) -> dict[str, int]:
    """
    Insert rows from dump_tables() output, keeping their ids, all in one
    transaction. Rows whose id already exists are skipped. Columns the
    table doesn't have are ignored; missing ones get their default.
    Returns how many rows were added per table.
    """
    conn = _connect()
    added = {}
    with conn:
        for table in SEED_TABLES:
            columns = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
            count = 0
            for row in data.get(table, []):
                row = {k: v for k, v in row.items() if k in columns}
                cols = ", ".join(row)
                marks = ", ".join("?" for _ in row)
                cur = conn.execute(
                    f"INSERT OR IGNORE INTO {table} ({cols}) VALUES ({marks})",
                    list(row.values()),
                )
                count += cur.rowcount
            added[table] = count
    conn.close()
    return added


def roster_is_empty() -> bool:
    conn = _connect()
    row = conn.execute("SELECT 1 FROM astronauts LIMIT 1").fetchone()
    conn.close()
    return row is None


# --------------------------------------------------------------------------
# Predictions
# --------------------------------------------------------------------------

def is_alert(result: dict, measurements: list[dict] | None = None) -> bool:
    """
    >>> THE ALERT RULE. Change this as we learn more. <<<

    A prediction is an alert if the model says so explicitly ("alert": true),
    or if the median of a metric's readings is outside ALERT_RANGES.

    The model's "status" is NOT used: for cardioresp it describes data
    quality (warming_up, ok, partial, no_face, insufficient_data), not the
    astronaut's health. It is still saved, so the UI can show e.g.
    "retake the video".
    """
    if "alert" in result:
        return bool(result["alert"])
    source = str(result.get("model"))
    readings_by_metric = defaultdict(list)
    for m in measurements or []:
        readings_by_metric[m["metric"]].append(float(m["value"]))
    for metric, values in readings_by_metric.items():
        limits = ALERT_RANGES.get((source, metric))
        if limits and not (limits[0] <= median(values) <= limits[1]):
            return True
    return False


def _prediction_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "astronaut_id": row["astronaut_id"],
        "created_at": row["created_at"],
        "video_file": row["video_file"],
        "model": row["model"],
        "model_version": row["model_version"],
        "status": row["status"],
        "is_alert": bool(row["is_alert"]),
        "alert_acknowledged": bool(row["alert_acknowledged"]),
        "result": json.loads(row["result_json"]),
    }


def _str_or_none(value) -> str | None:
    return None if value is None else str(value)


def save_prediction(
    result: dict,
    astronaut_id: str | None = None,
    video_file: str | None = None,
    measurements: list[dict] | None = None,
) -> dict:
    """
    Store one model run, plus the readings taken from it, in one go
    (both are saved, or neither is). Returns the saved prediction with a
    "measurements" list.

    Each measurement is a dict with: metric, value, and optionally unit and
    offset_s (seconds into the video). They get this prediction's astronaut
    and the model name as their source.

    Time of a reading: we assume the video ENDED at upload time, so the last
    reading gets the upload time and earlier ones are offset back from it.
    That's approximate: we don't know when the video was actually recorded.
    """
    now = datetime.now(timezone.utc)
    created_at = to_iso(now)
    offsets = [m["offset_s"] for m in measurements or [] if m.get("offset_s") is not None]
    last_offset = max(offsets, default=0)
    model = _str_or_none(result.get("model"))
    conn = _connect()
    with conn:   # one transaction
        cur = conn.execute(
            """
            INSERT INTO predictions
                (astronaut_id, created_at, video_file, model, model_version,
                 status, is_alert, result_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                astronaut_id,
                created_at,
                video_file,
                model,
                _str_or_none(result.get("model_version")),
                _str_or_none(result.get("status")),
                int(is_alert(result, measurements)),
                json.dumps(result, default=str),
            ),
        )
        prediction_id = cur.lastrowid
        for m in measurements or []:
            offset_s = m.get("offset_s")
            seconds_before_end = last_offset - offset_s if offset_s is not None else 0
            measured_at = now - timedelta(seconds=seconds_before_end)
            _insert_measurement(
                conn,
                astronaut_id=astronaut_id,
                source=model or "unknown",
                metric=m["metric"],
                value=m["value"],
                unit=m.get("unit"),
                measured_at=to_iso(measured_at),
                offset_s=offset_s,
                prediction_id=prediction_id,
            )
    conn.close()
    saved = get_prediction(prediction_id)
    saved["measurements"] = list_measurements(prediction_id=prediction_id, limit=100_000)
    return saved


def get_prediction(prediction_id: int) -> dict | None:
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM predictions WHERE id = ?", (prediction_id,)
    ).fetchone()
    conn.close()
    return _prediction_row(row) if row else None


def list_predictions(astronaut_id: str | None = None, limit: int = 50) -> list[dict]:
    """Newest first. Pass astronaut_id to get one astronaut's history."""
    query = "SELECT * FROM predictions"
    params: list = []
    if astronaut_id is not None:
        query += " WHERE astronaut_id = ?"
        params.append(astronaut_id)
    query += " ORDER BY created_at DESC, id DESC LIMIT ?"
    params.append(limit)
    conn = _connect()
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [_prediction_row(r) for r in rows]


def list_alerts(
    astronaut_id: str | None = None,
    include_acknowledged: bool = False,
    limit: int = 50,
) -> list[dict]:
    """Alerts, newest first. By default only the ones nobody has handled."""
    query = "SELECT * FROM predictions WHERE is_alert = 1"
    params: list = []
    if not include_acknowledged:
        query += " AND alert_acknowledged = 0"
    if astronaut_id is not None:
        query += " AND astronaut_id = ?"
        params.append(astronaut_id)
    query += " ORDER BY created_at DESC, id DESC LIMIT ?"
    params.append(limit)
    conn = _connect()
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [_prediction_row(r) for r in rows]


def acknowledge_alert(prediction_id: int) -> dict | None:
    """Mark an alert as handled. Returns the updated row, or None if no such id."""
    conn = _connect()
    with conn:
        conn.execute(
            "UPDATE predictions SET alert_acknowledged = 1 WHERE id = ?",
            (prediction_id,),
        )
    conn.close()
    return get_prediction(prediction_id)


# --------------------------------------------------------------------------
# Measurements
# --------------------------------------------------------------------------

def _insert_measurement(conn, *, astronaut_id, source, metric, value, unit,
                        measured_at, offset_s, prediction_id) -> int:
    cur = conn.execute(
        """
        INSERT INTO measurements
            (astronaut_id, source, metric, value, unit,
             measured_at, offset_s, prediction_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (astronaut_id, source, metric, float(value), unit,
         measured_at, offset_s, prediction_id),
    )
    return cur.lastrowid


def add_measurement(
    astronaut_id: str,
    metric: str,
    value: float,
    unit: str | None = None,
    measured_at: str | None = None,
    source: str = "manual",
) -> dict:
    """Store one value that did not come from a model run (e.g. a lab result)."""
    conn = _connect()
    with conn:
        new_id = _insert_measurement(
            conn,
            astronaut_id=astronaut_id,
            source=source,
            metric=metric,
            value=value,
            unit=unit,
            measured_at=measured_at or to_iso(datetime.now(timezone.utc)),
            offset_s=None,
            prediction_id=None,
        )
    row = conn.execute("SELECT * FROM measurements WHERE id = ?", (new_id,)).fetchone()
    conn.close()
    return dict(row)


def list_measurements(
    astronaut_id: str | None = None,
    source: str | None = None,
    metric: str | None = None,
    since: str | None = None,
    until: str | None = None,
    prediction_id: int | None = None,
    limit: int = 1000,
) -> list[dict]:
    """
    Measurements in time order (oldest first), ready to draw as a trend.
    Every filter is optional; since/until are times from to_iso().
    If there are more than `limit`, you get the newest `limit` of them.
    """
    filters = {
        "astronaut_id = ?": astronaut_id,
        "source = ?": source,
        "metric = ?": metric,
        "measured_at >= ?": since,
        "measured_at <= ?": until,
        "prediction_id = ?": prediction_id,
    }
    where = [clause for clause, v in filters.items() if v is not None]
    params = [v for v in filters.values() if v is not None]
    query = "SELECT * FROM measurements"
    if where:
        query += " WHERE " + " AND ".join(where)
    # Take the newest `limit` rows, then return them oldest first.
    query = (
        f"SELECT * FROM ({query} ORDER BY measured_at DESC, id DESC LIMIT ?) "
        "ORDER BY measured_at ASC, id ASC"
    )
    params.append(limit)
    conn = _connect()
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]
