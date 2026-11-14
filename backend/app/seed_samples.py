"""Explicit, repeatable SQLite sample data: python -m app.seed_samples.

Uses source=simulation, never replaces real records or imports the CSV.
"""
import json
from datetime import datetime
from app import db
from app.dashboard.repository import DATA_DIR


def seed_samples():
    profiles = json.loads((DATA_DIR / 'astronauts.json').read_text())
    known = {row['id'] for row in db.list_astronauts()}
    db.add_astronauts([row for row in profiles if row['id'] not in known])
    rows = json.loads((DATA_DIR / 'metrics.json').read_text())
    rules = json.loads((DATA_DIR / 'rules.json').read_text())
    readings = [(row['astronaut_id'], row['key'], row['value'],
                 rules['metrics'][row['key']]['unit'],
                 db.to_iso(datetime.fromisoformat(row['observed_at'].replace('Z', '+00:00'))))
                for row in rows]
    for astronaut, systolic, diastolic, glucose, temperature in [
        ('A-01', 118, 76, 92, 36.7), ('A-02', 132, 84, 105, 37.1),
        ('A-03', 112, 72, 88, 36.5), ('A-04', 124, 80, 99, 36.9),
    ]:
        for index in range(3):
            moment = f'2026-11-14T10:0{index}:00.000+00:00'
            for key, value, unit in [('systolic_bp', systolic-index, 'mmHg'),
                                     ('diastolic_bp', diastolic-index, 'mmHg'),
                                     ('glucose', glucose+index, 'mg/dL'),
                                     ('temperature_c', temperature, '°C')]:
                readings.append((astronaut, key, value, unit, moment))
    existing = {(row['astronaut_id'], row['metric'], row['measured_at'])
                for row in db.list_measurements(source='simulation', limit=10000)}
    added = 0
    for astronaut, metric, value, unit, moment in readings:
        if (astronaut, metric, moment) not in existing:
            db.add_measurement(astronaut, metric, value, unit, moment, source='simulation')
            existing.add((astronaut, metric, moment))
            added += 1
    return added


if __name__ == '__main__':
    print(f'Added {seed_samples()} synthetic measurements to SQLite; existing data preserved.')
