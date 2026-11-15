-- Raw import staging only; attach the draft database before applying.
CREATE TABLE IF NOT EXISTS draft.research_datasets (
 id TEXT PRIMARY KEY, filename TEXT NOT NULL, imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS draft.research_crew_links (
 dataset_id TEXT NOT NULL REFERENCES research_datasets(id),
 crew_id TEXT NOT NULL, subject_id TEXT NOT NULL,
 PRIMARY KEY(dataset_id, crew_id)
);
CREATE TABLE IF NOT EXISTS draft.research_observations (
 dataset_id TEXT NOT NULL REFERENCES research_datasets(id),
 row_number INTEGER NOT NULL, subject_id TEXT NOT NULL,
 timepoint REAL NOT NULL, timepoint_label TEXT NOT NULL,
 metric TEXT NOT NULL, value REAL NOT NULL,
 PRIMARY KEY(dataset_id, row_number, metric)
);
