-- Production domain tables. Indexes are applied after legacy upgrades.
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



CREATE TABLE IF NOT EXISTS measurements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    astronaut_id TEXT,
    source TEXT NOT NULL,
    metric TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT,
    measured_at TEXT,
    offset_s REAL,
    prediction_id INTEGER REFERENCES predictions(id),
    context TEXT NOT NULL DEFAULT 'live' CHECK(context IN ('live', 'research')),
    phase_index REAL,
    mission_phase TEXT,
    dataset_id TEXT,
    dataset_filename TEXT,
    source_row INTEGER,
    original_subject_id TEXT,
    original_metric TEXT,
    measurement_type TEXT,
    quality_flag TEXT,
    imported_at TEXT
);
