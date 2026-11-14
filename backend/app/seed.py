"""
Shared seed data: the database rows the team keeps in git.

The database file (backend/astrohealth.db) is binary and git-ignored, so we
share its contents as text instead: data/seed/astrohealth_seed.json.

  Export your local database to that file (run from backend/):
      python -m app.seed export

  Load it: automatic. When the backend starts and the database has no
  predictions or measurements yet, the file is loaded. A database that
  already has data is never touched. To start over from the file, stop the
  backend, delete backend/astrohealth.db and start it again.

File format: one JSON object with a list per table. Each row is on its own
line and rows are sorted by id, so a new row shows up in `git diff` as one
new line.
"""

import json
import sys
from pathlib import Path

from app import db

SEED_FILE = Path(__file__).resolve().parents[2] / "data" / "seed" / "astrohealth_seed.json"


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


if __name__ == "__main__":
    if sys.argv[1:] != ["export"]:
        sys.exit("usage: python -m app.seed export")
    counts = export_seed()
    print(f"Wrote {SEED_FILE}")
    for table, n in counts.items():
        print(f"  {table}: {n} rows")
