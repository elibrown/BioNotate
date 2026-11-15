"""Initialize reference data and inspect/back up the configured SQLite database."""
import argparse
import json
import hashlib
import tempfile
import os
import sqlite3
from pathlib import Path

from app import db
from app.data import imports as biologist

DATA_DIR = db.DATA_DIR
BIOLOGY_FILE = DATA_DIR / 'research' / 'biologist-final.csv'
SEED_FILE = DATA_DIR / 'seed' / 'astrohealth_seed.json'
SNAPSHOT_FILE = DATA_DIR / 'seed' / 'shared_demo.db'

def export_seed(path: Path | None = None) -> dict[str, int]:
    """Write every row of the database to the seed file. Returns rows per table."""
    path = path or SEED_FILE
    data = db.dump_tables()
    lines = ["{"]
    for t, table in enumerate(db.SEED_TABLES):
        rows = data[table]
        lines.append(f'  "{table}": [')
        for i, row in enumerate(rows):
            comma = "," if i < len(rows) - 1 else ""
            lines.append("    " + json.dumps(row, ensure_ascii=False) + comma)
        comma = "," if t < len(db.SEED_TABLES) - 1 else ""
        lines.append("  ]" + comma)
    lines.append("}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return {table: len(rows) for table, rows in data.items()}


def load_seed_if_empty(path: Path | None = None) -> dict[str, int] | None:
    """
    Load the seed file if the database has no predictions or measurements.
    Returns rows added per table, or None if nothing was loaded.
    """
    path = path or SEED_FILE
    if db.has_data() or not path.exists():
        return None
    return db.load_tables(json.loads(path.read_text(encoding="utf-8")))



def load_snapshot(path: Path | None = None, *, include_research: bool = True) -> dict:
    """Merge a reviewed snapshot, remapping IDs and preserving existing local records."""
    path = path or SNAPSHOT_FILE
    if path.resolve() == db._db_path().resolve():
        raise ValueError('Snapshot must be separate from the working database')
    source = sqlite3.connect(f'{path.resolve().as_uri()}?mode=ro', uri=True)
    source.row_factory = sqlite3.Row
    conn = db._connect()
    counts = dict.fromkeys(db.SEED_TABLES, 0)
    try:
        tables = {r[0] for r in source.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        if tables != set(db.SEED_TABLES) or source.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or source.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('Invalid three-table snapshot')
        prediction_ids = {}
        with conn:
            for row in source.execute('SELECT * FROM astronauts ORDER BY id'):
                counts['astronauts'] += conn.execute('INSERT OR IGNORE INTO astronauts VALUES (?, ?, ?)', tuple(row)).rowcount
            for original in source.execute('SELECT * FROM predictions ORDER BY id'):
                row = dict(original)
                source_id = row.pop('id')
                match = conn.execute('SELECT id FROM predictions WHERE astronaut_id IS ? AND created_at=? AND model IS ? AND result_json=? ORDER BY id LIMIT 1',
                    (row['astronaut_id'], row['created_at'], row['model'], row['result_json'])).fetchone()
                if match:
                    prediction_ids[source_id] = match['id']
                else:
                    cursor = conn.execute('INSERT INTO predictions (' + ','.join(row) + ') VALUES (' + ','.join('?' for _ in row) + ')', list(row.values()))
                    prediction_ids[source_id] = cursor.lastrowid
                    counts['predictions'] += 1
            for original in source.execute('SELECT * FROM measurements ORDER BY id'):
                row = dict(original)
                row.pop('id')
                if not include_research and row['context'] == 'research':
                    continue
                if row['prediction_id'] is not None:
                    row['prediction_id'] = prediction_ids[row['prediction_id']]
                if row['dataset_id'] and conn.execute('SELECT 1 FROM measurements WHERE dataset_id=? AND source_row=? AND original_metric=?',
                    (row['dataset_id'], row['source_row'], row['original_metric'])).fetchone():
                    continue
                # Recognize older copies of the same seed rows that had no import identity.
                natural = ('astronaut_id','source','metric','value','unit','measured_at','offset_s','prediction_id')
                if conn.execute('SELECT 1 FROM measurements WHERE ' + ' AND '.join(key+' IS ?' for key in natural),
                                [row[key] for key in natural]).fetchone():
                    continue
                conn.execute('INSERT INTO measurements (' + ','.join(row) + ') VALUES (' + ','.join('?' for _ in row) + ')', list(row.values()))
                counts['measurements'] += 1
    finally:
        source.close()
        conn.close()
    return counts


def build_snapshot(destination: Path) -> dict:
    """Build only from committed fixtures, never from a developer's working database."""
    if destination.exists():
        raise FileExistsError(destination)
    keys = ('ASTROHEALTH_DB', 'ASTROHEALTH_DRAFT_DB')
    previous = {key: os.environ.get(key) for key in keys}
    try:
        with tempfile.TemporaryDirectory() as directory:
            os.environ['ASTROHEALTH_DB'] = str(Path(directory) / 'snapshot.db')
            os.environ['ASTROHEALTH_DRAFT_DB'] = str(Path(directory) / 'draft.sqlite3')
            db.load_tables(json.loads(SEED_FILE.read_text()))
            db.add_astronauts(json.loads((DATA_DIR / 'astronauts.json').read_text()), update_existing=True)
            biologist.import_csv(BIOLOGY_FILE)
            demo = json.loads((DATA_DIR / 'demo_vitals.json').read_text())
            conn = db._connect()
            with conn:
                identity = 'shared-seed:' + hashlib.sha256(SEED_FILE.read_bytes()).hexdigest()
                conn.execute("UPDATE measurements SET dataset_id=?, source_row=id, original_metric=metric, dataset_filename='astrohealth_seed.json', quality_flag='shared_demo_fixture' WHERE dataset_id IS NULL", (identity,))
                for number, crew in enumerate(demo['crew']):
                    for metric, unit in [('hr_bpm','bpm'), ('respi_rate','breaths/min')]:
                        conn.execute('INSERT INTO measurements (astronaut_id,source,metric,value,unit,measured_at,dataset_id,source_row,original_metric,dataset_filename,measurement_type,quality_flag) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                            (crew['astronaut_id'],demo['source'],metric,crew[metric],unit,demo['measured_at'],demo['dataset_id'],number+1,metric,'demo_vitals.json','Synthetic demo',demo['quality_flag']))
                for number, reading in enumerate(demo.get('extra_readings', []), len(demo['crew'])+1):
                    conn.execute('INSERT INTO measurements (astronaut_id,source,metric,value,unit,measured_at,dataset_id,source_row,original_metric,dataset_filename,measurement_type,quality_flag) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                        (reading['astronaut_id'], demo['source'], reading['metric'], reading['value'], reading['unit'], reading['measured_at'], demo['dataset_id'], number, reading['metric'], 'demo_vitals.json', 'Synthetic demo', demo['quality_flag']))
            conn.close()
            result = backup(destination)
            result['counts'] = status()['counts']
            return result
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def initialize() -> dict:
    """Seed only an empty live DB; import versioned research even into populated DBs."""
    enabled = os.environ.get('ASTROHEALTH_IMPORT_BIOLOGY', 'true').lower()
    if enabled not in {'true', 'false'}:
        raise ValueError('ASTROHEALTH_IMPORT_BIOLOGY must be true or false')
    if enabled == 'true':
        if not BIOLOGY_FILE.is_file():
            raise FileNotFoundError(f'Missing packaged biology dataset: {BIOLOGY_FILE}')
    result = {'seed': None, 'shared_snapshot': None, 'biology': None}
    if SNAPSHOT_FILE.is_file():
        result['shared_snapshot'] = load_snapshot(include_research=enabled == 'true')
    else:
        result['seed'] = load_seed_if_empty()
    db.add_astronauts(json.loads((DATA_DIR / 'astronauts.json').read_text()), update_existing=True)
    if enabled == 'true':
        result['biology'] = biologist.import_csv(BIOLOGY_FILE)
    return result


def status() -> dict:
    """Report which DB is queried, row counts and imported dataset versions."""
    conn = biologist.connect()
    try:
        tables = db.SEED_TABLES
        counts = {table: conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                  for table in tables}
    finally:
        conn.close()
    return {'database': str(db._db_path().resolve()), 'counts': counts,
            'draft_database': str(biologist.draft_path().resolve()),
            'draft_datasets': biologist.datasets()}


def backup(destination: Path) -> dict:
    """Back up all production tables including biology measurements; refuse overwrite."""
    source = db._db_path()
    if not source.is_file():
        raise FileNotFoundError(f'Database does not exist: {source}')
    # Exclusive file creation also prevents backing up over the source database.
    with destination.open('xb'):
        pass
    conn = sqlite3.connect(f'{source.resolve().as_uri()}?mode=ro', uri=True)
    target = sqlite3.connect(destination)
    try:
        conn.backup(target)
        if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError('Backup failed integrity check')
    finally:
        target.close()
        conn.close()
    return {'backup': str(destination.resolve())}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    snapshot_parser = commands.add_parser('build-snapshot', help='Build reviewed shared demo DB from repository fixtures')
    snapshot_parser.add_argument('destination', type=Path)
    commands.add_parser('init', help='Apply startup initialization without deleting data')
    commands.add_parser('export', help='Export production rows to the shared seed JSON')
    import_parser = commands.add_parser('import-csv', help='Stage and promote an explicit CSV')
    import_parser.add_argument('csv', type=Path)
    commands.add_parser('status', help='Show database path, counts and dataset versions')
    backup_parser = commands.add_parser('backup', help='Create a full SQLite backup')
    backup_parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    if args.command == 'build-snapshot':
        result = build_snapshot(args.destination)
    elif args.command == 'init':
        result = initialize()
    elif args.command == 'status':
        result = status()
    elif args.command == 'export':
        result = export_seed()
    elif args.command == 'import-csv':
        result = biologist.import_csv(args.csv)
    else:
        result = backup(args.destination)
    print(json.dumps(result, indent=2))
