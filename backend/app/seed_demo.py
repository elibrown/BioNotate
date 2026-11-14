"""Explicit, repeatable seeding of synthetic JSON readings into SQLite.

Run from backend/: python -m app.seed_demo
Does not import the biologist's CSV or replace existing records.
"""
import json
from datetime import datetime
from app import db
from app.dashboard.repository import DATA_DIR


def seed_dashboard():
    astronauts = json.loads((DATA_DIR / "astronauts.json").read_text())
    rows = json.loads((DATA_DIR / "metrics.json").read_text())
    rules = json.loads((DATA_DIR / "rules.json").read_text())
    existing = {row["id"] for row in db.list_astronauts()}
    db.add_astronauts([row for row in astronauts if row["id"] not in existing])
    conn = db._connect()
    inserted = 0
    try:
        with conn:
            for row in rows:
                observed = db.to_iso(datetime.fromisoformat(row['observed_at'].replace('Z', '+00:00')))
                found = conn.execute(
                    "SELECT 1 FROM measurements WHERE source = 'simulation' AND astronaut_id = ? AND metric = ? AND measured_at = ?",
                    (row['astronaut_id'], row['key'], observed),
                ).fetchone()
                if found or row['value'] is None:
                    continue
                db._insert_measurement(conn, astronaut_id=row['astronaut_id'], source='simulation',
                                       metric=row['key'], value=row['value'], unit=rules['metrics'][row['key']]['unit'],
                                       measured_at=observed, offset_s=None, prediction_id=None)
                inserted += 1
    finally:
        conn.close()
    return inserted


if __name__ == '__main__':
    print(f"Inserted {seed_dashboard()} simulated readings; existing records retained.")
