# SQL schema definitions

- `production.sql`: the three production domain tables.
- `indexes.sql`: production query indexes and CSV import uniqueness.
- `draft.sql`: import staging tables in an attached draft database.

`app/db.py` creates production tables, upgrades the legacy measurements layout
without changing existing row IDs/values, then applies indexes. The upgrade derives
the replacement table definition from `production.sql`; Python does not contain a
second copy of the column definitions. Future structural changes also need an
explicit data-preserving upgrade, not just an edit to CREATE TABLE IF NOT EXISTS.

`app/data/imports.py` attaches the draft file and applies `draft.sql`. It migrates
legacy research tables from production into draft and promotes mapped values into
production measurements. The application never uses draft as its trend value store.

SQLite's main database is the production boundary; `draft` is an attached database.
No PostgreSQL server or PostgreSQL schema syntax is implied.
