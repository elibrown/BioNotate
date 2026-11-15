# Seed deployment validation (before the data-management fix)

Historical findings below describe the earlier implementation. Current startup and
persistence behavior are documented in [data management](../data-management.md).

Validated `backend/app/seed.py`, `backend/app/db.py` and the actual
`data/seed/astrohealth_seed.json` inside disposable Docker containers. No running
application database or cloud deployment was changed.

## Results

- Five existing seed tests passed.
- Actual seed imported exactly: four astronauts, six predictions, 54 measurements.
- Exported database rows matched the input JSON exactly.
- SQLite integrity and foreign-key checks passed.
- Repeating startup skipped loading, without creating duplicates.
- All 54 measurements are voice-model outputs; biology research is not included.

## Limits relevant to deployment

1. **Bootstrap only.** `load_seed_if_empty()` does nothing once any prediction or
   measurement exists. Updating the JSON and redeploying does not update an
   existing populated database.
2. **Research is excluded.** `db.SEED_TABLES` includes only astronauts, predictions
   and measurements. Research datasets, observations and crew links are neither
   exported nor restored. Current biology imports therefore stay in the database
   where the CSV importer ran, unless that import is repeated elsewhere.
3. **Stable IDs are not a merge strategy.** `load_tables()` uses INSERT OR IGNORE
   with preserved primary keys. Calling it against populated databases can skip
   different rows that share IDs; it does not compare content or update records.
4. **Runtime configuration differs from checked-in Compose.** The inspected
   running container has a persistent database mount and starts with
   `python -m app.db_snapshot init`, but this checkout has no db_snapshot module
   and its Compose files do not contain that command or database mount. The
   container may predate this checkout. A fresh deployment must not rely on those
   undocumented runtime differences.
5. **An image is not a persistent database backup.** The Dockerfile copies seed
   JSON. SQLite writes made after startup are not copied back to that file.

## Next implementation

Keep seed initialization for fresh demo instances. Add a separate versioned,
idempotent biology import that can update a populated database, preserving the
220 observations, dataset hash, original row identities and four crew mappings.
Include that research dataset in the deployment artifact (or a documented mounted
input), and run the import against the server's configured database. Do not clear
existing measurements to force seed initialization. Reconcile persistence and
startup configuration before deploying.

If the intended deployment file is a different script, review that exact file
before treating these results as validation of it.
