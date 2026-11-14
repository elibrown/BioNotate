"""Copy the versioned team database to/from an independent runtime database.

python -m app.db_snapshot init    # initialize only if runtime DB is absent
python -m app.db_snapshot export  # update the tracked snapshot deliberately
"""
import argparse
import os
import sqlite3
from pathlib import Path
from tempfile import NamedTemporaryFile

from app import db

SHARED_DB = Path(__file__).resolve().parents[2] / 'data' / 'shared' / 'astrohealth.sqlite3'


def copy_database(source: Path, target: Path):
    source, target = source.resolve(), target.resolve()
    if source == target:
        raise ValueError('The shared snapshot and runtime database must be separate files.')
    if not source.is_file():
        raise FileNotFoundError(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=target.parent, suffix='.sqlite3', delete=False) as temporary:
        temporary_path = Path(temporary.name)
    try:
        with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as connection:
            with sqlite3.connect(temporary_path) as snapshot:
                connection.backup(snapshot)
                if snapshot.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('Database integrity check failed.')
        os.replace(temporary_path, target)
    finally:
        temporary_path.unlink(missing_ok=True)


def initialize_database():
    target = db._db_path()
    if target.exists():
        return False
    copy_database(SHARED_DB, target)
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['init', 'export'])
    parser.add_argument('--output', type=Path, default=SHARED_DB, help='Export destination')
    args = parser.parse_args()
    if args.action == 'init':
        print('Initialized from shared snapshot.' if initialize_database() else 'Existing database kept unchanged.')
    else:
        copy_database(db._db_path(), args.output)
        print('Shared snapshot updated. Review and commit it to share with the team.')
