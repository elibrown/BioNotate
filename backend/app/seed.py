"""
Shared seed data: the database rows the team keeps in git.

The database file (backend/astrohealth.db) is binary and git-ignored, so we
share its contents as text instead: data/seed/astrohealth_seed.json.

  Export your local database to that file (run from backend/):
      python -m app.seed export

  Load it: automatic. When the backend starts and the database has no
  predictions or measurements yet, the file is loaded. A database that
  already has data is never touched by JSON bootstrap. App startup also merges
  the reviewed shared_demo.db snapshot without overwriting existing rows.

File format: one JSON object with a list per table. Each row is on its own
line and rows are sorted by id, so a new row shows up in `git diff` as one
new line.
"""

import json
import sys
import sqlite3
from pathlib import Path

from app import db

SEED_FILE = Path(__file__).resolve().parents[2] / "data" / "seed" / "astrohealth_seed.json"
SNAPSHOT_FILE = SEED_FILE.with_name('shared_demo.db')
BIOLOGY_FILE = SEED_FILE.parents[1] / 'research' / 'biologist-final.csv'


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
                if conn.execute('SELECT 1 FROM measurements WHERE dataset_id IS NULL AND ' + ' AND '.join(key+' IS ?' for key in natural),
                                [row[key] for key in natural]).fetchone():
                    continue
                conn.execute('INSERT INTO measurements (' + ','.join(row) + ') VALUES (' + ','.join('?' for _ in row) + ')', list(row.values()))
                counts['measurements'] += 1
    finally:
        source.close()
        conn.close()
    return counts


def initialize():
    """Load the shared baseline without replacing developer-owned readings."""
    added = load_snapshot() if SNAPSHOT_FILE.is_file() else load_seed_if_empty()
    db.add_astronauts(json.loads((db.DATA_DIR / 'astronauts.json').read_text(encoding='utf-8')), update_existing=True)
    return added


if __name__ == "__main__":
    if sys.argv[1:] != ["export"]:
        sys.exit("usage: python -m app.seed export")
    counts = export_seed()
    print(f"Wrote {SEED_FILE}")
    for table, n in counts.items():
        print(f"  {table}: {n} rows")
