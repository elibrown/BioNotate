import os
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.db_snapshot import initialize_database


def test_shared_snapshot_initializes_once_and_preserves_local_data():
    with TemporaryDirectory() as directory:
        target = Path(directory) / 'runtime.sqlite3'
        with patch.dict(os.environ, {'ASTROHEALTH_DB': str(target)}):
            assert initialize_database()
            with sqlite3.connect(target) as connection:
                assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
                assert connection.execute('SELECT COUNT(*) FROM measurements').fetchone()[0] > 0
                connection.execute("INSERT INTO astronauts(id,name) VALUES ('LOCAL', 'Local Crew')")
            assert not initialize_database()
            with sqlite3.connect(target) as connection:
                assert connection.execute("SELECT name FROM astronauts WHERE id='LOCAL'").fetchone()[0] == 'Local Crew'
