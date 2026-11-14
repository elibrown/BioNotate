"""
Storage (SQLite): predictions, measurements and the list of biomarker types.

Three tables:

  predictions   One row per model run (e.g. one uploaded video).
                Keeps the model's FULL output as JSON plus its status,
                and whether it is an alert for the UI.

  measurements  The health data we present and analyse for trends.
                One row = one number for one astronaut at one time,
                e.g. (A-07, BM06_HR_HRV_RMSSD, hr_bpm, 62.2, bpm, 2026-11-14T12:19Z).
                Rows can come from a model run (prediction_id is set) or be
                entered by hand, e.g. lab results (prediction_id is NULL).

  biomarkers    The allowed biomarker types (BM01 ... BM12). Adding a new
                kind of data = adding one row here; no table changes.

"Long" format for measurements (one value per row, instead of one column per
biomarker) is what lets us add new kinds of data without touching the schema,
and makes "HR for astronaut A-07 over the last week" a single simple query.

- The database is ONE file: backend/astrohealth.db (git-ignored).
  Set the ASTROHEALTH_DB environment variable to use another path (tests do).
- We use Python's built-in sqlite3 module: no extra install, no ORM.
- The rest of the app only calls the functions below; no SQL anywhere else.
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]   # .../backend
DEFAULT_DB_PATH = BACKEND_DIR / "astrohealth.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS biomarkers (
    code        TEXT PRIMARY KEY,          -- e.g. BM06_HR_HRV_RMSSD
    name        TEXT NOT NULL,             -- human-readable, for the UI
    description TEXT
);

CREATE TABLE IF NOT EXISTS predictions (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    astronaut_id       TEXT,                 -- may be NULL (optional on upload)
    created_at         TEXT    NOT NULL,     -- UTC, ISO 8601
    video_file         TEXT,                 -- file name in backend/uploads/
    model              TEXT,                 -- result["model"], e.g. "rppg"
    model_version      TEXT,                 -- result["model_version"]
    status             TEXT,                 -- result["status"], e.g. "ok"
    is_alert           INTEGER NOT NULL DEFAULT 0,   -- 1 = needs attention
    alert_acknowledged INTEGER NOT NULL DEFAULT 0,   -- 1 = someone saw it in the UI
    result_json        TEXT    NOT NULL      -- the full model output, as JSON
);
CREATE INDEX IF NOT EXISTS idx_predictions_astronaut
    ON predictions (astronaut_id, created_at);
CREATE INDEX IF NOT EXISTS idx_predictions_alerts
    ON predictions (is_alert, alert_acknowledged);

CREATE TABLE IF NOT EXISTS measurements (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    astronaut_id  TEXT,
    biomarker     TEXT    NOT NULL REFERENCES biomarkers(code),
    metric        TEXT    NOT NULL,          -- e.g. hr_bpm, rmssd_ms, glucose_mg_dl
    value         REAL    NOT NULL,
    unit          TEXT,                      -- e.g. bpm, ms, mg/dL
    measured_at   TEXT    NOT NULL,          -- UTC, ISO 8601
    prediction_id INTEGER REFERENCES predictions(id),  -- NULL if entered by hand
    source        TEXT                       -- e.g. "rppg" (model) or "manual"
);
CREATE INDEX IF NOT EXISTS idx_measurements_trend
    ON measurements (astronaut_id, biomarker, metric, measured_at);
"""

# The biomarker types we know about today. New ones can be added at runtime
# with add_biomarker() / POST /api/biomarkers, or by adding a line here.
DEFAULT_BIOMARKERS = [
    ("BM01_CBC_WBC_Lymph_Hgb", "Blood count: WBC, lymphocytes, hemoglobin"),
    ("BM02_CMP_Glucose_Ca_Renal", "Metabolic panel: glucose, calcium, renal"),
    ("BM03_Blood_CRP_Cytokines", "Inflammation: CRP, cytokines"),
    ("BM04_Urine_Ca_USG_pH_Citrate", "Urine: calcium, specific gravity, pH, citrate"),
    ("BM05_Urine_Proteomics_UTI", "Urine proteomics, UTI"),
    ("BM06_HR_HRV_RMSSD", "Heart rate and HRV (RMSSD)"),
    ("BM07_Respiratory_Rate_CO2", "Respiratory rate, CO2"),
    ("BM08_PTT_Blood_Pressure", "Blood pressure (pulse transit time)"),
    ("BM09_Sleep_WASO_Efficiency", "Sleep: WASO, efficiency"),
    ("BM10_ONSD_IJV_Ultrasound", "Ultrasound: ONSD, IJV"),
    ("BM11_Cognitive_PERCLOS_CTB", "Cognition: PERCLOS, cognitive test battery"),
    ("BM12_Skin_Rash_Microbiome", "Skin: rash, microbiome"),
]

