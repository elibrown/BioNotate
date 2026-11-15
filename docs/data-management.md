# Data management: three production tables

All values used by the application belong to these production tables:

| Table | Purpose | Shared snapshot count |
| --- | --- | ---: |
| astronauts | Crew IDs, names and roles | 4 |
| predictions | Full saved model results | 10 in shared snapshot |
| measurements | Every manual, model and imported biology reading | 616 in shared snapshot |

The reviewed shared snapshot contains 616 measurements: 387 seed readings, 220 biology readings and 9 explicitly synthetic demo vitals. Working databases may additionally contain local uploads.
These counts describe the shared snapshot. A working database can also retain older local readings.

## Production versus draft

SQLite uses attached databases rather than PostgreSQL-style named schemas:

- Production/main: `/app/storage/astrohealth.db`, with the three domain tables above.
- Draft: `/app/storage/astrohealth-draft.sqlite3`, attached as `draft` during imports.
  Raw CSV rows, file hashes and import assignments are kept here for audit/staging.
  The application does not read graph values from these draft tables.

SQLite's internal `sqlite_sequence` table is system metadata, not another domain table.

The migration copies the old research tables into draft, verifies their contents,
promotes mapped values into production measurements, then removes the old research
tables from main in the same transaction. Legacy measurements keep their IDs,
values and timestamps. A pre-migration backup was taken before changing local data.

## CSV to measurements

The authoritative import file is `data/research/biologist-final.csv`. Reference
scripts and the intermediate CSV stay in `docs/biologist_docs/`. Intermediate
unmapped subjects stay in draft; only the explicitly mapped final profiles are
promoted automatically.

Each nonblank cell becomes one production measurement. Example:

| astronaut_id | metric | value | unit | measured_at | phase_index | source |
| --- | --- | ---: | --- | --- | ---: | --- |
| A-01 | BM01_WBC | 5.4 | 10⁹ cells/L | NULL | 1 | biologist_csv |
| A-01 | BM02_Serum_Calcium | 9.7 | mg/dL | NULL | 1 | biologist_csv |
| A-01 | BM03_IL6 | 2.87 | pg/mL | NULL | 1 | biologist_csv |

BM05 is stored as BM05_LCN2. Heart rate uses the existing `hr_bpm` key and
respiratory rate uses `respi_rate`, so model and imported readings share metric
identities. Each imported row also stores dataset ID/filename, original subject,
original metric, source row, mission phase, modality and a provenance quality flag.
A-01 maps to Astronaut 1, through A-04 mapping to Astronaut 4.

Research readings have `context=research`; existing model/manual readings default
to `context=live`. Mission-phase readings have a NULL collection timestamp because
the CSV supplies no real collection time. Blanks are absent, never zero-filled.
A unique dataset/row/original-metric index prevents duplicate production imports.
New CSV content is a separate version. Imported profiles remain synthetic and can
contain derived or cross-subject pooled values; they do not replace live readings.

## One graph data source

All trends read production `measurements`:

```text
manual entry ─┐
video/audio ──┼─→ production.measurements → measurement API → trend graphs
CSV import ───┘
```

`GET /api/measurements` lists values with crew, source, metric, context, dataset,
and date filters. `GET /api/measurements/trends?astronaut_id=A-01` returns every
stored metric/source, grouped into separate series. Add `metric=hr_bpm` to get
both model and imported HR. Each series declares `axis=timestamp` or
`axis=mission_phase`; the graph must not connect these incompatible axes, units,
sources or dataset versions into a single line.

The older `/api/research/crew/{id}` endpoint remains a compatibility response for
the existing graph. It now reads production measurements, not draft observations.
No frontend files were changed for this migration. The general trends endpoint
is ready for the UI owner to use for arbitrary stored metrics.

## Startup, inspection and backup

Startup merges `data/seed/shared_demo.db` into the working database, without overwriting local rows. Prediction IDs are remapped where necessary and measurements are deduplicated. The seed JSON is used only as a fallback if the snapshot is absent. The packaged biology import remains idempotent.
`ASTROHEALTH_IMPORT_BIOLOGY=false` disables the packaged import without deleting
anything. Production data is in the persistent Docker `database` named volume.

