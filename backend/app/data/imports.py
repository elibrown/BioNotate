"""Stage research CSVs in draft and promote mapped values into production measurements."""
import csv
import hashlib
import json
import math
import os
from pathlib import Path

from app import db

CONFIG = json.loads((db.DATA_DIR / "biomarkers.json").read_text())
PHASES = {int(key): value for key, value in CONFIG["phases"].items()}
CATALOG = CONFIG["metrics"]

CREW_MAPPING = CONFIG["crew_mapping"]

DRAFT_SCHEMA = (db.DATA_DIR / 'schema' / 'draft.sql').read_text()

NOTICE = ('Research only. Final profiles combine unrelated NASA and PhysioNet subjects, '
          'derived proxies and potentially cross-subject filled values. '
          'Per-value provenance is unavailable. Units and names follow the supplied biologist dictionary; '
          'clinical thresholds are not activated. Mission phases apply only to the final table.')


def draft_path():
    default = db._db_path().with_name(db._db_path().stem + '-draft.sqlite3')
    return Path(os.environ.get('ASTROHEALTH_DRAFT_DB', default))


def _promote(conn, dataset_id):
    rows = conn.execute(
        'SELECT o.*, l.crew_id, d.filename, d.imported_at FROM draft.research_observations o '
        'JOIN draft.research_crew_links l ON l.dataset_id=o.dataset_id AND l.subject_id=o.subject_id '
        'JOIN draft.research_datasets d ON d.id=o.dataset_id WHERE o.dataset_id=?', (dataset_id,)
    ).fetchall()
    count = 0
    for row in rows:
        meta = CATALOG.get(row['metric'])
        if meta is None:
            raise ValueError(f"Unknown biomarker: {row['metric']}")
        metric = meta['measurement_metric']
        count += conn.execute(
            "INSERT OR IGNORE INTO measurements (astronaut_id, source, metric, value, unit, "
            "measured_at, context, phase_index, mission_phase, dataset_id, dataset_filename, "
            "source_row, original_subject_id, original_metric, measurement_type, quality_flag, imported_at) "
            "VALUES (?, 'biologist_csv', ?, ?, ?, NULL, 'research', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (row['crew_id'], metric, row['value'], meta['unit'], row['timepoint'], row['timepoint_label'],
             dataset_id, row['filename'], row['row_number'], row['subject_id'], row['metric'],
             meta['modality'], 'per_value_provenance_unknown_may_be_pooled', row['imported_at'])
        ).rowcount
    return count


def connect():
    """Main has three domain tables. Raw import staging is attached as draft."""
    conn = db._connect()
    try:
        conn.execute('ATTACH DATABASE ? AS draft', (str(draft_path()),))
        conn.executescript(DRAFT_SCHEMA)
        legacy = {row[0] for row in conn.execute("SELECT name FROM main.sqlite_master WHERE type='table'")}
        tables = ('research_datasets', 'research_observations', 'research_crew_links')
        if any(table in legacy for table in tables):
            if not all(table in legacy for table in tables):
                raise ValueError('Incomplete legacy research schema; migration stopped')
            with conn:
                for table in tables:
                    conn.execute(f'INSERT OR IGNORE INTO draft.{table} SELECT * FROM main.{table}')
                    # Fail rather than silently discard conflicting rows in draft.
                    if conn.execute(f'SELECT * FROM main.{table} EXCEPT SELECT * FROM draft.{table}').fetchone():
                        raise ValueError(f'Conflicting draft data in {table}')
                for row in conn.execute('SELECT id FROM draft.research_datasets').fetchall():
                    _promote(conn, row['id'])
                for table in ('research_crew_links', 'research_observations', 'research_datasets'):
                    conn.execute(f'DROP TABLE main.{table}')
        return conn
    except Exception:
        conn.close()
        raise


