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

-- Indexes
-- Apply after production table creation/upgrade.
CREATE INDEX IF NOT EXISTS idx_predictions_astronaut
    ON predictions (astronaut_id, created_at);

CREATE INDEX IF NOT EXISTS idx_predictions_alerts
    ON predictions (is_alert, alert_acknowledged);

CREATE INDEX IF NOT EXISTS idx_measurements_trend
    ON measurements (astronaut_id, source, metric, measured_at);

CREATE UNIQUE INDEX IF NOT EXISTS idx_measurements_import ON measurements
    (dataset_id, source_row, original_metric) WHERE dataset_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_mada_patient_history
    ON mada_assessments (patient_id, updated_at);