```sh
docker compose -f compose.yaml -f compose.dev.yaml up -d --no-build --wait
docker compose exec -T app python -m app.data.management status
docker compose exec -T app python -m app.data.management init
docker compose exec -T app python -m app.data.management backup /app/storage/backup-001.db
docker compose cp app:/app/storage/backup-001.db ./backup-001.db
```

Backup captures all three production tables, including imported biology values
and provenance. Back up the draft file separately while the app is stopped if raw
staging history is needed; it is not required for serving trends. Back up uploads
separately. Never overwrite a running database with a backup. `down -v` deletes
the database volume. Changing project names selects a separate volume.

## Deployment and sharing

The workflow `.github/workflows/deploy.yml` deploys Cloud Run service astro-health
in project bionotate, us-central1. It currently uses temporary SQLite in `/tmp`.
Packaging the seed and CSV recreates reference data, but does not preserve newly
entered data across Cloud Run instance replacement. There is no durable shared
cloud database today.

The deployment image packages `data/research/biologist-final.csv`,
`data/biomarkers.json` and `data/schema/`. FastAPI startup loads the seed on a
fresh database and promotes 220 biology values into production measurements.
No separate upload/import command is required after deployment. The production
frontend is taken unchanged from main; the metrics and generic trend API are
available for its owner to display. This branch contains no API proxy or
synchronization feature.

The authoritative crew names/roles are in `data/astronauts.json`, matched by ID
with the deployed roster. Startup refreshes these metadata fields for configured
IDs without replacing readings or deleting extra members. Biology profiles keep
their original subject labels and synthetic/proxy provenance. Crew detail's
**Key Vitals (Trend)** section queries `/api/measurements/trends` for every source.

## Shared demo snapshot

`data/seed/shared_demo.db` is the reviewed database shipped in Git and Docker.
It contains only the three production tables. Other developers receive the same
baseline when they pull this branch and restart/rebuild Docker. Their own readings
remain in their separate working volume; this is baseline distribution, not live
synchronization. Restarting does not duplicate rows or overwrite local predictions.

The snapshot is built from `astrohealth_seed.json`, `biologist-final.csv`, the
crew/biomarker configuration, and `data/demo_vitals.json`. It is never generated
from a developer's captured/personal database. Only this reviewed `.db` path is
allowed by Git; working databases remain ignored.

The nine extra HR/RR readings have source `shared_demo`, fixed fixture timestamps
and `quality_flag=synthetic_demo_not_a_clinical_measurement`. Dashboard vitals use
the latest timestamped reading for the metric, across live sources. Research-phase
readings are excluded. Later genuine readings therefore supersede demo values,
and actual alert rules still apply. Existing voice-score alerts are not suppressed.

To build a candidate snapshot after changing reviewed fixtures:

```sh
docker compose exec -T app python -m app.data.management build-snapshot /tmp/shared-demo-candidate.db
docker compose cp app:/tmp/shared-demo-candidate.db ./shared-demo-candidate.db
```

Review the candidate and replace the tracked snapshot deliberately. The command
refuses to overwrite files. Rebuild Docker images after updating the snapshot;
development data mounts pick up the file on the next app startup. No automatic
cloud synchronization or production deployment is part of these changes.

Graph headers are generic metric names/units. Sources and dataset IDs stay in the database/API, not visible headers. Recorded times are formatted `YYYYMMDD HH:mm:ss` in UTC. Each metric/unit has one graph panel; a time-axis selector is shown only when both timestamp and mission-phase data exist.

Trend queries normalize metric/unit aliases (for example heart_rate and hr_bpm) without changing stored raw records. The UI groups them into one metric panel across sources. Plot positions use equal observation spacing; tooltips and values retain actual timestamps.

Every configured warning or alert has an explicit issue in both the member's
`issues` list and the dashboard's aggregate `alerts` list. Missing/stale data are
warning issues, not clinical/model threshold alerts. Both Status Summary and
Status Report use this same issue list.

The shared demo includes one intentional yellow warning: A-02 / Victor Glover, HR 105 bpm at 20261115 11:17:00 UTC. Its issue appears in both personal Status Summary and the general Status Report.
