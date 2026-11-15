-- Apply after production table creation/upgrade.
CREATE INDEX IF NOT EXISTS idx_predictions_astronaut
    ON predictions (astronaut_id, created_at);

CREATE INDEX IF NOT EXISTS idx_predictions_alerts
    ON predictions (is_alert, alert_acknowledged);

CREATE INDEX IF NOT EXISTS idx_measurements_trend
    ON measurements (astronaut_id, source, metric, measured_at);

CREATE UNIQUE INDEX IF NOT EXISTS idx_measurements_import ON measurements
    (dataset_id, source_row, original_metric) WHERE dataset_id IS NOT NULL;