# Model statuses that mean "nothing wrong". Anything else is an alert.
NORMAL_STATUSES = {"ok", "normal"}

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
        conn.executemany(
            "INSERT OR IGNORE INTO biomarkers (code, name) VALUES (?, ?)",
            DEFAULT_BIOMARKERS,
        )
        conn.commit()
        _initialized.add(str(path))
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init_db() -> None:
    """Create the tables if they don't exist yet. Safe to call many times."""
    _connect().close()


# --------------------------------------------------------------------------
# Biomarker types
# --------------------------------------------------------------------------

def list_biomarkers() -> list[dict]:
    conn = _connect()
    rows = conn.execute("SELECT * FROM biomarkers ORDER BY code").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def biomarker_exists(code: str) -> bool:
    conn = _connect()
    row = conn.execute("SELECT 1 FROM biomarkers WHERE code = ?", (code,)).fetchone()
    conn.close()
    return row is not None


def add_biomarker(code: str, name: str, description: str | None = None) -> dict:
    """Register a new kind of data. Does nothing if the code already exists."""
    conn = _connect()
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO biomarkers (code, name, description) VALUES (?, ?, ?)",
            (code, name, description),
        )
    row = conn.execute("SELECT * FROM biomarkers WHERE code = ?", (code,)).fetchone()
    conn.close()
    return dict(row)


# --------------------------------------------------------------------------
# Predictions
# --------------------------------------------------------------------------

def is_alert(result: dict) -> bool:
    """
    >>> THE ALERT RULE. Change this as we learn what the models return. <<<

    A prediction is an alert if the model says so explicitly ("alert": true),
    or if its "status" is not one of NORMAL_STATUSES ("ok", "normal").
    """
    if "alert" in result:
        return bool(result["alert"])
    status = result.get("status")
    return status is not None and str(status).lower() not in NORMAL_STATUSES


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
    Store one model run, plus the measurements taken from it, in one go
    (both are saved, or neither is). Returns the saved prediction with a
    "measurements" list.

    Each measurement is a dict with: biomarker, metric, value, and
    optionally unit. They get this prediction's astronaut, time and model.
    """
    created_at = _now()
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
                int(is_alert(result)),
                json.dumps(result, default=str),
            ),
        )
        prediction_id = cur.lastrowid
        for m in measurements or []:
            _insert_measurement(
                conn,
                astronaut_id=astronaut_id,
                biomarker=m["biomarker"],
                metric=m["metric"],
                value=m["value"],
                unit=m.get("unit"),
                measured_at=created_at,
                prediction_id=prediction_id,
                source=model,
            )
    conn.close()
    saved = get_prediction(prediction_id)
    saved["measurements"] = list_measurements(prediction_id=prediction_id)
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
    conn = _connect()
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [_prediction_row(r) for r in rows]


def acknowledge_alert(prediction_id: int) -> dict | None:
    """Mark an alert as seen. Returns the updated row, or None if no such id."""
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

def _insert_measurement(conn, *, astronaut_id, biomarker, metric, value,
                        unit, measured_at, prediction_id, source) -> int:
    cur = conn.execute(
        """
        INSERT INTO measurements
            (astronaut_id, biomarker, metric, value, unit,
             measured_at, prediction_id, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (astronaut_id, biomarker, metric, float(value), unit,
         measured_at, prediction_id, source),
    )
    return cur.lastrowid


def add_measurement(
    astronaut_id: str,
    biomarker: str,
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
            biomarker=biomarker,
            metric=metric,
            value=value,
            unit=unit,
            measured_at=measured_at or _now(),
            prediction_id=None,
            source=source,
        )
    row = conn.execute("SELECT * FROM measurements WHERE id = ?", (new_id,)).fetchone()
    conn.close()
    return dict(row)


def list_measurements(
    astronaut_id: str | None = None,
    biomarker: str | None = None,
    metric: str | None = None,
    since: str | None = None,
    until: str | None = None,
    prediction_id: int | None = None,
    limit: int = 1000,
) -> list[dict]:
    """
    Measurements in time order (oldest first), ready to draw as a trend.
    Every filter is optional; since/until are ISO 8601 times (UTC).
    """
    filters = {
        "astronaut_id = ?": astronaut_id,
        "biomarker = ?": biomarker,
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