def import_csv(path: Path) -> dict:
    content = path.read_bytes()
    dataset_id = hashlib.sha256(content).hexdigest()
    rows = []
    with path.open(newline='', encoding='utf-8-sig') as stream:
        reader = csv.DictReader(stream)
        final_format = 'Timepoint' in (reader.fieldnames or [])
        required = {'Astronaut_ID', 'Timepoint'} if final_format else {'Astronaut_ID', 'Chronological_Day', 'Timepoint_Label'}
        seen = set()
        fields = reader.fieldnames or []
        metrics = [key for key in fields if key.startswith('BM')]
        if not required.issubset(fields) or not metrics or len(fields) != len(set(fields)):
            raise ValueError('Expected unique subject, timepoint and BM biomarker columns')
        if set(fields) != required | set(metrics):
            raise ValueError('Unexpected CSV columns')
        for number, row in enumerate(reader, 2):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f'Row {number}: wrong number of columns')
            subject = row['Astronaut_ID'].strip()
            timepoint = float(row['Timepoint'] if final_format else row['Chronological_Day'])
            if final_format and timepoint not in PHASES:
                raise ValueError(f'Row {number}: final timepoint must be 1–5')
            if (subject, timepoint) in seen:
                raise ValueError(f'Row {number}: duplicate subject/timepoint')
            seen.add((subject, timepoint))
            label = PHASES[int(timepoint)] if final_format else row['Timepoint_Label']
            if not subject or not math.isfinite(timepoint):
                raise ValueError(f'Row {number}: invalid subject/timepoint')
            for metric in metrics:
                raw = row[metric].strip()
                if not raw:
                    continue
                value = float(raw)
                if not math.isfinite(value):
                    raise ValueError(f'Row {number}: non-finite {metric}')
                rows.append((dataset_id, number, subject, timepoint,
                             label, metric, value))
    if not rows:
        raise ValueError('Dataset has no observations')
    conn = connect()
    try:
        with conn:
            added = conn.execute('INSERT OR IGNORE INTO draft.research_datasets(id, filename) VALUES (?, ?)',
                                 (dataset_id, path.name)).rowcount
            if added:
                conn.executemany('INSERT INTO draft.research_observations VALUES (?, ?, ?, ?, ?, ?, ?)', rows)
            if final_format:
                subjects = {row[2] for row in rows}
                conn.executemany('INSERT OR IGNORE INTO draft.research_crew_links VALUES (?, ?, ?)',
                                 [(dataset_id, crew, subject) for crew, subject in CREW_MAPPING.items()
                                  if subject in subjects])
            promoted = _promote(conn, dataset_id)
    finally:
        conn.close()
    return {'dataset_id': dataset_id, 'inserted': len(rows) if added else 0, 'measurements_inserted': promoted}


def datasets():
    conn = connect()
    try:
        return [dict(row) for row in conn.execute('SELECT * FROM draft.research_datasets ORDER BY imported_at, id')]
    finally:
        conn.close()


def observations(dataset_id: str, subject_id: str | None = None):
    conn = connect()
    try:
        query = 'SELECT * FROM draft.research_observations WHERE dataset_id = ?'
        params = [dataset_id]
        if subject_id is not None:
            query += ' AND subject_id = ?'
            params.append(subject_id)
        return [dict(row) for row in conn.execute(query + ' ORDER BY timepoint, row_number, metric', params)]
    finally:
        conn.close()


def crew_datasets(crew_id: str):
    """Compatibility response for existing graphs; values come only from measurements."""
    rows = db.list_measurements(astronaut_id=crew_id, source='biologist_csv', limit=10000)
    grouped = {}
    for row in rows:
        item = grouped.setdefault(row['dataset_id'], {
            'id': row['dataset_id'], 'filename': row['dataset_filename'],
            'subject_id': row['original_subject_id'], 'imported_at': row['imported_at'],
            'observations': []})
        item['observations'].append({**row, 'row_number': row['source_row'],
            'subject_id': row['original_subject_id'], 'metric': row['original_metric'],
            'timepoint': row['phase_index'], 'timepoint_label': row['mission_phase']})
    return sorted(grouped.values(), key=lambda item: (item['imported_at'] or '', item['id']), reverse=True)
